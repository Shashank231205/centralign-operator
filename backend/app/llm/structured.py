"""Typed JSON output from any backend.

Native tool-calling support differs across free backends, so the contract is enforced here:
the JSON schema goes in the prompt, the reply is validated with Pydantic, and on failure the
validation errors are sent back for a bounded number of repair attempts.
"""

import json
import logging
import re

from pydantic import BaseModel, ValidationError

from app.core.config import LLMSettings
from app.core.errors import LLMResponseInvalidError
from app.llm.base import ChatMessage, ChatModel, Completion, CompletionRequest, UsageSink
from app.llm.cache import LLMResponseCache

logger = logging.getLogger(__name__)

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class StructuredLLM:
    def __init__(
        self,
        model: ChatModel,
        settings: LLMSettings,
        cache: LLMResponseCache | None = None,
        model_fingerprint: str = "",
    ) -> None:
        self._model = model
        self._settings = settings
        self._cache = cache
        self._fingerprint = model_fingerprint

    async def generate[SchemaT: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[SchemaT],
        prompt_version: str,
        usage: UsageSink | None = None,
        cacheable: bool = False,
    ) -> SchemaT:
        messages = [
            ChatMessage(role="system", content=f"{system}\n\n{_schema_instructions(schema)}"),
            ChatMessage(role="user", content=user),
        ]
        cache_key = self._cache_key(messages, prompt_version) if cacheable else None
        if cache_key and self._cache and (hit := await self._cache.get(cache_key)):
            try:
                return schema.model_validate_json(hit)
            except ValidationError:
                logger.warning("discarding invalid cached llm response")
        result, raw = await self._generate_with_repair(messages, schema, usage)
        if cache_key and self._cache:
            await self._cache.put(cache_key, raw)
        return result

    async def _generate_with_repair[SchemaT: BaseModel](
        self, messages: list[ChatMessage], schema: type[SchemaT], usage: UsageSink | None
    ) -> tuple[SchemaT, str]:
        last_error = ""
        for _ in range(self._settings.max_repair_attempts + 1):
            completion = await self._model.complete(self._request(messages))
            if usage:
                usage.record(completion)
            try:
                raw = extract_json(completion.text)
                return schema.model_validate_json(raw), raw
            except (ValueError, ValidationError) as exc:
                last_error = _describe(exc)
                messages = [*messages, *_repair_turn(completion, last_error)]
        raise LLMResponseInvalidError(
            f"Model did not return valid {schema.__name__} JSON", details={"error": last_error}
        )

    def _request(self, messages: list[ChatMessage]) -> CompletionRequest:
        return CompletionRequest(
            messages=messages,
            json_mode=True,
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_output_tokens,
        )

    def _cache_key(self, messages: list[ChatMessage], prompt_version: str) -> str:
        return LLMResponseCache.key(self._fingerprint, prompt_version, self._request(messages))


def extract_json(text: str) -> str:
    """Return the outermost JSON object in ``text`` (models sometimes wrap it in prose/fences)."""
    match = _JSON_OBJECT.search(text)
    if not match:
        raise ValueError("No JSON object found in the reply")
    candidate = match.group(0)
    json.loads(candidate)
    return candidate


def _schema_instructions(schema: type[BaseModel]) -> str:
    return (
        "Respond with a single JSON object only, no prose and no code fences. "
        "It must validate against this JSON Schema:\n"
        f"{json.dumps(schema.model_json_schema(), separators=(',', ':'))}"
    )


def _repair_turn(completion: Completion, error: str) -> list[ChatMessage]:
    return [
        ChatMessage(role="assistant", content=completion.text),
        ChatMessage(
            role="user",
            content=f"That reply was invalid: {error}\nReturn the corrected JSON object only.",
        ),
    ]


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:8]
        )
    return str(exc)
