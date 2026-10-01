import unittest

from ollama_agent.agent import Agent
from ollama_agent.tools import ToolError


class FakeTools:
    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return "tool result"


class FakeClient:
    def __init__(self, messages):
        self.responses = iter(messages)
        self.requests = []

    def chat(self, model, messages, tools, on_text=None):
        self.requests.append((model, list(messages), tools))
        message = next(self.responses)
        if on_text and message.get("content"):
            for token in message["content"].split("|"):
                on_text(token)
            message = {**message, "content": message["content"].replace("|", "")}
        return message


class AgentTests(unittest.TestCase):
    def test_plain_text_is_streamed(self):
        streamed = []
        agent = Agent(
            FakeClient([{"content": "hel|lo"}]),
            FakeTools(),
            "test",
            stream_text=streamed.append,
        )
        self.assertEqual(agent.run("hi"), "hello")
        self.assertEqual(streamed, ["hel", "lo"])

    def test_multiple_tool_calls_and_rounds(self):
        client = FakeClient(
            [
                {
                    "content": "check|ing",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": {"path": "a"}}},
                        {"function": {"name": "list_files", "arguments": {"path": "."}}},
                    ],
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "search_text", "arguments": {"query": "x"}}}
                    ],
                },
                {"content": "done"},
            ]
        )
        tools = FakeTools()
        progress = []
        streamed = []
        agent = Agent(
            client,
            tools,
            "test",
            stream_text=streamed.append,
            report_progress=progress.append,
        )

        self.assertEqual(agent.run("work"), "done")
        self.assertEqual(streamed, ["check", "ing", "done"])
        self.assertEqual(len(tools.calls), 3)
        self.assertEqual(
            [message["role"] for message in agent.messages].count("tool"), 3
        )
        self.assertEqual(
            progress,
            [
                "Running read_file",
                "Completed read_file",
                "Running list_files",
                "Completed list_files",
                "Running search_text",
                "Completed search_text",
            ],
        )

    def test_string_arguments_are_rejected_not_parsed(self):
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path":"a"}',
                            }
                        }
                    ]
                },
                {"content": "recovered"},
            ]
        )
        tools = FakeTools()
        errors = []
        agent = Agent(client, tools, "test", report_error=errors.append)

        self.assertEqual(agent.run("work"), "recovered")
        self.assertEqual(tools.calls, [])
        self.assertIn("malformed tool arguments", agent.messages[-2]["content"])
        self.assertIn("malformed tool arguments", errors[0])

    def test_more_than_eight_tool_rounds_finish_normally(self):
        tool_turn = {
            "tool_calls": [
                {"function": {"name": "list_files", "arguments": {"path": "."}}}
            ]
        }
        client = FakeClient([tool_turn for _ in range(10)] + [{"content": "done"}])
        tools = FakeTools()
        agent = Agent(client, tools, "test")

        self.assertEqual(agent.run("long task"), "done")
        self.assertEqual(len(client.requests), 11)
        self.assertEqual(len(tools.calls), 10)

    def test_thinking_only_response_is_nudged_and_not_persisted(self):
        client = FakeClient(
            [
                {"content": "", "thinking": "I should inspect the result."},
                {"content": "visible answer"},
            ]
        )
        agent = Agent(client, FakeTools(), "test")

        self.assertEqual(agent.run("work"), "visible answer")
        self.assertIn("visible final content", client.requests[1][1][-1]["content"])
        self.assertEqual(
            [message["role"] for message in agent.messages],
            ["system", "user", "assistant"],
        )
        self.assertFalse(any("thinking" in message for message in agent.messages))

    def test_no_progress_recovery_uses_tool_error_instead_of_repeating_action(self):
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "git_diff",
                                "arguments": {},
                            }
                        }
                    ]
                },
                {"content": "", "thinking": "I should try again."},
                {"content": "This workspace is not a Git repository."},
            ]
        )

        def fail_git_diff(name, _arguments):
            self.assertEqual(name, "git_diff")
            raise ToolError(
                "Git tools are unavailable because the workspace is not inside "
                "a Git repository."
            )

        agent = Agent(client, FakeTools(), "test", tool_executor=fail_git_diff)

        self.assertEqual(
            agent.run("Check the changes."),
            "This workspace is not a Git repository.",
        )
        recovery_messages = client.requests[2][1]
        self.assertIn(
            "Git tools are unavailable because the workspace is not inside "
            "a Git repository.",
            recovery_messages[-2]["content"],
        )
        self.assertIn("repeat the failed action", recovery_messages[-1]["content"])

    def test_no_progress_counter_resets_after_tool_progress(self):
        client = FakeClient(
            [
                {"content": "", "thinking": "first pause"},
                {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "list_files",
                                "arguments": {"path": "."},
                            }
                        }
                    ]
                },
                {"content": ""},
                {"content": "", "thinking": "second pause"},
                {"content": "done"},
            ]
        )
        agent = Agent(client, FakeTools(), "test")

        self.assertEqual(agent.run("work"), "done")

    def test_repeated_no_progress_responses_fail_and_roll_back_turn(self):
        client = FakeClient(
            [
                {"content": "", "thinking": "still thinking"},
                {"content": ""},
                {"content": "", "thinking": "still thinking"},
            ]
        )
        agent = Agent(client, FakeTools(), "test")

        with self.assertRaisesRegex(
            RuntimeError, "3 consecutive model turns.*different tool-capable model"
        ):
            agent.run("work")
        self.assertEqual([message["role"] for message in agent.messages], ["system"])

    def test_failed_turn_rolls_back_history_but_not_completed_tools(self):
        client = FakeClient(
            [
                {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "list_files",
                                "arguments": {"path": "."},
                            }
                        }
                    ]
                },
                {"content": []},
                {"content": "next turn is clean"},
            ]
        )
        tools = FakeTools()
        agent = Agent(client, tools, "test")

        with self.assertRaisesRegex(RuntimeError, "malformed assistant content"):
            agent.run("work")
        self.assertEqual(len(tools.calls), 1)
        self.assertEqual([message["role"] for message in agent.messages], ["system"])
        self.assertEqual(agent.run("try again"), "next turn is clean")


if __name__ == "__main__":
    unittest.main()
