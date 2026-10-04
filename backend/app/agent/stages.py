"""The four reasoning stages, each one typed LLM call with its own prompt:
understand → plan (and re-plan) → decide next action → report."""

from pydantic import BaseModel, Field

from app.agent.prompts import sections
from app.agent.prompts.library import PromptLibrary
from app.agent.understanding.context import CompanyContext, Procedure
from app.core.config import AgentSettings
from app.domain.models import Goal, NextAction, Plan, RunState
from app.llm.base import UsageSink
from app.llm.structured import StructuredLLM
from app.tools.registry import ToolRegistry


class Report(BaseModel):
    summary: str
    key_results: dict[str, str] = Field(default_factory=dict)
    lessons: list[str] = Field(default_factory=list)


class Stages:
    def __init__(
        self,
        llm: StructuredLLM,
        prompts: PromptLibrary,
        registry: ToolRegistry,
        settings: AgentSettings,
    ) -> None:
        self._llm = llm
        self._prompts = prompts
        self._registry = registry
        self._settings = settings

    async def understand(
        self,
        state: RunState,
        company: CompanyContext,
        procedures: list[Procedure],
        lessons: list[str],
        usage: UsageSink,
    ) -> Goal:
        prompt = self._prompts.render(
            "understand",
            **sections.base_variables(company),
            request=state.request,
            human_answers=sections.bullet(state.human_inputs),
            systems=sections.systems(company),
            procedures=sections.procedures(procedures),
            lessons=sections.bullet(lessons),
        )
        return await self._llm.generate(
            system=prompt.system,
            user=prompt.user,
            schema=Goal,
            prompt_version=prompt.version,
            usage=usage,
            cacheable=True,
            max_tokens=self._settings.understand_max_tokens,
        )

    async def plan(
        self,
        state: RunState,
        company: CompanyContext,
        procedures: list[Procedure],
        lessons: list[str],
        usage: UsageSink,
    ) -> Plan:
        assert state.goal is not None
        prompt = self._prompts.render(
            "plan",
            **sections.base_variables(company),
            goal=state.goal.model_dump_json(),
            procedures=sections.procedures(procedures),
            systems=sections.systems(company),
            tools=self._registry.catalogue,
            facts=sections.facts(state.facts),
            lessons=sections.bullet(lessons),
            replan_reason=state.replan_reason or "",
            previous_plan=sections.plan(state.plan),
            history=sections.history(state.history, self._settings.history_window * 2),
        )
        plan = await self._llm.generate(
            system=prompt.system,
            user=prompt.user,
            schema=Plan,
            prompt_version=prompt.version,
            usage=usage,
            cacheable=state.replan_reason is None,
            max_tokens=self._settings.plan_max_tokens,
        )
        plan.version = (state.plan.version + 1) if state.plan else 1
        return plan

    async def decide(
        self, state: RunState, company: CompanyContext, lessons: list[str], usage: UsageSink
    ) -> NextAction:
        assert state.goal is not None and state.plan is not None
        prompt = self._prompts.render(
            "act",
            **sections.base_variables(company),
            goal=state.goal.model_dump_json(),
            plan=sections.plan(state.plan),
            criteria=sections.criteria(state.plan.success_criteria),
            required_facts=sections.required_facts(state),
            facts=sections.facts(state.facts),
            human_answers=sections.bullet(state.human_inputs),
            feedback=sections.bullet(state.feedback),
            lessons=sections.bullet(lessons),
            systems=sections.systems(company),
            policies=sections.policies(company),
            tools=self._registry.catalogue,
            history=sections.history(state.history, self._settings.history_window),
            observation=sections.latest_observation(state.history),
        )
        return await self._llm.generate(
            system=prompt.system,
            user=prompt.user,
            schema=NextAction,
            prompt_version=prompt.version,
            usage=usage,
            max_tokens=self._settings.decide_max_tokens,
        )

    async def report(self, state: RunState, company: CompanyContext, usage: UsageSink) -> Report:
        prompt = self._prompts.render(
            "report",
            **sections.base_variables(company),
            request=state.request,
            status=state.status.value,
            goal=state.goal.model_dump_json() if state.goal else sections.NONE,
            facts=sections.facts(state.facts),
            verification=sections.verification(state.verification),
            history=sections.history(state.history, len(state.history)),
            finish_note=state.summary or sections.NONE,
        )
        return await self._llm.generate(
            system=prompt.system,
            user=prompt.user,
            schema=Report,
            prompt_version=prompt.version,
            usage=usage,
            max_tokens=self._settings.report_max_tokens,
        )
