"""Workspace-scoped file, shell, and Git tools exposed to the model."""

from __future__ import annotations

import difflib
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable


class ToolError(RuntimeError):
    """A safe, user-readable tool failure."""


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
    }
    if required:
        parameters["required"] = required
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


_PATH = {"type": "string", "description": "Workspace-relative path"}
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _tool(
        "list_files",
        "List files and directories under a workspace directory.",
        {"path": {**_PATH, "description": "Directory; defaults to ."}},
    ),
    _tool("read_file", "Read a UTF-8 workspace file.", {"path": _PATH}, ["path"]),
    _tool(
        "search_text",
        "Recursively search UTF-8 workspace files for literal text.",
        {
            "query": {"type": "string"},
            "path": {**_PATH, "description": "File or directory; defaults to ."},
        },
        ["query"],
    ),
    _tool(
        "write_file",
        "Write a UTF-8 workspace file. The user immediately sees a bounded diff.",
        {"path": _PATH, "content": {"type": "string"}},
        ["path", "content"],
    ),
    _tool(
        "edit_file",
        "Replace one exact text occurrence in a workspace file and show its diff.",
        {
            "path": _PATH,
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path", "old_text", "new_text"],
    ),
    _tool(
        "run_shell",
        "Run a command from the workspace after explicit user approval.",
        {"command": {"type": "string"}},
        ["command"],
    ),
    _tool("git_status", "Show read-only Git status."),
    _tool(
        "git_diff",
        "Show a read-only Git diff.",
        {"path": _PATH, "staged": {"type": "boolean"}},
    ),
    _tool(
        "git_log",
        "Show recent Git commits.",
        {"max_count": {"type": "integer", "minimum": 1, "maximum": 100}},
    ),
    _tool(
        "git_show",
        "Show a revision without modifying Git state.",
        {"revision": {"type": "string"}, "path": _PATH},
    ),
    _tool("git_list_branches", "List local branches without changing branches."),
    _tool(
        "git_commit",
        "Commit already-staged changes after explicit user approval.",
        {"message": {"type": "string"}},
        ["message"],
    ),
    _tool(
        "git_switch_branch",
        "Switch to an existing branch after explicit user approval.",
        {"branch": {"type": "string"}},
        ["branch"],
    ),
    _tool(
        "git_create_branch",
        "Create a branch without switching to it, after explicit user approval.",
        {"branch": {"type": "string"}},
        ["branch"],
    ),
]

