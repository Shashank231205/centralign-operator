"""Workspace file tools: read documents, write CSV reports, list files."""

import asyncio
import csv
import io
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.domain.enums import EvidenceKind, RiskLevel, ToolKind
from app.domain.models import Assessment, Observation
from app.tools.base import Tool, ToolContext, truncate
from app.tools.files.readers import extract_text

WORKSPACE_SYSTEM = "workspace"


class PathArgs(BaseModel):
    path: str = Field(description="Path relative to the run workspace, e.g. downloads/x.pdf")


class FileRead(Tool[PathArgs]):
    name: ClassVar[str] = "file_read"
    description: ClassVar[str] = "Extract the text of a workspace file (pdf, docx, csv, txt, json)."
    kind: ClassVar[ToolKind] = ToolKind.FILES
    args_model = PathArgs

    async def run(self, args: PathArgs, ctx: ToolContext) -> Observation:
        path = ctx.workspace.resolve(args.path)
        text = await extract_text(path)
        return Observation(
            ok=True,
            summary=f"DOCUMENT {args.path}:\n{truncate(text, ctx.observation_char_budget)}",
            data={"path": args.path, "chars": len(text)},
        )


class CsvArgs(BaseModel):
    path: str = Field(description="Output path relative to the workspace, ending in .csv")
    columns: list[str] = Field(description="Header row")
    rows: list[list[str | int | float]] = Field(description="Data rows, same order as columns")


class FileWriteCsv(Tool[CsvArgs]):
    name: ClassVar[str] = "file_write_csv"
    description: ClassVar[str] = "Write a CSV file (header + rows) into the run workspace."
    kind: ClassVar[ToolKind] = ToolKind.FILES
    args_model = CsvArgs

    async def assess(self, args: CsvArgs, ctx: ToolContext) -> Assessment:
        ctx.workspace.resolve(args.path)
        return Assessment(
            risk=RiskLevel.WRITE,
            system=WORKSPACE_SYSTEM,
            payload={"path": args.path, "row_count": len(args.rows)},
            description=f"write {len(args.rows)} rows to {args.path}",
        )

    async def run(self, args: CsvArgs, ctx: ToolContext) -> Observation:
        bad_rows = [index for index, row in enumerate(args.rows) if len(row) != len(args.columns)]
        if bad_rows:
            return Observation(
                ok=False,
                summary=f"Rows {bad_rows} do not have {len(args.columns)} values; nothing written.",
                error="row/column mismatch",
            )
        content = _to_csv(args.columns, args.rows)
        path = ctx.workspace.resolve(args.path)
        await asyncio.to_thread(_write_text, path, content)
        artifact = await ctx.evidence.save(
            ctx.run_id, path.name, content.encode(), EvidenceKind.REPORT, f"Report {args.path}"
        )
        return Observation(
            ok=True,
            summary=f"Wrote {len(args.rows)} rows to {args.path}.",
            data={"path": args.path, "rows": len(args.rows)},
            artifacts=[artifact],
        )


class NoArgs(BaseModel):
    pass


class FileList(Tool[NoArgs]):
    name: ClassVar[str] = "file_list"
    description: ClassVar[str] = "List files in the run workspace."
    kind: ClassVar[ToolKind] = ToolKind.FILES
    args_model = NoArgs

    async def run(self, args: NoArgs, ctx: ToolContext) -> Observation:  # noqa: ARG002
        files = sorted(
            ctx.workspace.relative(path) for path in ctx.workspace.root.rglob("*") if path.is_file()
        )
        return Observation(
            ok=True, summary="FILES:\n" + ("\n".join(files) or "(empty)"), data={"files": files}
        )


def _to_csv(columns: list[str], rows: list[list[Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def file_tools() -> list[Tool[Any]]:
    return [FileRead(), FileWriteCsv(), FileList()]
