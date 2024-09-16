import unittest
from unittest.mock import ANY, MagicMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

from solver.workflow.patch import Patch
from solver.workflow.generate_code import GenerateCode
from solver.workflow.work_dir import WorkDir


class TestGenerateCode(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("/work/directory", write_sequence=False)
        self.trajectory_file = str(self.work_dir.path / "trajectory.jsonl")
        self.plan = "Sample plan"
        self.generator = GenerateCode(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.plan,
            python_version="3.8",
        )

    @patch("solver.workflow.generate_code.extract_changes")
    @patch("solver.workflow.generate_code.git_diff")
    @patch("solver.workflow.generate_code.relpath")
    @patch("solver.workflow.generate_code.getcwd")
    @patch("solver.workflow.generate_code.Editor")
    def test_generate_code(
        self,
        Editor_mock,
        getcwd_mock,
        relpath_mock,
        git_diff_mock,
        extract_changes_mock,
    ):
        getcwd_mock.return_value = "/current/directory"
        relpath_mock.side_effect = lambda x, _: x
        git_diff_mock.return_value = (
            "diff --git a/file.py b/file.py\nindex 123..456 789"
        )
        extract_changes_mock.return_value = [
            MagicMock(
                file="/current/directory/file.py",
                original="original code",
                modified="modified code",
            )
        ]

        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.generate.return_value = "Generated code"
        editor_instance_mock.apply.return_value = None

        with TemporaryDirectory() as temp_dir:
            # Test generate method
            generated_code = self.generator.generate(1, [])
            self.assertEqual(generated_code, "Generated code")

            editor_instance_mock.generate.assert_called_once_with(
                plan=ANY,
                prompt=ANY,
                options="/noprojectinfo /noclassify /exclude=\\btests?\\b|\\btesting\\b|\\btest_|_test\\b",
            )

            # Test apply method
            patch = self.generator.apply(1, "Generated code")
            self.assertIsInstance(patch, Patch)
            self.log_mock.assert_called_with(
                "workflow/generate-code",
                "Applied code changes to /current/directory/file.py",
            )
            editor_instance_mock.apply.assert_called_once_with(
                "/current/directory/file.py", "modified code", search="original code"
            )

    @patch("solver.workflow.generate_code.extract_changes")
    @patch("solver.workflow.generate_code.git_diff")
    @patch("solver.workflow.generate_code.relpath")
    @patch("solver.workflow.generate_code.getcwd")
    @patch("solver.workflow.generate_code.Editor")
    def test_apply_ignores_test_files(
        self,
        Editor_mock,
        getcwd_mock,
        relpath_mock,
        git_diff_mock,
        extract_changes_mock,
    ):
        getcwd_mock.return_value = "/current/directory"
        relpath_mock.side_effect = lambda x, _: x
        git_diff_mock.return_value = (
            "diff --git a/file.py b/file.py\nindex 123..456 789"
        )
        extract_changes_mock.return_value = [
            MagicMock(
                file="/current/directory/file.py",
                original="original code",
                modified="modified code",
            ),
            MagicMock(
                file="/current/directory/tests/test_file.py",
                original="original test code",
                modified="modified test code",
            ),
        ]

        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.apply.return_value = None

        with TemporaryDirectory() as temp_dir:
            patch = self.generator.apply(1, "Generated code")
            self.assertIsInstance(patch, Patch)
            self.log_mock.assert_called_with(
                "workflow/generate-code",
                "Applied code changes to /current/directory/file.py",
            )
            editor_instance_mock.apply.assert_called_once_with(
                "/current/directory/file.py", "modified code", search="original code"
            )


if __name__ == "__main__":
    unittest.main()
