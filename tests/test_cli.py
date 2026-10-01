import contextlib
import io
import os
import unittest
from unittest.mock import patch

from ollama_agent.cli import build_parser, main, resolve_role_models


class CliTests(unittest.TestCase):
    def test_defaults_and_no_unattended_bypass(self):
        with patch.dict(os.environ, {"ENGINEER_MAX_STEPS": "1"}, clear=True):
            parser = build_parser()
            args = parser.parse_args([])
        self.assertEqual(args.model, "qwen3.5:9b")
        self.assertEqual(args.agent, "engineer")
        self.assertEqual(args.base_url, "http://localhost:11434")
        self.assertFalse(hasattr(args, "max_steps"))
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertNotIn("--yes", option_strings)
        self.assertNotIn("--max-steps", option_strings)

    def test_removed_max_steps_option_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--max-steps", "8"])

    def test_positional_one_shot_prompt_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["one-shot prompt"])

    def test_agent_selection_and_role_model_overrides(self):
        args = build_parser().parse_args(
            ["--agent", "adversarial-pr-reviewer", "--model", "base"]
        )
        self.assertEqual(args.agent, "adversarial-pr-reviewer")
        with patch.dict(
            os.environ,
            {
                "ENGINEER_IMPLEMENTER_MODEL": "implementer",
                "ENGINEER_REVIEW_MODEL": "reviewer",
            },
            clear=True,
        ):
            models = resolve_role_models(args.model)
        self.assertEqual(models.engineer, "base")
        self.assertEqual(models.implementer, "implementer")
        self.assertEqual(models.reviewer, "reviewer")

    def test_role_models_default_to_selected_engineer_model(self):
        with patch.dict(os.environ, {}, clear=True):
            models = resolve_role_models("selected")
        self.assertEqual(
            (models.engineer, models.implementer, models.reviewer),
            ("selected", "selected", "selected"),
        )

    def test_eof_exits_repl_without_contacting_ollama(self):
        stdin = io.StringIO("")
        stdout = io.StringIO()
        with patch("sys.stdin", stdin), contextlib.redirect_stdout(stdout):
            result = main([])
        self.assertEqual(result, 0)
        self.assertIn("Engineer REPL", stdout.getvalue())

    def test_direct_reviewer_selection_reaches_repl(self):
        stdin = io.StringIO("")
        stdout = io.StringIO()
        with patch("sys.stdin", stdin), contextlib.redirect_stdout(stdout):
            result = main(["--agent", "adversarial-pr-reviewer"])
        self.assertEqual(result, 0)
        self.assertIn("agent=adversarial-pr-reviewer", stdout.getvalue())

    def test_run_subcommand_parser(self):
        parser = build_parser()
        args = parser.parse_args(["run", "Fix the failing test"])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.prompt, "Fix the failing test")
        self.assertFalse(args.unattended)

        args_unattended = parser.parse_args(
            ["run", "--unattended", "-m", "custom-model", "Do work"]
        )
        self.assertEqual(args_unattended.command, "run")
        self.assertEqual(args_unattended.prompt, "Do work")
        self.assertTrue(args_unattended.unattended)
        self.assertEqual(args_unattended.model, "custom-model")

    def test_run_executes_prompt_and_exits(self):
        with patch("ollama_agent.cli.AgentRuntime") as mock_runtime_cls:
            mock_runtime = mock_runtime_cls.return_value
            mock_agent = mock_runtime.create_agent.return_value
            mock_agent.run.return_value = "Done"

            result = main(["run", "test task"])
            self.assertEqual(result, 0)
            mock_agent.run.assert_called_once_with("test task")

    def test_run_unattended_configures_auto_approvers(self):
        with patch("ollama_agent.cli.AgentRuntime") as mock_runtime_cls, \
             patch("ollama_agent.cli.WorkspaceTools") as mock_tools_cls:
            mock_agent = mock_runtime_cls.return_value.create_agent.return_value
            mock_agent.run.return_value = "Done"

            result = main(["run", "--unattended", "test task"])
            self.assertEqual(result, 0)
            mock_tools_cls.assert_called_once()
            _, kwargs = mock_tools_cls.call_args
            args = mock_tools_cls.call_args[0]
            # args: (workspace, shell_approver, git_approver)
            shell_approver = args[1]
            git_approver = args[2]
            self.assertTrue(shell_approver("rm -rf something"))
            self.assertTrue(git_approver("commit", "test"))


if __name__ == "__main__":
    unittest.main()
