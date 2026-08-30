import unittest

from ollama_agent.agent import Agent, MaxStepsError


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
                    "content": "",
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
        agent = Agent(
            client,
            tools,
            "test",
            max_steps=3,
            report_progress=progress.append,
        )

        self.assertEqual(agent.run("work"), "done")
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

    def test_max_steps_exhaustion(self):
        client = FakeClient(
            [
                {"tool_calls": [{"function": {"name": "list_files", "arguments": {}}}]},
                {"tool_calls": [{"function": {"name": "list_files", "arguments": {}}}]},
            ]
        )
        agent = Agent(client, FakeTools(), "test", max_steps=2)
        with self.assertRaisesRegex(MaxStepsError, "2 model steps"):
            agent.run("loop")


if __name__ == "__main__":
    unittest.main()
