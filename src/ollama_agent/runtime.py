"""Profile-aware local agent construction and synchronous delegation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .agent import Agent, AgentError
from .client import OllamaClient, OllamaError
from .profiles import AgentProfile, ResourceError, load_profile, load_skill
from .tools import ToolError, WorkspaceTools, get_tool_definitions


@dataclass(frozen=True, slots=True)
class RoleModels:
    engineer: str
    implementer: str
    reviewer: str


class AgentRuntime:
    def __init__(
        self,
        client: OllamaClient,
        tools: WorkspaceTools,
        models: RoleModels,
        stream_text: Callable[[str], None] | None = None,
        report_error: Callable[[str], None] | None = None,
        report_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.tools = tools
        self.models = models
        self.stream_text = stream_text
        self.report_error = report_error
        self.report_progress = report_progress

    def create_agent(self, name: str) -> Agent:
        return self._create_agent(name, depth=0)

    def _create_agent(self, name: str, depth: int) -> Agent:
        profile = load_profile(name)
        return Agent(
            self.client,
            self.tools,
            self._model_for(name),
            stream_text=self.stream_text,
            report_error=self.report_error,
            report_progress=self.report_progress,
            system_prompt=profile.system_prompt,
            tool_definitions=get_tool_definitions(profile.tool_names),
            tool_executor=lambda tool_name, arguments: self._execute_tool(
                profile, depth, tool_name, arguments
            ),
        )

    def _model_for(self, name: str) -> str:
        if name == "engineer":
            return self.models.engineer
        if name == "scope-disciplined-swe":
            return self.models.implementer
        if name == "adversarial-pr-reviewer":
            return self.models.reviewer
        raise ResourceError(f"Unknown agent profile {name!r}")

    def _execute_tool(
        self,
        profile: AgentProfile,
        depth: int,
        name: str,
        arguments: dict[str, Any],
    ) -> str:
        if name == "delegate_agent" and depth >= 1:
            raise ToolError("delegation depth limit exceeded")
        if name not in profile.tool_names:
            raise ToolError(f"tool {name!r} is not permitted for agent {profile.name!r}")
        if name == "load_skill":
            skill_name = arguments.get("skill")
            if not isinstance(skill_name, str) or not skill_name:
                raise ToolError("skill must be a non-empty string")
            try:
                return load_skill(skill_name).instructions
            except ResourceError as exc:
                raise ToolError(str(exc)) from exc
        if name == "delegate_agent":
            return self._delegate(profile, depth, arguments)
        return self.tools.execute(name, arguments)

    def _delegate(
        self,
        profile: AgentProfile,
        depth: int,
        arguments: dict[str, Any],
    ) -> str:
        target = arguments.get("agent")
        task = arguments.get("task")
        if not isinstance(target, str) or not target:
            raise ToolError("agent must be a non-empty string")
        if target not in profile.delegated_agents:
            allowed = ", ".join(profile.delegated_agents) or "(none)"
            raise ToolError(
                f"agent {profile.name!r} cannot delegate to {target!r}; "
                f"allowed agents: {allowed}"
            )
        if not isinstance(task, str) or not task.strip():
            raise ToolError("task must be a non-empty string")
        try:
            child = self._create_agent(target, depth=depth + 1)
            return child.run(task)
        except (AgentError, OllamaError, ResourceError) as exc:
            raise ToolError(f"delegated agent {target!r} failed: {exc}") from exc
