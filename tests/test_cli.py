import contextlib
import io
import os
import unittest
from unittest.mock import patch

from ollama_agent.cli import build_parser, main


class CliTests(unittest.TestCase):
    def test_defaults_and_no_unattended_bypass(self):
        with patch.dict(os.environ, {"ENGINEER_MAX_STEPS": "1"}, clear=True):
            parser = build_parser()
            args = parser.parse_args([])
        self.assertEqual(args.model, "qwen3.5:9b")
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

    def test_eof_exits_repl_without_contacting_ollama(self):
        stdin = io.StringIO("")
        stdout = io.StringIO()
        with patch("sys.stdin", stdin), contextlib.redirect_stdout(stdout):
            result = main([])
        self.assertEqual(result, 0)
        self.assertIn("Engineer REPL", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
