import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ollama_agent.tools import ToolError, WorkspaceTools


class WorkspaceToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.shell_decisions = []
        self.git_decisions = []
        self.emitted = []
        self.tools = WorkspaceTools(
            self.root,
            lambda command: self.shell_decisions.append(command) or False,
            lambda action, detail: self.git_decisions.append((action, detail)) or False,
            self.emitted.append,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_file_tools_search_and_immediate_edit_diff(self):
        self.tools.execute(
            "write_file", {"path": "nested/a.txt", "content": "one\nneedle\n"}
        )
        result = self.tools.execute(
            "edit_file",
            {
                "path": "nested/a.txt",
                "old_text": "one",
                "new_text": "two",
            },
        )

        self.assertEqual(result, "edited nested/a.txt")
        self.assertEqual(
            self.tools.execute("read_file", {"path": "nested/a.txt"}),
            "two\nneedle\n",
        )
        self.assertIn(
            "nested/a.txt:2:needle",
            self.tools.execute("search_text", {"query": "needle"}),
        )
        self.assertIn("nested/", self.tools.execute("list_files", {}))
        self.assertIn("--- a/nested/a.txt", self.emitted[-1])
        self.assertIn("+two", self.emitted[-1])

    def test_edit_requires_one_exact_match(self):
        (self.root / "a.txt").write_text("same same", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "found 2"):
            self.tools.execute(
                "edit_file",
                {"path": "a.txt", "old_text": "same", "new_text": "new"},
            )

    def test_printed_diff_is_bounded(self):
        content = "".join(f"line {number}\n" for number in range(300))
        self.tools.execute("write_file", {"path": "large.txt", "content": content})
        diff = self.emitted[-1]
        self.assertIn("diff truncated", diff)
        self.assertLessEqual(len(diff), 12_100)

    def test_parent_and_absolute_paths_are_blocked(self):
        for path in ("../outside.txt", "a/../outside.txt", "/tmp/outside.txt"):
            with self.subTest(path=path), self.assertRaisesRegex(
                ToolError, "escapes workspace"
            ):
                self.tools.execute("read_file", {"path": path})

    def test_file_and_directory_symlink_traversal_are_blocked(self):
        outside = self.root.parent / f"{self.root.name}-outside"
        outside.mkdir()
        try:
            (outside / "secret.txt").write_text("secret needle", encoding="utf-8")
            (self.root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ToolError, "symlink traversal"):
                self.tools.execute("write_file", {"path": "link/a.txt", "content": "x"})
            with self.assertRaisesRegex(ToolError, "symlink traversal"):
                self.tools.execute("search_text", {"query": "needle"})
            (self.root / "secret-link").symlink_to(outside / "secret.txt")
            with self.assertRaisesRegex(ToolError, "symlink traversal"):
                self.tools.execute("read_file", {"path": "secret-link"})
        finally:
            (outside / "secret.txt").unlink()
            outside.rmdir()

    def test_shell_denial_and_approval(self):
        with self.assertRaisesRegex(ToolError, "denied by user"):
            self.tools.execute("run_shell", {"command": "printf denied"})
        self.assertEqual(self.shell_decisions, ["printf denied"])

        approved = WorkspaceTools(self.root, lambda _command: True)
        self.assertEqual(
            approved.execute("run_shell", {"command": "printf approved"}),
            "exit code: 0\napproved",
        )

    def test_shell_rejects_escape_symlink_and_git_bypass_before_prompt(self):
        (self.root / "link").symlink_to(self.root.parent, target_is_directory=True)
        commands = (
            "cat ../secret",
            "cat /tmp/secret",
            "tool --output=/tmp/secret",
            "cat link/secret",
            "tool --input=link/secret",
            "git status",
            "sh -c 'git reset --hard'",
        )
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ToolError):
                self.tools.execute("run_shell", {"command": command})
        self.assertEqual(self.shell_decisions, [])

    def test_read_only_git_tools_do_not_prompt(self):
        with patch.object(self.tools, "_git", return_value="ok") as run_git:
            self.assertEqual(self.tools.execute("git_status", {}), "ok")
            self.assertEqual(self.tools.execute("git_list_branches", {}), "ok")
            self.assertEqual(self.tools.execute("git_log", {"max_count": 3}), "ok")
        self.assertEqual(self.git_decisions, [])
        self.assertEqual(run_git.call_count, 3)

    def test_git_mutations_require_confirmation(self):
        cases = (
            ("git_commit", {"message": "message"}, "commit"),
            ("git_switch_branch", {"branch": "main"}, "switch branch"),
            ("git_create_branch", {"branch": "topic"}, "create branch"),
        )
        with patch.object(self.tools, "_git") as run_git:
            for tool, arguments, action in cases:
                with self.subTest(tool=tool), self.assertRaisesRegex(
                    ToolError, "denied by user"
                ):
                    self.tools.execute(tool, arguments)
                self.assertEqual(self.git_decisions[-1][0], action)
        run_git.assert_not_called()

    def test_approved_git_mutation_uses_fixed_command(self):
        tools = WorkspaceTools(
            self.root,
            lambda _command: False,
            lambda _action, _detail: True,
        )
        with patch.object(tools, "_git", return_value="committed") as run_git:
            self.assertEqual(
                tools.execute("git_commit", {"message": "safe message"}), "committed"
            )
        run_git.assert_called_once_with(["commit", "-m", "safe message"])


if __name__ == "__main__":
    unittest.main()
