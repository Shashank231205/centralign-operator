"""Control-flow tools. The runtime handles these itself (pause, finish, replan); they live in
the registry so the model sees one uniform tool catalogue."""

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.domain.enums import ToolKind
from app.domain.models import Observation
from app.tools.base import Tool, ToolContext

ASK_HUMAN = "ask_human"
FINISH = "finish"
REPLAN = "replan"


class AskArgs(BaseModel):
    question: str = Field(description="One clear question for the requester")


class FinishArgs(BaseModel):
    summary: str = Field(description="What was done and the key results, for the requester")


class ReplanArgs(BaseModel):
    reason: str = Field(description="Why the current plan no longer fits what you observed")


class _ControlTool[ArgsT: BaseModel](Tool[ArgsT]):
    kind: ClassVar[ToolKind] = ToolKind.CONTROL

    async def run(self, args: ArgsT, ctx: ToolContext) -> Observation:  # noqa: ARG002
        raise RuntimeError(f"{self.name} is handled by the runtime, not executed")


class AskHuman(_ControlTool[AskArgs]):
    name: ClassVar[str] = ASK_HUMAN
    description: ClassVar[str] = (
        "Pause and ask the requester when information is missing or ambiguous. Never guess."
    )
    args_model = AskArgs


class Finish(_ControlTool[FinishArgs]):
    name: ClassVar[str] = FINISH
    description: ClassVar[str] = (
        "Declare the work done. Success criteria are then verified independently."
    )
    args_model = FinishArgs


class Replan(_ControlTool[ReplanArgs]):
    name: ClassVar[str] = REPLAN
    description: ClassVar[str] = "Request a new plan when the current one cannot work."
    args_model = ReplanArgs


def control_tools() -> list[Tool[Any]]:
    return [AskHuman(), Finish(), Replan()]