MAX_DIFF_LINES = 120
MAX_DIFF_CHARS = 12_000
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@{}^~:+-]*$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class WorkspaceTools:
    def __init__(
        self,
        workspace: Path,
        approve_shell: Callable[[str], bool],
        approve_git: Callable[[str, str], bool] | None = None,
        emit: Callable[[str], None] | None = None,
        shell_timeout: float = 60.0,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError(f"Workspace is not a directory: {self.workspace}")
        self.approve_shell = approve_shell
        self.approve_git = approve_git or (lambda _action, _detail: False)
        self.emit = emit or (lambda _text: None)
        self.shell_timeout = shell_timeout

    def _safe_path(self, value: Any) -> Path:
        if not isinstance(value, str) or not value:
            raise ToolError("path must be a non-empty string")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ToolError(f"path escapes workspace: {value}")

        current = self.workspace
        for part in relative.parts:
            if part in {"", "."}:
                continue
            current = current / part
            if current.is_symlink():
                raise ToolError(f"symlink traversal is not allowed: {value}")

        candidate = self.workspace / relative
        try:
            candidate.resolve(strict=False).relative_to(self.workspace)
        except ValueError as exc:
            raise ToolError(f"path escapes workspace: {value}") from exc
        return candidate

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if not isinstance(arguments, dict):
            raise ToolError("tool arguments must be an object")
        handlers = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_text": self._search_text,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
            "run_shell": self._run_shell,
            "git_status": self._git_status,
            "git_diff": self._git_diff,
            "git_log": self._git_log,
            "git_show": self._git_show,
            "git_list_branches": self._git_list_branches,
            "git_commit": self._git_commit,
            "git_switch_branch": self._git_switch_branch,
            "git_create_branch": self._git_create_branch,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"unknown tool: {name}")
        try:
            return handler(arguments)
        except ToolError:
            raise
        except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
            raise ToolError(f"{name} failed: {exc}") from exc

    def _list_files(self, arguments: dict[str, Any]) -> str:
        path = self._safe_path(arguments.get("path", "."))
        if not path.is_dir():
            raise ToolError(f"not a directory: {arguments.get('path', '.')}")
        entries = []
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            suffix = "@" if child.is_symlink() else ("/" if child.is_dir() else "")
            entries.append(f"{child.relative_to(self.workspace)}{suffix}")
        return "\n".join(entries) or "(empty directory)"

    def _read_file(self, arguments: dict[str, Any]) -> str:
        path = self._safe_path(arguments.get("path"))
        if not path.is_file():
            raise ToolError(f"not a file: {arguments.get('path')}")
        return path.read_text(encoding="utf-8")

    def _search_text(self, arguments: dict[str, Any]) -> str:
        query = arguments.get("query")
        if not isinstance(query, str) or not query:
            raise ToolError("query must be a non-empty string")
        target = self._safe_path(arguments.get("path", "."))
        if not target.exists():
            raise ToolError(f"path does not exist: {arguments.get('path', '.')}")

        paths = [target] if target.is_file() else self._walk_files(target)
        matches: list[str] = []
        for path in paths:
            path = self._safe_path(str(path.relative_to(self.workspace)))
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for number, line in enumerate(lines, 1):
                if query in line:
                    relative = path.relative_to(self.workspace)
                    matches.append(f"{relative}:{number}:{line}")
        return "\n".join(matches) or "(no matches)"

    def _walk_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames.sort()
            filenames.sort()
            for name in dirnames:
                candidate = Path(directory) / name
                if candidate.is_symlink():
                    relative = candidate.relative_to(self.workspace)
                    raise ToolError(f"symlink traversal is not allowed: {relative}")
            files.extend(Path(directory) / name for name in filenames)
        return files

    def _write_file(self, arguments: dict[str, Any]) -> str:
        path = self._safe_path(arguments.get("path"))
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        old_content = path.read_text(encoding="utf-8") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._safe_path(str(path.relative_to(self.workspace)))
        path.write_text(content, encoding="utf-8")
        self._emit_diff(path, old_content, content)
        return (
            f"wrote {len(content.encode('utf-8'))} bytes to "
            f"{path.relative_to(self.workspace)}"
        )

    def _edit_file(self, arguments: dict[str, Any]) -> str:
        path = self._safe_path(arguments.get("path"))
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")
        if not isinstance(old_text, str) or not old_text:
            raise ToolError("old_text must be a non-empty string")
        if not isinstance(new_text, str):
            raise ToolError("new_text must be a string")
        if not path.is_file():
            raise ToolError(f"not a file: {arguments.get('path')}")
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(old_text)
        if occurrences != 1:
            raise ToolError(
                f"old_text must match exactly once; found {occurrences} occurrences"
            )
        updated = content.replace(old_text, new_text, 1)
        path = self._safe_path(str(path.relative_to(self.workspace)))
        path.write_text(updated, encoding="utf-8")
        self._emit_diff(path, content, updated)
        return f"edited {path.relative_to(self.workspace)}"

    def _emit_diff(self, path: Path, before: str, after: str) -> None:
        relative = path.relative_to(self.workspace)
        lines = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
        )
        kept: list[str] = []
        characters = 0
        truncated = False
        for line_number, line in enumerate(lines, 1):
            if (
                line_number > MAX_DIFF_LINES
                or characters + len(line) > MAX_DIFF_CHARS
            ):
                truncated = True
                break
            kept.append(line)
            characters += len(line)
        diff = "".join(kept)
        if truncated:
            if diff and not diff.endswith("\n"):
                diff += "\n"
            diff += "... diff truncated ...\n"
        self.emit(f"Applied diff:\n{diff or '(no changes)'}")

    def _run_shell(self, arguments: dict[str, Any]) -> str:
        command = arguments.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ToolError("command must be a non-empty string")
        self._validate_shell_command(command)
        if not self.approve_shell(command):
            raise ToolError("shell command denied by user")
        try:
            result = subprocess.run(
                command,
                cwd=self.workspace,
                shell=True,
                executable="/bin/sh",
                text=True,
                capture_output=True,
                timeout=self.shell_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"shell command timed out after {self.shell_timeout:g} seconds"
            ) from exc
        output = "\n".join(
            part.rstrip() for part in (result.stdout, result.stderr) if part
        )
        return f"exit code: {result.returncode}\n{output or '(no output)'}"

    def _validate_shell_command(self, command: str) -> None:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            raise ToolError(f"malformed shell command: {exc}") from exc
        if not tokens:
            raise ToolError("command must be a non-empty string")
        if any(re.search(r"(?<![\w.-])git(?![\w.-])", token) for token in tokens):
            raise ToolError("Git commands must use the dedicated Git tools")
        for token in tokens:
            if "$" in token or "`" in token or token.startswith("~"):
                raise ToolError("shell path expansion is not allowed")
            path_token = token.lstrip("<>")
            if "=" in path_token:
                path_token = path_token.split("=", 1)[1]
            candidate = Path(path_token)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ToolError(f"shell path escapes workspace: {token}")
            if (
                path_token
                and not path_token.startswith("-")
                and ("/" in path_token or (self.workspace / path_token).exists())
            ):
                self._safe_path(path_token)

    def _git_status(self, _arguments: dict[str, Any]) -> str:
        return self._git(["status", "--short", "--branch"])

    def _git_diff(self, arguments: dict[str, Any]) -> str:
        args = ["diff"]
        staged = arguments.get("staged", False)
        if not isinstance(staged, bool):
            raise ToolError("staged must be a boolean")
        if staged:
            args.append("--cached")
        if "path" in arguments:
            path = self._safe_path(arguments["path"])
            args.extend(["--", str(path.relative_to(self.workspace))])
        return self._git(args)

    def _git_log(self, arguments: dict[str, Any]) -> str:
        count = arguments.get("max_count", 20)
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 100:
            raise ToolError("max_count must be an integer from 1 to 100")
        return self._git(["log", f"--max-count={count}", "--oneline", "--decorate"])

    def _git_show(self, arguments: dict[str, Any]) -> str:
        revision = arguments.get("revision", "HEAD")
        if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
            raise ToolError("revision contains unsupported characters")
        args = ["show", "--no-ext-diff", revision]
        if "path" in arguments:
            path = self._safe_path(arguments["path"])
            args.extend(["--", str(path.relative_to(self.workspace))])
        return self._git(args)

    def _git_list_branches(self, _arguments: dict[str, Any]) -> str:
        return self._git(["branch", "--list", "--verbose", "--no-abbrev"])

    def _git_commit(self, arguments: dict[str, Any]) -> str:
        message = arguments.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ToolError("commit message must be a non-empty string")
        if not self.approve_git("commit", message):
            raise ToolError("Git commit denied by user")
        return self._git(["commit", "-m", message])

    def _git_switch_branch(self, arguments: dict[str, Any]) -> str:
        branch = self._branch(arguments.get("branch"))
        if not self.approve_git("switch branch", branch):
            raise ToolError("Git branch switch denied by user")
        return self._git(["switch", branch])

    def _git_create_branch(self, arguments: dict[str, Any]) -> str:
        branch = self._branch(arguments.get("branch"))
        if not self.approve_git("create branch", branch):
            raise ToolError("Git branch creation denied by user")
        return self._git(["branch", branch])

    @staticmethod
    def _branch(value: Any) -> str:
        if (
            not isinstance(value, str)
            or not _BRANCH_RE.fullmatch(value)
            or ".." in value
            or "@{" in value
            or value.endswith((".", "/", ".lock"))
            or "//" in value
        ):
            raise ToolError("invalid branch name")
        return value

    def _git(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.workspace), *args],
                text=True,
                capture_output=True,
                timeout=self.shell_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                f"Git command timed out after {self.shell_timeout:g} seconds"
            ) from exc
        output = "\n".join(
            part.rstrip() for part in (result.stdout, result.stderr) if part
        )
        if result.returncode:
            raise ToolError(
                f"Git command failed with exit code {result.returncode}: "
                f"{output or '(no output)'}"
            )
        return output or "(no output)"


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    raise ToolError("malformed tool arguments: expected a native JSON object")
