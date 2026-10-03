from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompletionRequest(BaseModel):
    messages: list[ChatMessage]
    json_mode: bool = True
    temperature: float
    max_tokens: int


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Completion(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage
    cached: bool = False


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, request: CompletionRequest) -> Completion: ...


class ChatModel(Protocol):
    """What the agent depends on: any component that turns a request into a completion."""

    async def complete(self, request: CompletionRequest) -> Completion: ...


class UsageSink(Protocol):
    """Receives token usage per call (the runtime uses it to enforce run budgets)."""

    def record(self, completion: Completion) -> None: ...
