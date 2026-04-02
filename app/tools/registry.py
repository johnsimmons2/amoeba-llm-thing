from __future__ import annotations

import importlib.util
import logging

from app.config import TOOLS_DYNAMIC
from app.tools import Tool
from app.tools.primitive.files import make_file_tools
from app.tools.primitive.shell import make_shell_tools
from app.tools.primitive.http import make_http_tools
from app.tools.primitive.agents import make_agent_tools
from app.tools.primitive.lifecycle import make_lifecycle_tools
from app.tools.primitive.models import make_model_tools
from app.tools.primitive.resources import make_resource_tools
from app.tools.primitive.oracle import make_oracle_tools
from app.tools.primitive.tasks import make_task_tools
from app.tools.primitive.memory import make_memory_tools
from app.tools.primitive.images import make_image_tools
from app.tools.primitive.audio import make_audio_tools

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Builds the full tool list: primitives + dynamically loaded tools."""

    def build_tools(self, mesh: object) -> list[Tool]:
        tools: list[Tool] = []
        tools.extend(make_file_tools())
        tools.extend(make_shell_tools())
        tools.extend(make_http_tools())
        tools.extend(make_agent_tools(mesh))
        tools.extend(make_model_tools(mesh))
        tools.extend(make_resource_tools())
        tools.extend(make_oracle_tools(mesh))
        tools.extend(make_task_tools(mesh))
        tools.extend(make_memory_tools(mesh))
        tools.extend(make_image_tools(mesh))
        tools.extend(make_audio_tools(mesh))
        tools.extend(make_lifecycle_tools())
        tools.extend(self._load_dynamic())
        return tools

    def _load_dynamic(self) -> list[Tool]:
        tools: list[Tool] = []
        for path in sorted(TOOLS_DYNAMIC.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f"dynamic.{path.stem}", path)
                mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                if hasattr(mod, "get_tools"):
                    loaded = mod.get_tools()
                    tools.extend(loaded)
                    logger.info("Loaded %d dynamic tool(s) from %s", len(loaded), path.name)
            except Exception as exc:
                logger.warning("Failed to load %s: %s", path.name, exc)
        return tools
