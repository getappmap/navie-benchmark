import unittest
from unittest.mock import ANY, MagicMock, patch
from pathlib import Path
from tempfile import TemporaryDirectory

from navie.editor import Editor
from navie.format_instructions import xml_format_instructions

from solver.workflow.patch import Patch
from solver.workflow.generator import Generator


class TestGenerator(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.editor_mock = MagicMock(spec=Editor)
        self.plan = "Sample plan"
        self.generator = Generator(
            log=self.log_mock, editor=self.editor_mock, plan=self.plan
        )

    @patch("solver.workflow.generator.extract_changes")
    @patch("solver.workflow.generator.git_diff")
    @patch("solver.workflow.generator.relpath")
    @patch("solver.workflow.generator.getcwd")
    def test_generate(
        self, getcwd_mock, relpath_mock, git_diff_mock, extract_changes_mock
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

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self.editor_mock.generate.return_value = "Generated code"
            self.editor_mock.apply.side_effect = (
                lambda file, modified, search: "original code"
            )

            # Test generate method
            generated_code = self.generator.generate()
            self.assertEqual(generated_code, "Generated code")
            self.editor_mock.generate.assert_called_once_with(
                plan="Sample plan",
                prompt=ANY,
                options="/noprojectinfo /exclude=\\btests?\\b|\\btesting\\b|\\btest_|_test\\b",
            )

            # Test apply method
            patch = self.generator.apply("Generated code")
            self.assertIsInstance(patch, Patch)
            self.log_mock.assert_called_with(
                "workflow/generator",
                "Applied code changes to /current/directory/file.py",
            )
            self.editor_mock.apply.assert_called_once_with(
                "/current/directory/file.py", "modified code", search="original code"
            )


if __name__ == "__main__":
    unittest.main()
