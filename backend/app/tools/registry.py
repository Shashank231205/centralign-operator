"""Tool discovery and the compact catalogue shown to the model for tool selection."""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.core.errors import ToolInputError
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool[Any]]) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name '{tool.name}'")
            self._tools[tool.name] = tool
        self._catalogue = self._render_catalogue()

    def get(self, name: str) -> Tool[Any]:
        if name not in self._tools:
            raise ToolInputError(f"Unknown tool '{name}'. Available: {', '.join(self._tools)}")
        return self._tools[name]

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    @property
    def catalogue(self) -> str:
        return self._catalogue

    def _render_catalogue(self) -> str:
        return "\n".join(
            f"- {tool.name}({_signature(tool.args_model)}): {tool.description}"
            for tool in self._tools.values()
        )


def _signature(model: type[BaseModel]) -> str:
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    parts = []
    for name, spec in schema.get("properties", {}).items():
        kind = spec.get("type") or "|".join(
            option.get("type", "any") for option in spec.get("anyOf", [])
        )
        optional = "" if name in required else "?"
        hint = f" — {spec['description']}" if "description" in spec else ""
        parts.append(f"{name}{optional}: {kind}{hint}")
    return ", ".join(parts)
