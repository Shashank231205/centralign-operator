"""Evidence on a local volume. The interface (EvidenceStore) also fits an S3-compatible bucket;
only this adapter would change."""

import asyncio
import re
import time
from pathlib import Path
from uuid import UUID

from app.domain.enums import EvidenceKind
from app.domain.models import ArtifactRef

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class LocalEvidenceStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    async def save(
        self, run_id: UUID, name: str, content: bytes, kind: EvidenceKind, description: str
    ) -> ArtifactRef:
        directory = self._root / str(run_id)
        # Time-ordered unique names keep every screenshot of a run, in sequence.
        path = directory / f"{time.time_ns()}-{_UNSAFE.sub('_', name)}"
        await asyncio.to_thread(_write, path, content)
        return ArtifactRef(
            kind=kind, path=path.relative_to(self._root).as_posix(), description=description
        )

    def open(self, relative: str) -> Path:
        path = (self._root / relative).resolve()
        if not path.is_relative_to(self._root) or not path.is_file():
            raise FileNotFoundError(relative)
        return path


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
