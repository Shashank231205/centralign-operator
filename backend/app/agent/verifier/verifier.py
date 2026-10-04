"""Independent outcome verification.

The verifier never trusts what the executor saw ("the form said saved"). It re-reads the target
system fresh — through the read API or the workspace file — and checks every success criterion.
The same check runs before writes as an idempotency guard: if the outcome already holds, the
write is skipped.
"""

import asyncio
import csv
import io
from typing import Any

from app.core.config import AgentSettings
from app.core.resilience import RetryPolicy
from app.domain.enums import FailureKind
from app.domain.models import CriterionResult, FileCheck, HttpJsonCheck, SuccessCriterion
from app.domain.values import MissingFactError, resolve, values_match
from app.tools.base import ToolContext
from app.tools.http.tool import HttpArgs, HttpRequest

_ITEM_LIST_KEYS = ("items", "data", "results")


class Verifier:
    def __init__(self, settings: AgentSettings, retry: RetryPolicy) -> None:
        self._date_formats = settings.date_formats
        self._retry = retry
        self._http = HttpRequest()

    async def verify(
        self, criteria: list[SuccessCriterion], facts: dict[str, str], ctx: ToolContext
    ) -> list[CriterionResult]:
        return [await self._check(criterion, facts, ctx) for criterion in criteria]

    async def already_satisfied(
        self, criteria: list[SuccessCriterion], facts: dict[str, str], ctx: ToolContext
    ) -> bool:
        """Idempotency guard: True only if every criterion is resolvable *and* passes now."""
        if not criteria:
            return False
        results = await self.verify(criteria, facts, ctx)
        return all(result.passed for result in results)

    async def _check(
        self, criterion: SuccessCriterion, facts: dict[str, str], ctx: ToolContext
    ) -> CriterionResult:
        try:
            if isinstance(criterion.check, HttpJsonCheck):
                passed, detail, observed = await self._http_check(criterion.check, facts, ctx)
            else:
                passed, detail, observed = await self._file_check(criterion.check, facts, ctx)
        except MissingFactError as exc:
            passed, detail, observed = False, f"Fact '{exc.args[0]}' was never discovered", {}
        except VerificationReadError as exc:
            passed, detail, observed = False, str(exc), {}
        return CriterionResult(
            criterion_id=criterion.id,
            description=criterion.description,
            passed=passed,
            detail=detail,
            observed=observed,
        )

    async def _http_check(
        self, check: HttpJsonCheck, facts: dict[str, str], ctx: ToolContext
    ) -> tuple[bool, str, dict[str, Any]]:
        params = {key: resolve(value, facts) for key, value in check.params.items()}
        expected = {key: resolve(value, facts) for key, value in check.match.items()}
        items = await self._fetch_items(check.system, check.path, params, ctx)
        matching = [item for item in items if self._matches(item, expected)]
        observed = {"returned": len(items), "matching": len(matching), "items": matching[:5]}
        if check.expected_count is None:
            passed = len(matching) >= 1
            wanted = "at least 1"
        else:
            passed = len(matching) == check.expected_count
            wanted = str(check.expected_count)
        detail = f"{len(matching)} matching record(s) (expected {wanted}) for {expected}"
        return passed, detail, observed

    async def _file_check(
        self, check: FileCheck, facts: dict[str, str], ctx: ToolContext
    ) -> tuple[bool, str, dict[str, Any]]:
        path = ctx.workspace.resolve(resolve(check.path, facts))
        if not await asyncio.to_thread(path.is_file):
            return False, f"File {check.path} does not exist", {}
        rows = list(csv.DictReader(io.StringIO(await asyncio.to_thread(path.read_text))))
        columns = set(rows[0].keys()) if rows else set()
        missing = [column for column in check.required_columns if column not in columns]
        if missing:
            return False, f"Missing columns {missing}", {"columns": sorted(columns)}
        if not (check.compare_to and check.key_column):
            return True, f"File has {len(rows)} rows and the required columns", {"rows": len(rows)}
        source = check.compare_to
        params = {key: resolve(value, facts) for key, value in source.params.items()}
        items = await self._fetch_items(source.system, source.path, params, ctx)
        expected_keys = {str(item.get(source.key_field)) for item in items}
        file_keys = {row[check.key_column] for row in rows}
        observed = {
            "file_keys": sorted(file_keys),
            "source_keys": sorted(expected_keys),
            "missing": sorted(expected_keys - file_keys),
            "unexpected": sorted(file_keys - expected_keys),
        }
        passed = file_keys == expected_keys
        detail = f"File keys {'match' if passed else 'differ from'} {source.system}{source.path}"
        return passed, detail, observed

    async def _fetch_items(
        self, system: str, path: str, params: dict[str, str], ctx: ToolContext
    ) -> list[dict[str, Any]]:
        args = HttpArgs(system=system, path=path, params=params)
        for attempt in range(1, self._retry.max_attempts + 1):
            observation = await self._http.run(args, ctx)
            if observation.ok:
                return _items(observation.data.get("json"))
            if observation.failure_kind is not FailureKind.TRANSIENT:
                break
            if attempt < self._retry.max_attempts:
                await asyncio.sleep(self._retry.base_delay_seconds * attempt)
        raise VerificationReadError(f"Could not read {system}{path}: {observation.error}")

    def _matches(self, item: dict[str, Any], expected: dict[str, str]) -> bool:
        return all(
            field in item and values_match(value, item[field], self._date_formats)
            for field, value in expected.items()
        )


class VerificationReadError(Exception):
    """The target system could not be read; the criterion cannot be confirmed."""


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in _ITEM_LIST_KEYS:
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        return [payload]
    return []
