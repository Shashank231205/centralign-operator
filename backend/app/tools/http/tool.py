"""Generic HTTP tool scoped to company API systems.

The model names a *system* and a path, never a host, so it cannot reach arbitrary URLs.
Authentication is injected from the credential store and never appears in prompts or logs.
"""

import json
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field

from app.agent.understanding.context import SystemInfo
from app.core.errors import RetryableToolError, ToolInputError
from app.domain.enums import FailureKind, RiskLevel, ToolKind
from app.domain.models import Assessment, Observation
from app.tools.base import Tool, ToolContext, ensure_writable, truncate

_METHOD_RISK = {
    "GET": RiskLevel.READ,
    "POST": RiskLevel.WRITE,
    "PUT": RiskLevel.WRITE,
    "PATCH": RiskLevel.WRITE,
    "DELETE": RiskLevel.IRREVERSIBLE,
}
_HTTP_SERVER_ERROR = 500
_HTTP_CLIENT_ERROR = 400


class HttpArgs(BaseModel):
    system: str = Field(description="Name of an http_api system from the company profile")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str = Field(description="Path relative to the system base URL, e.g. /invoices")
    params: dict[str, str] = Field(default_factory=dict, description="Query parameters")
    body: dict[str, Any] | None = Field(default=None, description="JSON body for writes")


class HttpRequest(Tool[HttpArgs]):
    name: ClassVar[str] = "http_request"
    description: ClassVar[str] = "Call a company API system (see its documented endpoints)."
    kind: ClassVar[ToolKind] = ToolKind.HTTP
    args_model = HttpArgs

    async def assess(self, args: HttpArgs, ctx: ToolContext) -> Assessment:
        system = _api_system(args.system, ctx)
        risk = _METHOD_RISK[args.method]
        ensure_writable(ctx, system.name, risk)
        return Assessment(
            risk=risk,
            system=system.name,
            payload={**(args.body or {}), "_method": args.method, "_action": args.path},
            description=f"{args.method} {system.name}{args.path}",
        )

    async def run(self, args: HttpArgs, ctx: ToolContext) -> Observation:
        system = _api_system(args.system, ctx)
        url = f"{(system.base_url or '').rstrip('/')}/{args.path.lstrip('/')}"
        await ctx.throttle_host(system.host or "")
        breaker = ctx.breakers.get(f"host:{system.host}")
        try:
            response = await ctx.http.request(
                args.method, url, params=args.params, json=args.body, headers=_auth(system, ctx)
            )
        except httpx.HTTPError as exc:
            breaker.record_failure()
            raise RetryableToolError(f"{system.name} unreachable: {type(exc).__name__}") from exc
        if response.status_code >= _HTTP_SERVER_ERROR:
            breaker.record_failure()
        else:
            breaker.record_success()
        return _observation(args, response, ctx.observation_char_budget)


def _api_system(name: str, ctx: ToolContext) -> SystemInfo:
    system = ctx.company.systems.get(name)
    if system is None or system.kind != "http_api":
        apis = [item.name for item in ctx.company.systems.values() if item.kind == "http_api"]
        raise ToolInputError(f"'{name}' is not an API system. Available: {apis}")
    return system


def _auth(system: SystemInfo, ctx: ToolContext) -> dict[str, str]:
    if system.auth == "bearer" and system.credential:
        token = ctx.credentials.get(system.credential).password.get_secret_value()
        return {"Authorization": f"Bearer {token}"}
    return {}


def _observation(args: HttpArgs, response: httpx.Response, budget: int) -> Observation:
    status = response.status_code
    try:
        payload: Any = response.json()
        text = json.dumps(payload, indent=None)
    except ValueError:
        payload, text = None, response.text
    ok = status < _HTTP_CLIENT_ERROR
    failure = None
    if status >= _HTTP_SERVER_ERROR:
        failure = FailureKind.TRANSIENT
    elif not ok:
        failure = FailureKind.STRUCTURAL
    return Observation(
        ok=ok,
        summary=f"HTTP {status} {args.method} {args.system}{args.path} {args.params}\n"
        f"{truncate(text, budget)}",
        data={"status": status, "json": payload},
        error=None if ok else f"HTTP {status}",
        failure_kind=failure,
    )


def http_tools() -> list[Tool[Any]]:
    return [HttpRequest()]
