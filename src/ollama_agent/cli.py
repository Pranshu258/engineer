"""Interactive ``engineer`` command-line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Sequence

from .agent import Agent, AgentError
from .client import OllamaClient, OllamaError
from .profiles import ResourceError, profile_names
from .runtime import AgentRuntime, RoleModels
from .tools import WorkspaceTools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="engineer",
        description="Interactive or headless, workspace-scoped coding agent powered only by local Ollama.",
    )
    _add_shared_arguments(parser)

    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser(
        "run",
        help="run a one-shot task headlessly and exit",
        description="Run a one-shot task headlessly and exit.",
    )
    _add_shared_arguments(run_parser)
    run_parser.add_argument(
        "prompt",
        help="task prompt to execute headlessly",
    )
    run_parser.add_argument(
        "--unattended",
        action="store_true",
        default=False,
        help="auto-approve shell commands and git mutations (for isolated environments/benchmarks)",
    )

    return parser


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-m",
        "--model",
        default=os.getenv("ENGINEER_MODEL", os.getenv("OLLAMA_MODEL", "qwen3.5:9b")),
        help="Ollama model (default: ENGINEER_MODEL, OLLAMA_MODEL, or qwen3.5:9b)",
    )
    parser.add_argument(
        "--agent",
        choices=profile_names(),
        default="engineer",
        help="agent profile (default: engineer)",
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


def resolve_role_models(engineer_model: str) -> RoleModels:
    return RoleModels(
        engineer=engineer_model,
        implementer=os.getenv("ENGINEER_IMPLEMENTER_MODEL", engineer_model),
        reviewer=os.getenv("ENGINEER_REVIEW_MODEL", engineer_model),
    )


def _interactive_approver(label: str) -> Callable[[str], bool]:
    def approve(detail: str) -> bool:
        if not sys.stdin.isatty():
            print(f"\n{label} denied: no interactive terminal.", file=sys.stderr)
            return False
        print(f"\n{label} requested:\n  {detail}", file=sys.stderr)
        answer = input("Allow? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    return approve


def _unattended_approver() -> Callable[[str], bool]:
    def approve(_detail: str) -> bool:
        return True

    return approve


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unattended = getattr(args, "unattended", False)
    if unattended:
        shell_approver = _unattended_approver()
        git_action_approver = _unattended_approver()
    else:
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
        runtime = AgentRuntime(
            client,
            tools,
            resolve_role_models(args.model),
            stream_text=lambda text: print(text, end="", flush=True),
            report_error=lambda text: print(f"\nTool error: {text}", file=sys.stderr),
            report_progress=lambda text: print(
                f"\n[tool] {text}", file=sys.stderr, flush=True
            ),
        )
        agent = runtime.create_agent(args.agent)
    except (ResourceError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "run":
        return _run_prompt(agent, args.prompt)

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
        f"Engineer REPL — agent={args.agent}, model={agent.model}, "
        f"workspace={agent.tools.workspace}\n"
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
