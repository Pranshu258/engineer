# Engineer

`engineer` is a small, interactive coding agent for macOS. It talks directly
to Ollama's local `/api/chat` HTTP endpoint, uses Ollama's native chat tool
calls, and has no cloud provider, fallback provider, action-tag parser, or
runtime dependency outside Python's standard library.

Conversation and tool state exist only for the current process.

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

There is intentionally no one-shot prompt mode. Use `/clear` to discard the
current process's conversation history and `/exit` (or EOF) to quit.

Assistant text is rendered as each Ollama stream chunk arrives. A turn may
contain multiple native tool calls and may continue through multiple
tool/model rounds.

### Configuration

| CLI option | Environment variable | Default |
| --- | --- | --- |
| `--model` | `ENGINEER_MODEL`, then `OLLAMA_MODEL` | `qwen3.5:9b` |
| `--base-url` | `ENGINEER_OLLAMA_HOST`, then `OLLAMA_HOST` | `http://localhost:11434` |
| `--workspace` | `ENGINEER_WORKSPACE` | current directory |
| `--max-steps` | `ENGINEER_MAX_STEPS` | `8` |

For local-only inference, the configured endpoint must use `localhost` or a
loopback IP address.

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

Every shell command requires a fresh `y`/`yes` response in an interactive
terminal. There is no flag or environment variable that bypasses this prompt,
and commands are denied when standard input is not a terminal. Shell commands
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

Git commit, existing-branch switch, and branch creation each require a fresh
interactive confirmation. No destructive Git operation is exposed.

## Errors

The CLI reports unavailable Ollama endpoints, HTTP/model/API failures,
malformed stream data or native tool arguments, denied actions, tool failures,
and exhaustion of the configured model-step limit. A failed tool result is
also returned to the model so it may recover in a later round.

## Test

The focused tests mock Ollama and do not require a running server:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m ollama_agent --help
printf '' | PYTHONPATH=src python3 -m ollama_agent
git diff --check
```
