"""Chat completions over the OpenAI wire format, which Groq, Gemini and Ollama all implement.

Plain httpx instead of a vendor SDK: one small adapter covers every backend, and the error
mapping (429 vs 5xx vs 4xx) is explicit rather than buried in SDK exception types.
"""

import re
from typing import Any

import httpx

from app.core.config import LLMBackendSettings
from app.core.errors import LLMError, LLMRateLimitedError, LLMRetryableError
from app.llm.base import Completion, CompletionRequest, TokenUsage

_REASONING_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR = 500
_HTTP_CLIENT_ERROR = 400


class OpenAICompatibleProvider:
    def __init__(self, name: str, settings: LLMBackendSettings, client: httpx.AsyncClient) -> None:
        self.name = name
        self.model = settings.model
        self._settings = settings
        self._client = client
        self._url = settings.base_url.rstrip("/") + "/chat/completions"

    async def complete(self, request: CompletionRequest) -> Completion:
        response = await self._post(self._payload(request))
        body = response.json()
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRetryableError(f"{self.name}: malformed completion body") from exc
        if self._settings.strip_reasoning:
            text = _REASONING_BLOCK.sub("", text)
        usage = body.get("usage") or {}
        return Completion(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            usage=TokenUsage(
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            ),
        )

    def _payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(self._settings.extra_body)
        return payload

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key.get_secret_value()}"
        try:
            response = await self._client.post(
                self._url, json=payload, headers=headers, timeout=self._settings.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise LLMRetryableError(f"{self.name}: request timed out") from exc
        except httpx.TransportError as exc:
            raise LLMRetryableError(f"{self.name}: {type(exc).__name__}") from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == _HTTP_TOO_MANY_REQUESTS:
            retry_after = response.headers.get("retry-after")
            raise LLMRateLimitedError(
                f"{self.name}: rate limited",
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if status >= _HTTP_SERVER_ERROR:
            raise LLMRetryableError(f"{self.name}: server error {status}")
        if status >= _HTTP_CLIENT_ERROR:
            # Bad key, unknown model, invalid request: retrying the same backend won't help.
            raise LLMError(f"{self.name}: request rejected ({status}): {response.text[:300]}")
