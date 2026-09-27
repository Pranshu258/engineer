import unittest

from ollama_agent.runtime import AgentRuntime, RoleModels


def tool_call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


class FakeTools:
    workspace = "/workspace"

    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return "workspace result"


class RoutedClient:
    def __init__(self, responses):
        self.responses = {
            model: list(model_responses)
            for model, model_responses in responses.items()
        }
        self.requests = []

    def chat(self, model, messages, tools, on_text=None):
        self.requests.append(
            {
                "model": model,
                "messages": list(messages),
                "tools": tools,
            }
        )
        message = self.responses[model].pop(0)
        if on_text and message.get("content"):
            on_text(message["content"])
        return message


class RuntimeTests(unittest.TestCase):
    def make_runtime(self, responses):
        tools = FakeTools()
        client = RoutedClient(responses)
        runtime = AgentRuntime(
            client,
            tools,
            RoleModels(
                engineer="engineer-model",
                implementer="implementer-model",
                reviewer="reviewer-model",
            ),
        )
        return runtime, client, tools

    def test_engineer_delegates_to_each_allowed_agent(self):
        for child_name, child_model in (
            ("scope-disciplined-swe", "implementer-model"),
            ("adversarial-pr-reviewer", "reviewer-model"),
        ):
            with self.subTest(child_name=child_name):
                runtime, client, _tools = self.make_runtime(
                    {
                        "engineer-model": [
                            {
                                "tool_calls": [
                                    tool_call(
                                        "delegate_agent",
                                        {"agent": child_name, "task": "child task"},
                                    )
                                ]
                            },
                            {"content": "parent complete"},
                        ],
                        child_model: [{"content": "child output"}],
                    }
                )

                self.assertEqual(
                    runtime.create_agent("engineer").run("parent task"),
                    "parent complete",
                )
                child_request = next(
                    request
                    for request in client.requests
                    if request["model"] == child_model
                )
                self.assertEqual(
                    [message["role"] for message in child_request["messages"]],
                    ["system", "user"],
                )
                self.assertEqual(
                    child_request["messages"][-1]["content"], "child task"
                )
                self.assertNotIn("parent task", str(child_request["messages"]))
                parent_follow_up = client.requests[-1]["messages"]
                self.assertEqual(parent_follow_up[-1]["content"], "child output")

    def test_child_delegation_is_denied_by_runtime_depth(self):
        runtime, client, _tools = self.make_runtime(
            {
                "engineer-model": [
                    {
                        "tool_calls": [
                            tool_call(
                                "delegate_agent",
                                {
                                    "agent": "scope-disciplined-swe",
                                    "task": "implement",
                                },
                            )
                        ]
                    },
                    {"content": "parent complete"},
                ],
                "implementer-model": [
                    {
                        "tool_calls": [
                            tool_call(
                                "delegate_agent",
                                {
                                    "agent": "adversarial-pr-reviewer",
                                    "task": "review",
                                },
                            )
                        ]
                    },
                    {"content": "child recovered"},
                ],
            }
        )

        self.assertEqual(
            runtime.create_agent("engineer").run("parent task"),
            "parent complete",
        )
        implementer_follow_up = [
            request
            for request in client.requests
            if request["model"] == "implementer-model"
        ][1]
        self.assertIn(
            "delegation depth limit exceeded",
            implementer_follow_up["messages"][-1]["content"],
        )

    def test_child_failure_is_returned_as_a_parent_tool_error(self):
        runtime, client, _tools = self.make_runtime(
            {
                "engineer-model": [
                    {
                        "tool_calls": [
                            tool_call(
                                "delegate_agent",
                                {
                                    "agent": "scope-disciplined-swe",
                                    "task": "implement",
                                },
                            )
                        ]
                    },
                    {"content": "parent recovered"},
                ],
                "implementer-model": [{"content": []}],
            }
        )

        self.assertEqual(
            runtime.create_agent("engineer").run("parent task"),
            "parent recovered",
        )
        self.assertIn(
            "delegated agent 'scope-disciplined-swe' failed",
            client.requests[-1]["messages"][-1]["content"],
        )

    def test_reviewer_advertises_only_read_only_tools_and_denies_write(self):
        runtime, client, tools = self.make_runtime(
            {
                "reviewer-model": [
                    {
                        "tool_calls": [
                            tool_call(
                                "write_file",
                                {"path": "bad.txt", "content": "not allowed"},
                            )
                        ]
                    },
                    {"content": "review complete"},
                ]
            }
        )

        reviewer = runtime.create_agent("adversarial-pr-reviewer")
        self.assertEqual(reviewer.run("review"), "review complete")
        advertised = {
            definition["function"]["name"]
            for definition in client.requests[0]["tools"]
        }
        self.assertEqual(
            advertised,
            {
                "list_files",
                "read_file",
                "search_text",
                "git_status",
                "git_diff",
                "git_log",
                "git_show",
                "git_list_branches",
                "load_skill",
            },
        )
        self.assertEqual(tools.calls, [])
        self.assertIn(
            "not permitted",
            client.requests[1]["messages"][-1]["content"],
        )

    def test_load_skill_returns_instructions_and_rejects_unknown_name(self):
        runtime, client, _tools = self.make_runtime(
            {
                "engineer-model": [
                    {
                        "tool_calls": [
                            tool_call(
                                "load_skill",
                                {"skill": "systematic-debugging"},
                            )
                        ]
                    },
                    {
                        "tool_calls": [
                            tool_call("load_skill", {"skill": "unknown-skill"})
                        ]
                    },
                    {"content": "done"},
                ]
            }
        )

        self.assertEqual(runtime.create_agent("engineer").run("debug"), "done")
        first_result = client.requests[1]["messages"][-1]["content"]
        second_result = client.requests[2]["messages"][-1]["content"]
        self.assertIn("# Systematic debugging", first_result)
        self.assertIn("Unknown skill 'unknown-skill'", second_result)

    def test_direct_profiles_use_role_specific_models(self):
        runtime, _client, _tools = self.make_runtime({})
        self.assertEqual(runtime.create_agent("engineer").model, "engineer-model")
        self.assertEqual(
            runtime.create_agent("scope-disciplined-swe").model,
            "implementer-model",
        )
        self.assertEqual(
            runtime.create_agent("adversarial-pr-reviewer").model,
            "reviewer-model",
        )


if __name__ == "__main__":
    unittest.main()
