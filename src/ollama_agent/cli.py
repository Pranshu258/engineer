"""Interactive ``engineer`` command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from .agent import Agent, AgentError
from .client import OllamaClient, OllamaError
from .tools import WorkspaceTools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="engineer",
        description="Interactive, workspace-scoped coding agent powered only by local Ollama.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=os.getenv("ENGINEER_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:9b")),
        help="Ollama model (default: ENGINEER_MODEL, OLLAMA_MODEL, or qwen3.5:9b)",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "ENGINEER_OLLAMA_HOST",
            os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ),
        help="Ollama endpoint (default: ENGINEER_OLLAMA_HOST, OLLAMA_HOST, or localhost)",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        type=Path,
        default=Path(os.getenv("ENGINEER_WORKSPACE", ".")),
        help="tool workspace (default: ENGINEER_WORKSPACE or current directory)",
    )
    return parser


def _interactive_approver(label: str) -> Callable[[str], bool]:
    def approve(detail: str) -> bool:
        if not sys.stdin.isatty():
            print(f"\n{label} denied: no interactive terminal.", file=sys.stderr)
            return False
        print(f"\n{label} requested:\n  {detail}", file=sys.stderr)
        answer = input("Allow? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    return approve


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    shell_approver = _interactive_approver("Shell command")
    git_action_approver = _interactive_approver("Git change")
    try:
        tools = WorkspaceTools(
            args.workspace,
            shell_approver,
            lambda action, detail: git_action_approver(f"{action}: {detail}"),
            emit=lambda text: print(f"\n{text}", flush=True),
        )
        client = OllamaClient(args.base_url)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    agent = Agent(
        client,
        tools,
        model=args.model,
        stream_text=lambda text: print(text, end="", flush=True),
        report_error=lambda text: print(f"\nTool error: {text}", file=sys.stderr),
        report_progress=lambda text: print(
            f"\n[tool] {text}", file=sys.stderr, flush=True
        ),
    )
    return _repl(agent, args)


def _run_prompt(agent: Agent, prompt: str) -> int:
    try:
        agent.run(prompt)
        print()
        return 0
    except (AgentError, OllamaError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


def _repl(agent: Agent, args: argparse.Namespace) -> int:
    print(
        f"Engineer REPL — model={args.model}, workspace={agent.tools.workspace}\n"
        "Type /exit to quit, /clear to reset this session's conversation."
    )
    while True:
        try:
            prompt = input("engineer> ").strip()
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\nInterrupted.")
            continue
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return 0
        if prompt == "/clear":
            agent.clear()
            print("Conversation cleared.")
            continue
        _run_prompt(agent, prompt)
