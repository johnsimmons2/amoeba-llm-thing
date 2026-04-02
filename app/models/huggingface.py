"""Local image/video generation via HuggingFace diffusers — fully offline after first download."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from pathlib import Path

from app.config import DATA_DIR, HF_TOKEN, CIVITAI_API_KEY

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

IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_IMAGE_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

# Known models the agent can pick from.  Downloaded on first use.
KNOWN_MODELS: list[dict] = [
    # ── Standard safetensors models ──
    {"name": "stabilityai/stable-diffusion-xl-base-1.0", "type": "image", "format": "safetensors",
     "vram": "~7 GB", "description": "SDXL 1.0 — high-quality 1024×1024 images"},
    {"name": "stabilityai/sdxl-turbo", "type": "image", "format": "safetensors",
     "vram": "~7 GB", "description": "SDXL Turbo — fast 1-4 step generation",
     "recommended": {"steps": 4, "guidance_scale": 0.0}},
    {"name": "stabilityai/stable-diffusion-3.5-medium", "type": "image", "format": "safetensors",
     "vram": "~8 GB", "description": "SD 3.5 Medium — latest Stability AI model"},
    {"name": "black-forest-labs/FLUX.1-schnell", "type": "image", "format": "safetensors",
     "vram": "~12 GB", "description": "FLUX.1 schnell — fast high-quality images",
     "recommended": {"steps": 4, "guidance_scale": 0.0}},
    {"name": "Lykon/dreamshaper-xl-v2-turbo", "type": "image", "format": "safetensors",
     "vram": "~7 GB", "description": "DreamShaper XL v2 Turbo — artistic images"},
    # ── GGUF quantized models (Flux architecture) ──
    {"name": "city96/FLUX.1-dev-gguf (Q4_0)", "type": "image", "format": "gguf",
     "vram": "~10 GB", "description": "FLUX.1 Dev — 4-bit GGUF, high quality",
     "gguf_repo": "city96/FLUX.1-dev-gguf", "gguf_file": "flux1-dev-Q4_0.gguf",
     "base_pipeline": "black-forest-labs/FLUX.1-dev",
     "recommended": {"steps": 20, "guidance_scale": 3.5}},
    {"name": "shuttleai/shuttle-jaguar (Q4_K_S)", "type": "image", "format": "gguf",
     "vram": "~8 GB", "description": "Shuttle Jaguar — Flux-based 12B, 4-bit GGUF",
     "gguf_repo": "shuttleai/shuttle-jaguar", "gguf_file": "shuttle-jaguar-Q4_K_S.gguf",
     "base_pipeline": "black-forest-labs/FLUX.1-schnell",
     "recommended": {"steps": 4, "guidance_scale": 3.5}},
]


# Map CivitAI base-model strings to diffusers pipeline class names
CIVITAI_PIPELINE_MAP: dict[str, str] = {
    "SD 1.4": "StableDiffusionPipeline",
    "SD 1.5": "StableDiffusionPipeline",
    "SD 1.5 LCM": "StableDiffusionPipeline",
    "SD 2.0": "StableDiffusionPipeline",
    "SD 2.1": "StableDiffusionPipeline",
    "SDXL 0.9": "StableDiffusionXLPipeline",
    "SDXL 1.0": "StableDiffusionXLPipeline",
    "SDXL 1.0 LCM": "StableDiffusionXLPipeline",
    "SDXL Turbo": "StableDiffusionXLPipeline",
    "SDXL Lightning": "StableDiffusionXLPipeline",
    "Flux.1 D": "FluxPipeline",
    "Flux.1 S": "FluxPipeline",
    "SD 3": "StableDiffusion3Pipeline",
    "SD 3.5": "StableDiffusion3Pipeline",
    "SD 3.5 Medium": "StableDiffusion3Pipeline",
    "SD 3.5 Large": "StableDiffusion3Pipeline",
}


class DiffusionProvider:
    """Manages local diffusion pipelines on GPU.

    Only one pipeline is loaded at a time to conserve VRAM.
    Call ``unload()`` before switching back to Ollama LLMs.
    """

    def __init__(self) -> None:
        self._pipeline = None
        self._loaded_model: str = ""
        self._pipeline_type: str = ""
        self._clip_skip: int = 0
        self._lock = threading.Lock()
        self._used_models: set[str] = set()
        self._model_configs: dict[str, dict] = {}
        for m in KNOWN_MODELS:
            if m.get("format") == "gguf":
                self._model_configs[m["name"]] = m

    @property
    def loaded_model(self) -> str:
        return self._loaded_model

    def _apply_clip_skip(self, clip_skip: int) -> None:
        """Apply clip_skip by truncating text encoder hidden layers.

        For SDXL the primary text encoder (text_encoder) is CLIP-L with 12
        hidden layers.  clip_skip=2 means use up to layer -2 (10 layers).
        We store the original count so we can restore later.
        """
        if clip_skip == self._clip_skip:
            return
        pipe = self._pipeline
        if pipe is None:
            return

        te = getattr(pipe, "text_encoder", None)
        if te is None:
            return

        # Restore original layer count first
        original = getattr(te.config, "_original_num_hidden_layers", None)
        if original is None:
            # First time — save the original
            te.config._original_num_hidden_layers = te.config.num_hidden_layers
            original = te.config.num_hidden_layers

        if clip_skip > 0:
            new_layers = max(1, original - (clip_skip - 1))
            te.config.num_hidden_layers = new_layers
            logger.info("clip_skip=%d → text_encoder layers: %d→%d", clip_skip, original, new_layers)
        else:
            te.config.num_hidden_layers = original
            logger.info("clip_skip reset → text_encoder layers: %d", original)

        self._clip_skip = clip_skip

    # ------------------------------------------------------------------
    # Pipeline management
    # ------------------------------------------------------------------

    def _load_pipeline(self, model: str) -> None:
        """Load (or switch to) a diffusion pipeline.  Runs on the calling thread."""
        if self._loaded_model == model and self._pipeline is not None:
            return

        self.unload_sync()

        config = self._model_configs.get(model, {})
        source = config.get("source", "huggingface")
        if config.get("format") == "gguf":
            self._load_gguf_pipeline(model, config)
        elif source == "civitai":
            self._load_civitai_pipeline(model, config)
        else:
            self._load_standard_pipeline(model)

    def _load_standard_pipeline(self, model: str) -> None:
        """Load a standard safetensors pipeline via AutoPipelineForText2Image."""
        import torch
        from diffusers import AutoPipelineForText2Image

        logger.info("Loading diffusion pipeline: %s", model)
        kwargs: dict = dict(torch_dtype=torch.float16)
        if HF_TOKEN:
            kwargs["token"] = HF_TOKEN

        # Try fp16 variant first; fall back to default if not available
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(model, variant="fp16", **kwargs)
        except OSError:
            logger.info("fp16 variant not available for %s, loading default", model)
            pipe = AutoPipelineForText2Image.from_pretrained(model, **kwargs)
        pipe.to("cuda")

        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass

        self._pipeline = pipe
        self._pipeline_type = "standard"
        self._loaded_model = model
        self._used_models.add(model)
        logger.info("Diffusion pipeline loaded: %s", model)

    def _load_gguf_pipeline(self, model: str, config: dict) -> None:
        """Load a GGUF-quantized Flux pipeline with CPU offloading."""
        import torch
        from diffusers import FluxPipeline, FluxTransformer2DModel, GGUFQuantizationConfig

        gguf_repo = config["gguf_repo"]
        gguf_file = config["gguf_file"]
        base_pipeline = config["base_pipeline"]

        ckpt_url = f"https://huggingface.co/{gguf_repo}/blob/main/{gguf_file}"

        logger.info("Loading GGUF transformer from %s/%s", gguf_repo, gguf_file)
        sf_kwargs: dict = dict(
            quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            torch_dtype=torch.bfloat16,
        )
        if HF_TOKEN:
            sf_kwargs["token"] = HF_TOKEN
        transformer = FluxTransformer2DModel.from_single_file(ckpt_url, **sf_kwargs)

        logger.info("Building FluxPipeline from base: %s", base_pipeline)
        fp_kwargs: dict = dict(
            transformer=transformer,
            torch_dtype=torch.bfloat16,
        )
        if HF_TOKEN:
            fp_kwargs["token"] = HF_TOKEN
        pipe = FluxPipeline.from_pretrained(base_pipeline, **fp_kwargs)
        pipe.enable_model_cpu_offload()

        self._pipeline = pipe
        self._pipeline_type = "flux"
        self._loaded_model = model
        self._used_models.add(model)
        logger.info("GGUF pipeline loaded: %s", model)

    def _load_civitai_pipeline(self, model: str, config: dict) -> None:
        """Load a CivitAI single-file checkpoint."""
        import torch
        import diffusers

        local_path = MODELS_DIR / config["civitai_filename"]

        if not local_path.exists():
            logger.info("Downloading CivitAI model to %s", local_path)
            self._download_file(config["download_url"], local_path)

        pipeline_cls_name = config.get("pipeline_class", "StableDiffusionXLPipeline")
        PipeClass = getattr(diffusers, pipeline_cls_name)

        logger.info("Loading CivitAI checkpoint: %s via %s", local_path.name, pipeline_cls_name)
        sf_kwargs: dict = dict(torch_dtype=torch.float16)
        if HF_TOKEN:
            sf_kwargs["token"] = HF_TOKEN
        pipe = PipeClass.from_single_file(str(local_path), **sf_kwargs)
        pipe.to("cuda")

        try:
            pipe.enable_xformers_memory_efficient_attention()
        except Exception:
            pass

        self._pipeline = pipe
        self._pipeline_type = "civitai"
        self._loaded_model = model
        self._used_models.add(model)
        logger.info("CivitAI pipeline loaded: %s", model)

    @staticmethod
    def _download_file(url: str, dest: Path) -> None:
        """Stream-download a file with optional CivitAI auth."""
        import httpx

        headers: dict[str, str] = {}
        if CIVITAI_API_KEY:
            headers["Authorization"] = f"Bearer {CIVITAI_API_KEY}"

        with httpx.stream(
            "GET", url, headers=headers, follow_redirects=True, timeout=600,
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            total_mb = total / (1024 * 1024) if total else 0
            tmp = dest.with_suffix(".part")
            written = 0
            last_logged = 0
            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    written += len(chunk)
                    mb = written / (1024 * 1024)
                    if mb - last_logged >= 100:
                        pct = f" ({mb / total_mb * 100:.0f}%)" if total_mb else ""
                        logger.info("Download progress: %.0f / %.0f MB%s", mb, total_mb, pct)
                        last_logged = mb
            logger.info("Download complete: %.1f MB", written / (1024 * 1024))
            tmp.replace(dest)  # .replace() works atomically on Windows

    def unload_sync(self) -> None:
        """Free VRAM immediately."""
        if self._pipeline is not None:
            import torch

            del self._pipeline
            self._pipeline = None
            self._loaded_model = ""
            self._pipeline_type = ""
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Diffusion pipeline unloaded, VRAM freed")

    async def unload(self) -> str:
        """Async wrapper for unloading."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.unload_sync)
        return "Diffusion pipeline unloaded"

    async def load(self, model: str) -> str:
        """Load a pipeline without generating — useful for preloading."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._load_pipeline, model)
        return f"Diffusion pipeline loaded: {model}"

    # ------------------------------------------------------------------
    # Image generation
    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        prompt: str,
        model: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        guidance_scale: float,
        clip_skip: int = 0,
        seed: int = -1,
        batch_count: int = 1,
    ) -> list[dict]:
        import torch
        results = []
        with self._lock:
            self._load_pipeline(model)
            assert self._pipeline is not None

            # Apply clip_skip at the text encoder level
            if self._pipeline_type != "flux":
                self._apply_clip_skip(clip_skip)

            for i in range(batch_count):
                generator = None
                actual_seed = seed
                if seed >= 0:
                    actual_seed = seed + i
                    generator = torch.Generator(device="cuda").manual_seed(actual_seed)
                else:
                    actual_seed = torch.randint(0, 2**32, (1,)).item()
                    generator = torch.Generator(device="cuda").manual_seed(actual_seed)

                kwargs: dict = {
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_inference_steps": steps,
                    "guidance_scale": guidance_scale,
                    "generator": generator,
                }
                if negative_prompt and self._pipeline_type != "flux":
                    kwargs["negative_prompt"] = negative_prompt

                result = self._pipeline(**kwargs)
                image = result.images[0]

                filename = f"{uuid.uuid4().hex[:12]}.png"
                filepath = IMAGES_DIR / filename
                image.save(filepath)

                size_bytes = filepath.stat().st_size
                logger.info("Image saved: %s (%d bytes) [%d/%d]", filename, size_bytes, i + 1, batch_count)

                # Save generation metadata sidecar
                import json as _json
                meta = {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "model": model,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "guidance_scale": guidance_scale,
                    "clip_skip": clip_skip,
                    "seed": actual_seed,
                    "pipeline_type": self._pipeline_type,
                }
                meta_path = filepath.with_suffix(".json")
                meta_path.write_text(_json.dumps(meta, indent=2), encoding="utf-8")

                results.append({
                    "path": f"data/images/{filename}",
                    "filename": filename,
                    "model": model,
                    "size_bytes": size_bytes,
                    "seed": actual_seed,
                })

        return results

    async def generate_image(
        self,
        prompt: str,
        model: str = "",
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        guidance_scale: float = 7.5,
        clip_skip: int = 0,
        seed: int = -1,
        batch_count: int = 1,
    ) -> list[dict]:
        """Generate image(s) locally.  Returns list of {path, filename, model, size_bytes, seed}."""
        import functools
        model = model or DEFAULT_IMAGE_MODEL
        batch_count = max(1, min(batch_count, 50))
        logger.info("Image gen request: model=%s clip_skip=%s batch=%d prompt=%s", model, clip_skip, batch_count, prompt[:80])

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._generate_sync,
                prompt=prompt, model=model, negative_prompt=negative_prompt,
                width=width, height=height, steps=steps,
                guidance_scale=guidance_scale, clip_skip=clip_skip,
                seed=seed, batch_count=batch_count,
            ),
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def available_models(self) -> list[dict]:
        known_names = {m["name"] for m in KNOWN_MODELS}
        result = []
        for m in KNOWN_MODELS:
            source = m.get("source", "huggingface")
            cache_name = m.get("gguf_repo", m["name"])
            dl = _is_model_cached(cache_name) if source == "huggingface" else False
            result.append({**m, "source": source, "loaded": m["name"] == self._loaded_model, "downloaded": dl})
        # Append any custom models the user has loaded
        for name in sorted(self._used_models - known_names):
            config = self._model_configs.get(name, {})
            source = config.get("source", "huggingface")
            downloading = False
            if source == "civitai":
                fname = config.get("civitai_filename", "")
                dl = (MODELS_DIR / fname).exists() if fname else False
                downloading = not dl and (MODELS_DIR / (fname + ".part")).exists() if fname else False
            else:
                cache_name = config.get("gguf_repo", name)
                dl = _is_model_cached(cache_name)
            entry = {
                "name": name,
                "type": "image",
                "source": source,
                "format": config.get("format", "safetensors"),
                "vram": config.get("vram", "unknown"),
                "description": config.get("description", "Custom model"),
                "loaded": name == self._loaded_model,
                "downloaded": dl,
                "downloading": downloading,
            }
            if config.get("format") == "gguf":
                entry.update({
                    "gguf_repo": config["gguf_repo"],
                    "gguf_file": config["gguf_file"],
                    "base_pipeline": config["base_pipeline"],
                })
            if "recommended" in config:
                entry["recommended"] = config["recommended"]
            result.append(entry)
        return result

    def status(self) -> dict:
        rec = {}
        fmt = ""
        if self._loaded_model:
            for m in KNOWN_MODELS:
                if m["name"] == self._loaded_model:
                    rec = m.get("recommended", {})
                    fmt = m.get("format", "safetensors")
                    break
            else:
                config = self._model_configs.get(self._loaded_model, {})
                rec = config.get("recommended", {})
                fmt = config.get("format", "safetensors")
        return {
            "loaded_model": self._loaded_model,
            "pipeline_loaded": self._pipeline is not None,
            "pipeline_type": self._pipeline_type,
            "format": fmt,
            "recommended": rec,
        }

    def add_gguf_model(
        self, name: str, gguf_repo: str, gguf_file: str, base_pipeline: str,
        description: str = "", vram: str = "",
    ) -> None:
        """Register a custom GGUF model for loading."""
        config = {
            "name": name,
            "type": "image",
            "source": "huggingface",
            "format": "gguf",
            "gguf_repo": gguf_repo,
            "gguf_file": gguf_file,
            "base_pipeline": base_pipeline,
            "description": description or "Custom GGUF model",
            "vram": vram or "unknown",
        }
        self._model_configs[name] = config
        self._used_models.add(name)

    def add_civitai_model(
        self, name: str, download_url: str, civitai_filename: str,
        pipeline_class: str = "StableDiffusionXLPipeline",
        description: str = "", vram: str = "",
        recommended: dict | None = None,
    ) -> None:
        """Register a CivitAI model for download-on-load."""
        config = {
            "name": name,
            "type": "image",
            "source": "civitai",
            "format": "safetensors",
            "download_url": download_url,
            "civitai_filename": civitai_filename,
            "pipeline_class": pipeline_class,
            "description": description or "CivitAI model",
            "vram": vram or "unknown",
        }
        if recommended:
            config["recommended"] = recommended
        self._model_configs[name] = config
        self._used_models.add(name)
