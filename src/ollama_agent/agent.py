"""Agent loop for native Ollama chat tool calling."""

from __future__ import annotations

from typing import Any, Callable

from .client import OllamaClient
from .tools import TOOL_DEFINITIONS, ToolError, WorkspaceTools, parse_tool_arguments


class AgentError(RuntimeError):
    """A clear agent-loop failure."""


class MaxStepsError(AgentError):
    """The model did not finish within the configured step limit."""


SYSTEM_PROMPT = """You are a local coding assistant. Work only in the configured workspace.
Use the supplied native tools when needed; never emit JSON actions in text. File writes and
edits happen automatically and their diffs are shown to the user. Every shell command and
every Git mutation requires the user's interactive approval. Never claim an action succeeded
unless its tool result says it succeeded. Explain the final result concisely."""


class Agent:
    def __init__(
        self,
        client: OllamaClient,
        tools: WorkspaceTools,
        model: str,
        max_steps: int = 8,
        stream_text: Callable[[str], None] | None = None,
        report_error: Callable[[str], None] | None = None,
        report_progress: Callable[[str], None] | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.client = client
        self.tools = tools
        self.model = model
        self.max_steps = max_steps
        self.stream_text = stream_text
        self.report_error = report_error
        self.report_progress = report_progress
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def clear(self) -> None:
        self.messages = self.messages[:1]

    def run(self, prompt: str) -> str:
        if not prompt.strip():
            raise AgentError("Prompt cannot be empty.")
        self.messages.append({"role": "user", "content": prompt})

        for _ in range(self.max_steps):
            message = self.client.chat(
                self.model,
                self.messages,
                TOOL_DEFINITIONS,
                on_text=self.stream_text,
            )
            content = message.get("content", "")
            if not isinstance(content, str):
                raise AgentError("Ollama returned malformed assistant content.")
            tool_calls = message.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                raise AgentError("Ollama returned malformed tool_calls.")

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": content,
            }
            if isinstance(message.get("thinking"), str) and message["thinking"]:
                assistant_message["thinking"] = message["thinking"]
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            self.messages.append(assistant_message)

            if not tool_calls:
                if content.strip():
                    return content
                raise AgentError("Ollama returned neither text nor tool calls.")

            for call in tool_calls:
                name = self._tool_name(call)
                if self.report_progress is not None:
                    self.report_progress(f"Running {name}")
                try:
                    if not isinstance(call, dict) or not isinstance(
                        call.get("function"), dict
                    ):
                        raise ToolError("malformed tool call")
                    arguments = parse_tool_arguments(call["function"].get("arguments"))
                    result = self.tools.execute(name, arguments)
                except ToolError as exc:
                    result = f"Tool error: {exc}"
                    if self.report_error is not None:
                        self.report_error(f"{name}: {exc}")
                    if self.report_progress is not None:
                        self.report_progress(f"Failed {name}")
                else:
                    if self.report_progress is not None:
                        self.report_progress(f"Completed {name}")
                self.messages.append(
                    {"role": "tool", "tool_name": name, "content": result}
                )

        raise MaxStepsError(
            f"Agent stopped after {self.max_steps} model steps without a final response."
        )

    @staticmethod
    def _tool_name(call: Any) -> str:
        if not isinstance(call, dict):
            return "<malformed>"
        function = call.get("function")
        if not isinstance(function, dict):
            return "<malformed>"
        name = function.get("name")
        return name if isinstance(name, str) and name else "<malformed>"
