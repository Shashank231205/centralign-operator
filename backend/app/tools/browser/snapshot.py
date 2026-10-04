"""Typed page snapshot and its compact text rendering for the model."""

from pathlib import Path

from pydantic import BaseModel, Field

SNAPSHOT_SCRIPT = (Path(__file__).parent / "snapshot.js").read_text(encoding="utf-8")


class ElementInfo(BaseModel):
    ref: str
    tag: str
    type: str = ""
    label: str = ""
    name: str = ""
    form: int = -1
    submits: bool = False
    href: str | None = None
    value: str | None = None
    options: list[str] = Field(default_factory=list)


class FormInfo(BaseModel):
    index: int
    method: str
    action: str
    fields: dict[str, str]
    has_password: bool = False


class TableInfo(BaseModel):
    label: str = ""
    rows: list[list[str]]


class PageSnapshot(BaseModel):
    url: str
    title: str
    alerts: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    elements: list[ElementInfo] = Field(default_factory=list)
    forms: list[FormInfo] = Field(default_factory=list)
    text: str = ""
    status: int | None = None

    def element(self, ref: str) -> ElementInfo | None:
        return next((element for element in self.elements if element.ref == ref), None)

    def form_of(self, element: ElementInfo) -> FormInfo | None:
        return self.forms[element.form] if 0 <= element.form < len(self.forms) else None

    def render(self, budget: int) -> str:
        lines = [f"URL: {self.url}", f"TITLE: {self.title}"]
        if self.status:
            lines.append(f"HTTP STATUS: {self.status}")
        lines += [f"MESSAGE: {alert}" for alert in self.alerts]
        if self.headings:
            lines.append("HEADINGS: " + " | ".join(self.headings))
        lines.append("ELEMENTS:")
        lines += [f"  {_describe(element)}" for element in self.elements]
        for table in self.tables:
            lines.append(f"TABLE {table.label!r}:")
            lines += ["  " + " | ".join(row) for row in table.rows]
        text = "\n".join(lines)
        # Tables and form fields already carry the content; raw page text would repeat it.
        has_structure = bool(self.tables) or any(element.form >= 0 for element in self.elements)
        if not has_structure and len(text) < budget:
            text += f"\nPAGE TEXT: {self.text[: budget - len(text)]}"
        return text[:budget]


def _describe(element: ElementInfo) -> str:
    kind = (
        element.tag if not element.type or element.tag == "a" else f"{element.tag}[{element.type}]"
    )
    parts = [f"[{element.ref}] {kind} {element.label!r}"]
    if element.value not in (None, ""):
        parts.append(f"= {element.value!r}")
    if element.options:
        parts.append("options: " + ", ".join(element.options))
    if element.href:
        parts.append(f"-> {element.href}")
    if element.submits:
        parts.append("(submits form)")
    return " ".join(parts)
