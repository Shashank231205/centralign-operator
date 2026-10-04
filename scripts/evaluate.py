"""Run the evaluation scenarios against a live deployment through the public API.

Usage:  uv run python scripts/evaluate.py [--only invoice_entry,overdue_report]
Reads OPERATOR_API_URL and OPERATOR_API_KEY from the environment or .env.
Writes a JSON report to var/evals/ and exits non-zero if any scenario fails.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import dotenv_values

SCENARIOS_FILE = Path(__file__).resolve().parent.parent / "evals" / "scenarios.yaml"
REPORT_DIR = Path("var/evals")
TERMINAL = {"completed", "failed", "cancelled"}


@dataclass
class Outcome:
    scenario: str
    passed: bool
    status: str
    seconds: float
    checks: dict[str, bool] = field(default_factory=dict)
    run_id: str = ""
    summary: str | None = None
    counters: dict[str, Any] = field(default_factory=dict)


def _config() -> tuple[str, str]:
    values = {**dotenv_values(".env"), **os.environ}
    url, key = values.get("OPERATOR_API_URL"), values.get("OPERATOR_API_KEY")
    if not url or not key:
        sys.exit("OPERATOR_API_URL and OPERATOR_API_KEY must be set")
    return url.rstrip("/"), key


async def run_scenario(
    client: httpx.AsyncClient, scenario: dict[str, Any], poll_seconds: float, timeout_seconds: float
) -> Outcome:
    started = time.monotonic()
    human = scenario.get("human", {})
    response = await client.post(
        "/tasks",
        json={"request": scenario["request"]},
        headers={"Idempotency-Key": f"eval-{scenario['id']}-{uuid.uuid4()}"},
    )
    response.raise_for_status()
    run_id = response.json()["run_id"]
    asked = False
    while time.monotonic() - started < timeout_seconds:
        run = (await client.get(f"/runs/{run_id}")).raise_for_status().json()
        if run["status"] in TERMINAL:
            break
        if run["status"] == "awaiting_input":
            asked = True
            answer = human.get("answer", "Please proceed with the most reasonable option.")
            await client.post(f"/runs/{run_id}/input", json={"answer": answer})
        elif run["status"] == "awaiting_approval" and run["pending_approval"]:
            decision = human.get("approval", "reject")
            await client.post(
                f"/approvals/{run['pending_approval']['approval_id']}",
                json={"decision": decision, "comment": "evaluation harness"},
            )
        await asyncio.sleep(poll_seconds)
    steps = (await client.get(f"/runs/{run_id}/steps")).raise_for_status().json()
    checks = _checks(scenario["expect"], run, steps, asked)
    return Outcome(
        scenario=scenario["id"],
        passed=all(checks.values()),
        status=run["status"],
        seconds=round(time.monotonic() - started, 1),
        checks=checks,
        run_id=run_id,
        summary=run.get("summary"),
        counters=run.get("counters", {}),
    )


def _checks(
    expect: dict[str, Any], run: dict[str, Any], steps: list[dict[str, Any]], asked: bool
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    if "status" in expect:
        checks["status"] = run["status"] == expect["status"]
    if "status_in" in expect:
        checks["status_in"] = run["status"] in expect["status_in"]
    for key in expect.get("key_results_include", []):
        checks[f"key_result:{key}"] = key in run.get("key_results", {}) or key in run["facts"]
    if expect.get("asked_question"):
        checks["asked_question"] = asked
    if expect.get("no_write_to_status_paid"):
        checks["no_paid_writes"] = not any(
            "paid" in json.dumps(step["action"].get("args", {})).lower()
            and step["tool"] in {"browser_click", "http_request"}
            and step["ok"]
            for step in steps
        )
    return checks


async def run_all(
    scenarios: list[dict[str, Any]], poll_seconds: float, timeout_seconds: float
) -> list[Outcome]:
    url, key = _config()
    async with httpx.AsyncClient(base_url=url, headers={"X-API-Key": key}, timeout=30) as client:
        return [
            await run_scenario(client, scenario, poll_seconds, timeout_seconds)
            for scenario in scenarios
        ]


def write_report(outcomes: list[Outcome]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"report-{int(time.time())}.json"
    report.write_text(json.dumps([asdict(o) for o in outcomes], indent=2), encoding="utf-8")
    for outcome in outcomes:
        mark = "PASS" if outcome.passed else "FAIL"
        sys.stdout.write(
            f"{mark} {outcome.scenario:<26} {outcome.status:<10} {outcome.seconds:>7}s "
            f"steps={outcome.counters.get('steps')} checks={outcome.checks}\n"
        )
    sys.stdout.write(f"report: {report}\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="comma-separated scenario ids")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=float, default=1200.0)
    arguments = parser.parse_args()
    only = set(arguments.only.split(",")) if arguments.only else None
    all_scenarios = yaml.safe_load(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]
    selected = [s for s in all_scenarios if only is None or s["id"] in only]
    results = asyncio.run(run_all(selected, arguments.poll_seconds, arguments.timeout_seconds))
    write_report(results)
    sys.exit(0 if all(outcome.passed for outcome in results) else 1)
