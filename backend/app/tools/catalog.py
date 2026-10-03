"""The operator's full tool catalogue. Adding a capability means adding it here; nothing in
the agent runtime changes."""

from app.tools.browser.tools import browser_tools
from app.tools.control import control_tools
from app.tools.files.tools import file_tools
from app.tools.http.tool import http_tools
from app.tools.registry import ToolRegistry


def default_registry() -> ToolRegistry:
    return ToolRegistry([*browser_tools(), *file_tools(), *http_tools(), *control_tools()])
