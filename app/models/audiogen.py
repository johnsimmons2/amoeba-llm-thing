"""Local audio generation via HuggingFace transformers — fully offline after first download."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from pathlib import Path

from app.config import DATA_DIR, HF_TOKEN

logger = logging.getLogger(__name__)


def _is_model_cached(model_name: str) -> bool:
    """Check if a HuggingFace model exists in the local hub cache."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        cache_dir = Path(HF_HUB_CACHE)
    except Exception:
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    snapshots = cache_dir / f"models--{model_name.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())

AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_AUDIO_MODEL = "facebook/musicgen-small"

KNOWN_MODELS: list[dict] = [
    {"name": "facebook/musicgen-small", "type": "music", "vram": "~2 GB", "description": "MusicGen Small — 300M, fast music generation"},
    {"name": "facebook/musicgen-medium", "type": "music", "vram": "~4 GB", "description": "MusicGen Medium — 1.5B, higher quality music"},
    {"name": "facebook/musicgen-large", "type": "music", "vram": "~8 GB", "description": "MusicGen Large — 3.3B, best quality music"},
    {"name": "cvssp/audioldm2", "type": "sound", "vram": "~4 GB", "description": "AudioLDM 2 — sound effects and ambient audio"},
    {"name": "cvssp/audioldm2-music", "type": "music", "vram": "~4 GB", "description": "AudioLDM 2 Music — music via diffusion"},
]


