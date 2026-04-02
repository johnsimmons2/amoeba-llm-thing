"""Image generation tools — let agents create images via local diffusion models."""

from __future__ import annotations

import json
from typing import Any

from app.tools import Tool


def make_image_tools(mesh: Any) -> list[Tool]:
    diffusion = mesh.diffusion_provider

    async def generate_image(
        prompt: str,
        model: str = "",
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 20,
        guidance_scale: float = 7.5,
    ) -> str:
        """Generate an image from a text prompt using a local Stable Diffusion model.

        This will load the diffusion model into GPU VRAM (unloading the LLM).
        After generation the pipeline stays loaded for follow-up requests.
        Call unload_diffusion when done to free VRAM for the LLM.

        Args:
            prompt: Detailed description of the image to generate.
            model: HuggingFace model id (default: stabilityai/stable-diffusion-xl-base-1.0).
            negative_prompt: Things to avoid in the image.
            width: Image width in pixels (default 1024).
            height: Image height in pixels (default 1024).
            steps: Inference steps — more = better quality, slower (default 20).
            guidance_scale: How closely to follow the prompt (default 7.5).
        """
        result = await diffusion.generate_image(
            prompt=prompt,
            model=model,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            guidance_scale=guidance_scale,
        )
        return json.dumps(result)

    async def unload_diffusion() -> str:
        """Unload the diffusion model from VRAM so the LLM can use it again.
        Call this after you are done generating images."""
        return await diffusion.unload()

    async def list_diffusion_models() -> str:
        """List available local diffusion models for image generation."""
        models = diffusion.available_models()
        return json.dumps(models, indent=2)

    async def diffusion_status() -> str:
        """Check if a diffusion pipeline is currently loaded and which model."""
        return json.dumps(diffusion.status())

    return [
        Tool(
            name="generate_image",
            description="Generate an image from a text prompt using a local diffusion model. "
                        "Loads the model into GPU (VRAM shared with LLM). "
                        "Call unload_diffusion when done generating.",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Detailed description of the image"},
                    "model": {"type": "string", "description": "HuggingFace model id (optional, default: SDXL)"},
                    "negative_prompt": {"type": "string", "description": "Things to exclude from the image"},
                    "width": {"type": "integer", "description": "Image width (default: 1024)"},
                    "height": {"type": "integer", "description": "Image height (default: 1024)"},
                    "steps": {"type": "integer", "description": "Inference steps (default: 20)"},
                    "guidance_scale": {"type": "number", "description": "Prompt adherence (default: 7.5)"},
                },
                "required": ["prompt"],
            },
            func=generate_image,
        ),
        Tool(
            name="unload_diffusion",
            description="Unload the diffusion model from VRAM to free memory for the LLM.",
            parameters={"type": "object", "properties": {}},
            func=unload_diffusion,
        ),
        Tool(
            name="list_diffusion_models",
            description="List available diffusion models for image generation with VRAM requirements.",
            parameters={"type": "object", "properties": {}},
            func=list_diffusion_models,
        ),
        Tool(
            name="diffusion_status",
            description="Check which diffusion model (if any) is loaded in VRAM.",
            parameters={"type": "object", "properties": {}},
            func=diffusion_status,
        ),
    ]
