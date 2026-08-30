"""Agent loop for native Ollama chat tool calling."""

from __future__ import annotations

from typing import Any, Callable

from .client import OllamaClient
from .tools import TOOL_DEFINITIONS, ToolError, WorkspaceTools, parse_tool_arguments


class AgentError(RuntimeError):
    """A clear agent-loop failure."""


SYSTEM_PROMPT = """You are a local coding assistant. Work only in the configured workspace.
Use the supplied native tools when needed; never emit JSON actions in text. File writes and
edits happen automatically and their diffs are shown to the user. Every shell command and
every Git commit or branch change requires the user's interactive approval. Use git_stage
before git_commit; do not try to run Git through the shell tool. Never claim an action
succeeded unless its tool result says it succeeded. Explain the final result concisely."""

MAX_CONSECUTIVE_NO_PROGRESS = 3
_NO_PROGRESS_RECOVERY_PROMPT = """The previous model turn made no observable progress.
Continue now with visible final content or a valid native tool call. Do not return only hidden
thinking."""


class Agent:
    def __init__(
        self,
        client: OllamaClient,
        tools: WorkspaceTools,
        model: str,
        stream_text: Callable[[str], None] | None = None,
        report_error: Callable[[str], None] | None = None,
        report_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.tools = tools
        self.model = model
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
        turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": prompt})
        consecutive_no_progress = 0

        try:
            while True:
                request_messages = self.messages
                if consecutive_no_progress:
                    request_messages = [
                        *self.messages,
                        {"role": "user", "content": _NO_PROGRESS_RECOVERY_PROMPT},
                    ]
                message = self.client.chat(
                    self.model,
                    request_messages,
                    TOOL_DEFINITIONS,
                    on_text=self.stream_text,
                )

                if not isinstance(message, dict):
                    raise AgentError("Ollama returned a malformed assistant message.")
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise AgentError("Ollama returned malformed assistant content.")
                raw_tool_calls = message.get("tool_calls")
                if raw_tool_calls is None:
                    tool_calls = []
                elif isinstance(raw_tool_calls, list):
                    tool_calls = raw_tool_calls
                else:
                    raise AgentError("Ollama returned malformed tool_calls.")
                thinking = message.get("thinking")
                if thinking is not None and not isinstance(thinking, str):
                    raise AgentError("Ollama returned malformed thinking content.")

                if not content.strip() and not tool_calls:
                    consecutive_no_progress += 1
                    if consecutive_no_progress >= MAX_CONSECUTIVE_NO_PROGRESS:
                        raise AgentError(
                            "Ollama made no observable progress for "
                            f"{MAX_CONSECUTIVE_NO_PROGRESS} consecutive model turns "
                            "(empty or thinking-only responses). Retry with a clearer "
                            "prompt or use a different tool-capable model."
                        )
                    continue

                consecutive_no_progress = 0
                assistant_message: dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                }
                if thinking:
                    assistant_message["thinking"] = thinking
                if tool_calls:
                    assistant_message["tool_calls"] = tool_calls
                self.messages.append(assistant_message)

                if not tool_calls:
                    return content

                for call in tool_calls:
                    name = self._tool_name(call)
                    if self.report_progress is not None:
                        self.report_progress(f"Running {name}")
                    try:
                        if not isinstance(call, dict) or not isinstance(
                            call.get("function"), dict
                        ):
                            raise ToolError("malformed tool call")
                        arguments = parse_tool_arguments(
                            call["function"].get("arguments")
                        )
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
        except BaseException:
            del self.messages[turn_start:]
            raise

    @staticmethod
    def _tool_name(call: Any) -> str:
        if not isinstance(call, dict):
            return "<malformed>"
        function = call.get("function")
        if not isinstance(function, dict):
            return "<malformed>"
        name = function.get("name")
        return name if isinstance(name, str) and name else "<malformed>"