class AudioProvider:
    """Manages local audio generation pipelines on GPU.

    Only one pipeline is loaded at a time to conserve VRAM.
    Call ``unload()`` before switching back to other models.
    """

    def __init__(self) -> None:
        self._pipeline = None
        self._processor = None
        self._loaded_model: str = ""
        self._pipeline_type: str = ""  # "musicgen" or "audioldm"
        self._lock = threading.Lock()
        self._used_models: set[str] = set()

    @property
    def loaded_model(self) -> str:
        return self._loaded_model

    # ------------------------------------------------------------------
    # Pipeline management
    # ------------------------------------------------------------------

    def _load_pipeline(self, model: str) -> None:
        if self._loaded_model == model and self._pipeline is not None:
            return

        import torch

        self.unload_sync()
        logger.info("Loading audio pipeline: %s", model)

        if "musicgen" in model.lower():
            from transformers import AutoProcessor, MusicgenForConditionalGeneration

            self._processor = AutoProcessor.from_pretrained(model, **({"token": HF_TOKEN} if HF_TOKEN else {}))
            self._pipeline = MusicgenForConditionalGeneration.from_pretrained(
                model, torch_dtype=torch.float16, **({"token": HF_TOKEN} if HF_TOKEN else {}),
            ).to("cuda")
            self._pipeline_type = "musicgen"
        elif "audioldm" in model.lower():
            from diffusers import AudioLDM2Pipeline

            self._pipeline = AudioLDM2Pipeline.from_pretrained(
                model, torch_dtype=torch.float16, **({"token": HF_TOKEN} if HF_TOKEN else {}),
            ).to("cuda")
            self._patch_audioldm2()
            self._pipeline_type = "audioldm"
        else:
            # Try musicgen-style first, fall back to audioldm
            try:
                from transformers import AutoProcessor, MusicgenForConditionalGeneration

                self._processor = AutoProcessor.from_pretrained(model, **({"token": HF_TOKEN} if HF_TOKEN else {}))
                self._pipeline = MusicgenForConditionalGeneration.from_pretrained(
                    model, torch_dtype=torch.float16, **({"token": HF_TOKEN} if HF_TOKEN else {}),
                ).to("cuda")
                self._pipeline_type = "musicgen"
            except Exception:
                from diffusers import AudioLDM2Pipeline

                self._pipeline = AudioLDM2Pipeline.from_pretrained(
                    model, torch_dtype=torch.float16, **({"token": HF_TOKEN} if HF_TOKEN else {}),
                ).to("cuda")
                self._patch_audioldm2()
                self._pipeline_type = "audioldm"

        self._loaded_model = model
        self._used_models.add(model)
        logger.info("Audio pipeline loaded: %s (type=%s)", model, self._pipeline_type)

    def _patch_audioldm2(self) -> None:
        """Patch AudioLDM2's internal GPT2Model for newer transformers compat."""
        lm = getattr(self._pipeline, "language_model", None)
        if lm is None:
            return
        if hasattr(lm, "_update_model_kwargs_for_generation"):
            return
        import torch

        def _update_model_kwargs_for_generation(self_lm, outputs, model_kwargs, **kwargs):
            past = getattr(outputs, "past_key_values", None)
            if past is not None:
                model_kwargs["past_key_values"] = past
            if "attention_mask" in model_kwargs:
                am = model_kwargs["attention_mask"]
                model_kwargs["attention_mask"] = torch.cat(
                    [am, am.new_ones((am.shape[0], 1))], dim=-1
                )
            return model_kwargs

        import types
        lm._update_model_kwargs_for_generation = types.MethodType(
            _update_model_kwargs_for_generation, lm
        )
        logger.info("Patched AudioLDM2 language_model with _update_model_kwargs_for_generation")

    def unload_sync(self) -> None:
        if self._pipeline is not None:
            import torch

            del self._pipeline
            del self._processor
            self._pipeline = None
            self._processor = None
            self._loaded_model = ""
            self._pipeline_type = ""
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Audio pipeline unloaded, VRAM freed")

    async def unload(self) -> str:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.unload_sync)
        return "Audio pipeline unloaded"

    async def load(self, model: str) -> str:
        """Load a pipeline without generating — useful for preloading."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_pipeline, model)
        return f"Audio pipeline loaded: {model}"

    # ------------------------------------------------------------------
    # Audio generation
    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        prompt: str,
        model: str,
        duration: float,
        guidance_scale: float,
        custom_filename: str = "",
        batch_count: int = 1,
    ) -> list[dict]:
        import numpy as np
        import re
        import scipy.io.wavfile
        import json as _json

        results = []
        with self._lock:
            self._load_pipeline(model)
            assert self._pipeline is not None

            for i in range(batch_count):
                if self._pipeline_type == "musicgen":
                    inputs = self._processor(
                        text=[prompt], padding=True, return_tensors="pt",
                    ).to("cuda")
                    max_tokens = int(duration * 50)
                    audio_values = self._pipeline.generate(
                        **inputs, max_new_tokens=max_tokens, guidance_scale=guidance_scale,
                    )
                    audio_np = audio_values[0, 0].cpu().float().numpy()
                    sample_rate = self._pipeline.config.audio_encoder.sampling_rate

                elif self._pipeline_type == "audioldm":
                    result = self._pipeline(
                        prompt,
                        audio_length_in_s=duration,
                        guidance_scale=guidance_scale,
                        num_inference_steps=50,
                    )
                    audio_np = result.audios[0]
                    sample_rate = 16000
                else:
                    raise RuntimeError(f"Unknown pipeline type: {self._pipeline_type}")

                # Normalize to int16 WAV
                audio_np = audio_np / (np.abs(audio_np).max() + 1e-8)
                audio_int16 = (audio_np * 32767).astype(np.int16)

                filename = f"{uuid.uuid4().hex[:12]}.wav"
                if custom_filename:
                    safe = re.sub(r'[^\w\-. ]', '', custom_filename).strip()
                    if safe:
                        if not safe.lower().endswith('.wav'):
                            safe += '.wav'
                        if batch_count > 1:
                            base = safe.rsplit('.', 1)[0]
                            filename = f"{base}_{i+1}.wav"
                        else:
                            filename = safe
                filepath = AUDIO_DIR / filename

                scipy.io.wavfile.write(str(filepath), sample_rate, audio_int16)

                size_bytes = filepath.stat().st_size
                logger.info("Audio saved: %s (%d bytes, %.1fs) [%d/%d]", filename, size_bytes, duration, i + 1, batch_count)

                meta = {
                    "prompt": prompt,
                    "model": model,
                    "duration": duration,
                    "guidance_scale": guidance_scale,
                    "sample_rate": sample_rate,
                    "pipeline_type": self._pipeline_type,
                }
                meta_path = filepath.with_suffix(".json")
                meta_path.write_text(_json.dumps(meta, indent=2), encoding="utf-8")

                results.append({
                    "path": f"data/audio/{filename}",
                    "filename": filename,
                    "model": model,
                    "duration": duration,
                    "sample_rate": sample_rate,
                    "size_bytes": size_bytes,
                })

        return results

    async def generate_audio(
        self,
        prompt: str,
        model: str = "",
        duration: float = 10.0,
        guidance_scale: float = 3.0,
        filename: str = "",
        batch_count: int = 1,
    ) -> list[dict]:
        """Generate audio locally. Returns list of {path, filename, model, duration, size_bytes}."""
        model = model or DEFAULT_AUDIO_MODEL
        duration = max(1.0, min(duration, 60.0))
        batch_count = max(1, min(batch_count, 20))
        logger.info("Audio gen request: model=%s duration=%.1fs batch=%d filename=%s prompt=%s", model, duration, batch_count, filename, prompt[:80])

        import functools
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._generate_sync,
                prompt=prompt,
                model=model,
                duration=duration,
                guidance_scale=guidance_scale,
                custom_filename=filename,
                batch_count=batch_count,
            ),
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def available_models(self) -> list[dict]:
        known_names = {m["name"] for m in KNOWN_MODELS}
        result = [
            {**m, "loaded": m["name"] == self._loaded_model, "downloaded": _is_model_cached(m["name"])}
            for m in KNOWN_MODELS
        ]
        for name in sorted(self._used_models - known_names):
            result.append({
                "name": name,
                "type": "audio",
                "vram": "unknown",
                "description": "Custom model",
                "loaded": name == self._loaded_model,
                "downloaded": _is_model_cached(name),
            })
        return result

    def status(self) -> dict:
        return {
            "loaded_model": self._loaded_model,
            "pipeline_loaded": self._pipeline is not None,
            "pipeline_type": self._pipeline_type,
        }
