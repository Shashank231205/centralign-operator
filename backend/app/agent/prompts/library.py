"""Versioned prompt templates stored as files.

Each template is ``<name>.v<N>.md`` with a system part and a user part separated by a line
containing only ``---USER---``. The newest version is used unless pinned; the version string
is part of the LLM cache key and of every run event, so behaviour changes are traceable.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

_SEPARATOR = "---USER---"
_FILE_PATTERN = re.compile(r"^(?P<name>[a-z_]+)\.v(?P<version>\d+)\.md$")


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    system: str
    user: str
    version: str


@dataclass(frozen=True, slots=True)
class _Template:
    system: str
    user: str
    version: str


class PromptLibrary:
    def __init__(self, directory: Path) -> None:
        self._env = Environment(autoescape=False, undefined=StrictUndefined, trim_blocks=True)  # noqa: S701  # prompts are not HTML
        self._templates = self._load(directory)

    def render(self, name: str, **variables: Any) -> RenderedPrompt:
        template = self._templates[name]
        return RenderedPrompt(
            system=self._env.from_string(template.system).render(**variables).strip(),
            user=self._env.from_string(template.user).render(**variables).strip(),
            version=template.version,
        )

    @staticmethod
    def _load(directory: Path) -> dict[str, _Template]:
        latest: dict[str, tuple[int, Path]] = {}
        for path in directory.glob("*.md"):
            match = _FILE_PATTERN.match(path.name)
            if not match:
                continue
            name, version = match["name"], int(match["version"])
            if name not in latest or version > latest[name][0]:
                latest[name] = (version, path)
        templates = {}
        for name, (version, path) in latest.items():
            system, separator, user = path.read_text(encoding="utf-8").partition(_SEPARATOR)
            if not separator:
                raise ValueError(f"Prompt {path.name} is missing the {_SEPARATOR} separator")
            templates[name] = _Template(system=system, user=user, version=f"{name}.v{version}")
        return templates


DEFAULT_PROMPTS_DIR = Path(__file__).parent / "templates"
