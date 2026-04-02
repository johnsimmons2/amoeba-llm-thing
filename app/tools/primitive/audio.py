"""Audio generation tools — let agents create audio via local models."""

from __future__ import annotations

import json
from typing import Any

from app.tools import Tool


def make_audio_tools(mesh: Any) -> list[Tool]:
    audio = mesh.audio_provider

    async def generate_audio(
        prompt: str,
        model: str = "",
        duration: float = 10.0,
        guidance_scale: float = 3.0,
    ) -> str:
        """Generate audio from a text prompt using a local model (MusicGen or AudioLDM).

        This will load the audio model into GPU VRAM.
        Call unload_audio when done to free VRAM for the LLM.

        Args:
            prompt: Description of the audio to generate (e.g. "upbeat electronic dance music").
            model: HuggingFace model id (default: facebook/musicgen-small).
            duration: Audio length in seconds (1-60, default 10).
            guidance_scale: How closely to follow the prompt (default 3.0).
        """
        result = await audio.generate_audio(
            prompt=prompt,
            model=model,
            duration=duration,
            guidance_scale=guidance_scale,
        )
        return json.dumps(result)

    async def unload_audio() -> str:
        """Unload the audio model from VRAM so the LLM can use it again."""
        return await audio.unload()

    async def list_audio_models() -> str:
        """List available audio generation models."""
        return json.dumps(audio.available_models(), indent=2)

    async def audio_status() -> str:
        """Check if an audio pipeline is currently loaded and which model."""
        return json.dumps(audio.status())

    return [
        Tool(
            name="generate_audio",
            description="Generate audio (music or sound effects) from a text prompt using a local model. "
                        "Loads the model into GPU (VRAM shared with LLM). "
                        "Call unload_audio when done.",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Description of the audio to generate"},
                    "model": {"type": "string", "description": "HuggingFace model id (optional, default: musicgen-small)"},
                    "duration": {"type": "number", "description": "Audio length in seconds (1-60, default 10)"},
                    "guidance_scale": {"type": "number", "description": "Prompt adherence (default 3.0)"},
                },
                "required": ["prompt"],
            },
            func=generate_audio,
        ),
        Tool(
            name="unload_audio",
            description="Unload the audio model from VRAM to free memory for the LLM.",
            parameters={"type": "object", "properties": {}},
            func=unload_audio,
        ),
        Tool(
            name="list_audio_models",
            description="List available audio generation models with VRAM requirements.",
            parameters={"type": "object", "properties": {}},
            func=list_audio_models,
        ),
        Tool(
            name="audio_status",
            description="Check which audio model (if any) is loaded in VRAM.",
            parameters={"type": "object", "properties": {}},
            func=audio_status,
        ),
    ]
