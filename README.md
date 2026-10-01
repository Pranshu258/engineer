# Engineer

`engineer` is a small, interactive coding agent for macOS. It talks directly
to Ollama's local `/api/chat` HTTP endpoint, uses Ollama's native chat tool
calls, and has no cloud provider, fallback provider, action-tag parser, or
runtime dependency outside Python's standard library.

Conversation and tool state exist only for the current process.

Three packaged agent profiles are available:

- `engineer` is the default top-level agent. It has all workspace tools, can
  load packaged skills, and may synchronously delegate one task to either child
  profile.
- `scope-disciplined-swe` has all workspace tools and packaged skills, but
  cannot delegate.
- `adversarial-pr-reviewer` is read-only: it can list, read, search, inspect
  read-only Git state, and load packaged skills. Its review evidence is limited
  to the current local checkout; it cannot inspect remote pull requests,
  comments, CI, or web sources.

## Requirements

- macOS
- Python 3.10 or newer
- [Ollama](https://ollama.com/) running locally
- The default tool-capable model:

```sh
ollama serve
ollama pull qwen3.5:9b
```

Ollama normally listens on `http://localhost:11434`.

## Install

Install the package and isolated `engineer` console command with pipx:

```sh
pipx install .
```

For local development, an editable virtual-environment install also works:

```sh
python3 -m pip install -e .
```

## Use

Run the interactive REPL from the directory the agent may work in:

```sh
engineer
```

Select a profile directly with `--agent`:

```sh
engineer --agent scope-disciplined-swe
engineer --agent adversarial-pr-reviewer
```

Run a task headlessly (non-interactively) with `run`:

```sh
engineer run "Fix the failing tests in tests/test_calc.py"
```

For isolated environments, benchmarks (e.g. Harbor), or automated workflows,
pass `--unattended` to automatically approve shell commands and Git operations:

```sh
engineer run --unattended "Fix the failing tests in tests/test_calc.py"
```

In interactive REPL mode, use `/clear` to discard the current process's
conversation history and `/exit` (or EOF) to quit.

Assistant text is rendered as each Ollama stream chunk arrives. A turn may
contain multiple native tool calls and may continue through multiple
tool/model rounds. There is no fixed model-turn horizon: work continues until
the model returns a visible final response, the user interrupts, or an API,
tool, or recovery failure stops the turn.

### Configuration

| CLI option | Environment variable | Default |
| --- | --- | --- |
| `--model` | `ENGINEER_MODEL`, then `OLLAMA_MODEL` | `qwen3.5:9b` |
| child implementer model | `ENGINEER_IMPLEMENTER_MODEL` | selected `--model` |
| child/reviewer model | `ENGINEER_REVIEW_MODEL` | selected `--model` |
| `--base-url` | `ENGINEER_OLLAMA_HOST`, then `OLLAMA_HOST` | `http://localhost:11434` |
| `--workspace` | `ENGINEER_WORKSPACE` | current directory |

For local-only inference, the configured endpoint must use `localhost` or a
loopback IP address. All three profiles use Ollama; there is no cloud model
routing.

Example:

```sh
ENGINEER_OLLAMA_HOST=http://127.0.0.1:11434 \
  engineer --model qwen3.5:9b --workspace ./project
```

## Tool and approval boundaries

File tools can list, search, read, write, and make one exact text replacement.
Paths are workspace-relative. Absolute paths, every `..` component, and
traversal through symlinks are rejected. Writes and edits need no approval;
immediately after either operation, `engineer` prints a unified diff capped at
120 lines and 12,000 characters.

In interactive mode, every shell command requires a fresh `y`/`yes` response in an interactive
terminal. Commands are denied when standard input is not a terminal, unless running
with `--unattended` (for automated and isolated environments). Shell commands
start in the workspace and explicit absolute paths, `..`, path expansion, and
symlink path arguments are rejected. Git commands are rejected by the shell
tool so they cannot bypass the dedicated Git controls. The approved executable
itself is not an operating-system sandbox; review each command before allowing
it.

The following dedicated Git operations are read-only and run automatically:

- status
- diff (working tree or staged)
- log
- show
- local branch list

Selected workspace paths can be staged automatically with the dedicated staging
tool; shell-based Git commands remain blocked. Git commit, existing-branch
switch, and branch creation each require a fresh interactive confirmation. No
destructive Git operation is exposed.

## Skills and delegation

The profiles and skills are installed as package resources. `load_skill`
returns the full instructions for exactly these five skills:

- `systematic-debugging`
- `codebase-architecture-health`
- `technical-evidence-map`
- `safe-merge-conflict-resolution`
- `engineering-handoff`

Only `engineer` has `delegate_agent`, and it may target only
`scope-disciplined-swe` or `adversarial-pr-reviewer`. Delegation is synchronous:
the child receives an isolated conversation, reuses the same workspace tools
and approval callbacks, and returns its final text as the tool result. Runtime
enforcement limits delegation to one level; child agents cannot delegate.

Tool permissions are enforced twice: each profile receives only its advertised
tool definitions, and the runtime rejects calls outside that profile even if a
model attempts an unadvertised tool. Direct reviewer invocation remains
read-only under the same runtime enforcement.

## Errors

The CLI reports unavailable Ollama endpoints, HTTP/model/API failures,
malformed stream data or native tool arguments, denied actions, and tool
failures. A failed tool result is also returned to the model so it may recover
in a later round.

Empty or thinking-only model turns are not treated as successful answers.
`engineer` asks the model to continue with visible text or a native tool call,
then stops with an actionable error after three consecutive no-progress turns
so a malformed model response cannot loop forever. A failed prompt is removed
from conversation history before the next REPL prompt; any tool or file effects
that already completed remain in the workspace.

## Test

The focused tests mock Ollama and do not require a running server:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m ollama_agent --help
printf '' | PYTHONPATH=src python3 -m ollama_agent
git diff --check
```
