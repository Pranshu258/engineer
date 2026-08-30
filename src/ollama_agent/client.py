"""Minimal streaming Ollama HTTP client using only the standard library."""

from __future__ import annotations

import json
import ipaddress
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


class OllamaError(RuntimeError):
    """An actionable Ollama API or network error."""


class OllamaClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        if "://" not in base_url:
            base_url = f"http://{base_url}"
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Ollama endpoint must be an HTTP(S) URL with a host")
        hostname = parsed.hostname
        try:
            is_loopback = hostname == "localhost" or (
                hostname is not None and ipaddress.ip_address(hostname).is_loopback
            )
        except ValueError:
            is_loopback = False
        if not is_loopback:
            raise ValueError("Ollama endpoint must use localhost or a loopback IP address")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        on_text: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Stream one chat turn and return the fully assembled assistant message."""
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "tools": tools,
                "stream": True,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        calls = _ToolCallAssembler()
        saw_chunk = False
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    saw_chunk = True
                    chunk = self._parse_chunk(raw_line)
                    if isinstance(chunk.get("error"), str):
                        raise OllamaError(f"Ollama API error: {chunk['error']}")
                    message = chunk.get("message")
                    if message is None and chunk.get("done") is True:
                        continue
                    if not isinstance(message, dict):
                        raise OllamaError("Ollama stream chunk has no valid message.")

                    content = message.get("content")
                    if content is not None and not isinstance(content, str):
                        raise OllamaError("Ollama returned malformed message content.")
                    if content:
                        content_parts.append(content)
                        if on_text is not None:
                            on_text(content)

                    thinking = message.get("thinking")
                    if thinking is not None and not isinstance(thinking, str):
                        raise OllamaError("Ollama returned malformed thinking content.")
                    if thinking:
                        thinking_parts.append(thinking)

                    tool_calls = message.get("tool_calls")
                    if tool_calls is not None:
                        if not isinstance(tool_calls, list):
                            raise OllamaError("Ollama returned malformed tool_calls.")
                        calls.add(tool_calls)
        except urllib.error.HTTPError as exc:
            try:
                detail = self._http_error_detail(exc.read(), str(exc.reason))
            finally:
                exc.close()
            raise OllamaError(
                f"Ollama returned HTTP {exc.code} for model {model!r}: {detail}"
            ) from exc
        except OllamaError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(
                f"Could not reach Ollama at {self.base_url}: {exc}. "
                "Start Ollama with `ollama serve` and verify the configured endpoint."
            ) from exc

        if not saw_chunk:
            raise OllamaError("Ollama returned an empty streaming response.")

        message: dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts),
        }
        thinking = "".join(thinking_parts)
        if thinking:
            message["thinking"] = thinking
        tool_calls = calls.finish()
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message

    @staticmethod
    def _parse_chunk(raw_line: bytes) -> dict[str, Any]:
        try:
            chunk = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OllamaError("Ollama returned malformed streaming JSON.") from exc
        if not isinstance(chunk, dict):
            raise OllamaError("Ollama returned a non-object stream chunk.")
        return chunk

    @staticmethod
    def _http_error_detail(raw: bytes, fallback: str) -> str:
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            text = raw.decode("utf-8", errors="replace").strip()
            return text or fallback
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            return body["error"]
        return repr(body)


class _ToolCallAssembler:
    """Assemble Ollama's streamed function-indexed tool-call chunks."""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, Any]] = {}
        self._next_index = 0

    def add(self, streamed_calls: list[Any]) -> None:
        for raw_call in streamed_calls:
            if not isinstance(raw_call, dict):
                index = self._allocate_index()
                self._calls[index] = raw_call
                continue
            function = raw_call.get("function")
            if not isinstance(function, dict):
                index = self._allocate_index()
                self._calls[index] = dict(raw_call)
                continue

            raw_index = function.get("index")
            if isinstance(raw_index, int) and raw_index >= 0:
                index = raw_index
                self._next_index = max(self._next_index, index + 1)
            else:
                index = self._allocate_index()

            call = self._calls.setdefault(
                index,
                {"type": raw_call.get("type", "function"), "function": {"index": index}},
            )
            existing_function = call.get("function")
            if not isinstance(existing_function, dict):
                self._calls[index] = dict(raw_call)
                continue

            name = function.get("name")
            if isinstance(name, str):
                previous_name = existing_function.get("name", "")
                if not previous_name:
                    existing_function["name"] = name
                elif name != previous_name:
                    existing_function["name"] = previous_name + name

            if "arguments" in function:
                incoming = function["arguments"]
                previous = existing_function.get("arguments")
                if isinstance(previous, dict) and isinstance(incoming, dict):
                    previous.update(incoming)
                elif isinstance(previous, str) and isinstance(incoming, str):
                    existing_function["arguments"] = previous + incoming
                elif previous is None:
                    existing_function["arguments"] = incoming
                else:
                    existing_function["arguments"] = incoming

    def finish(self) -> list[Any]:
        return [self._calls[index] for index in sorted(self._calls)]

    def _allocate_index(self) -> int:
        while self._next_index in self._calls:
            self._next_index += 1
        index = self._next_index
        self._next_index += 1
        return index
