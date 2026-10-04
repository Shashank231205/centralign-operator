import pytest
from pydantic import BaseModel

from app.core.config import LLMBackendSettings, LLMSettings
from app.core.errors import LLMResponseInvalidError
from app.llm.base import Completion, CompletionRequest, TokenUsage
from app.llm.structured import StructuredLLM, extract_json

SETTINGS = LLMSettings(
    backends={"fake": LLMBackendSettings(base_url="http://fake", model="fake")},
    providers=["fake"],
    max_repair_attempts=1,
)


class Answer(BaseModel):
    city: str


class ScriptedModel:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        return Completion(
            text=self.replies.pop(0),
            provider="fake",
            model="fake",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        )


class Usage:
    def __init__(self) -> None:
        self.calls = 0

    def record(self, completion: Completion) -> None:
        self.calls += 1


async def test_valid_json_is_parsed_even_inside_prose() -> None:
    model = ScriptedModel(['Sure! {"city": "Bengaluru"} hope that helps'])
    usage = Usage()
    answer = await StructuredLLM(model, SETTINGS).generate(
        system="s", user="u", schema=Answer, prompt_version="t.v1", usage=usage
    )
    assert answer.city == "Bengaluru"
    assert usage.calls == 1
    assert model.requests[0].json_mode


async def test_invalid_reply_is_repaired_with_validation_feedback() -> None:
    model = ScriptedModel(['{"town": "x"}', '{"city": "Pune"}'])
    answer = await StructuredLLM(model, SETTINGS).generate(
        system="s", user="u", schema=Answer, prompt_version="t.v1"
    )
    assert answer.city == "Pune"
    repair_turn = model.requests[1].messages[-1].content
    assert "city" in repair_turn and "invalid" in repair_turn


async def test_gives_up_after_repair_budget() -> None:
    model = ScriptedModel(["not json", "still not json"])
    with pytest.raises(LLMResponseInvalidError):
        await StructuredLLM(model, SETTINGS).generate(
            system="s", user="u", schema=Answer, prompt_version="t.v1"
        )


def test_extract_json_rejects_text_without_object() -> None:
    with pytest.raises(ValueError, match="No JSON"):
        extract_json("no braces here")
