import unittest
from unittest.mock import ANY, MagicMock, mock_open, patch
from pathlib import Path
from tempfile import TemporaryDirectory

from solver.workflow.patch import Patch
from solver.workflow.generate_test import GenerateTest, strip_filename_comment
from solver.workflow.work_dir import WorkDir


class TestGenerateTest(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("/work/directory", write_sequence=False)
        self.trajectory_file = str(self.work_dir.path / "trajectory.jsonl")
        self.test_command = "python -m unittest"
        self.edit_test_file = Path("/work/directory/edit_test_file.py")
        self.test_file_path = Path("/work/directory/test_file.py")
        self.issue_text = "Sample issue text"
        self.observed_errors = ["Error 1", "Error 2"]
        self.generator = GenerateTest(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.test_command,
            self.test_file_path,
            self.issue_text,
            self.observed_errors,
            python_version="3.8",
        )

    @patch("solver.workflow.generate_test.extract_fenced_content")
    @patch("solver.workflow.generate_test.git_diff")
    @patch("solver.workflow.generate_test.Editor")
    @patch("solver.workflow.generate_test.os.makedirs")
    @patch("solver.workflow.generate_test.open", new_callable=mock_open)
    @patch("solver.workflow.generate_test.run")
    def test_generate_test(
        self,
        run_mock,
        open_mock,
        makedirs_mock,
        Editor_mock,
        git_diff_mock,
        extract_fenced_content_mock,
    ):
        git_diff_mock.return_value = (
            "diff --git a/test_file.py b/test_file.py\nindex 123..456 789"
        )
        extract_fenced_content_mock.return_value = ["Generated test content"]

        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.test.return_value = "Generated test code"
        editor_instance_mock.apply.return_value = None

        with TemporaryDirectory() as temp_dir:
            # Test generate method
            generated_test = self.generator.generate(self.edit_test_file, 1, [])
            self.assertEqual(generated_test, "Generated test code")
            editor_instance_mock.test.assert_called_once_with(
                issue=ANY,
                prompt=ANY,
                options="/noprojectinfo /noclassify",
            )

        # Test apply method
        patch = self.generator.apply(self.test_file_path, "Generated test code")
        self.assertIsInstance(patch, Patch)
        self.log_mock.assert_called_with(
            "generate-test",
            "Generated test file: /work/directory/test_file.py",
        )
        makedirs_mock.assert_called_once_with(
            str(self.test_file_path.parent), exist_ok=True
        )
        open_mock.assert_called_once_with(self.test_file_path, "w")
        run_mock.assert_called_once_with(["git", "add", "-N", "."], check=True)

    @patch("solver.workflow.generate_test.Editor")
    def test_invert(self, Editor_mock):
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.test.return_value = "Inverted test code"

        inverted_code = self.generator.invert("Original test code", 1)
        self.assertEqual(inverted_code, "Inverted test code")
        editor_instance_mock.test.assert_called_once()


class TestStripFilenameComment(unittest.TestCase):
    CODE = """import pytest

def test_nested_compound_model_separability():
    # Define the compound model
    cm = models.Linear1D(10) & models.Linear1D(5)"""

    def test_strip_comment(self):
        content = f"""<!-- file: test_compound_separability.py -->
{TestStripFilenameComment.CODE}"""

        stripped_content = strip_filename_comment(content)
        self.assertEqual(stripped_content, TestStripFilenameComment.CODE)

    def test_strip_comment_no_comment(self):
        stripped_content = strip_filename_comment(TestStripFilenameComment.CODE)
        self.assertEqual(stripped_content, TestStripFilenameComment.CODE)

    def test_strip_comment_whitespace(self):
        comment = "<!-- file: test_compound_separability.py --> "
        content = f"""{comment}
{TestStripFilenameComment.CODE}"""
        stripped_content = strip_filename_comment(content)
        self.assertEqual(stripped_content, TestStripFilenameComment.CODE)

    def test_strip_multiple_filename_comments(self):
        content = f"""<!-- file: file_1.py -->
<!-- file: file_2.py -->
{TestStripFilenameComment.CODE}"""
        stripped_content = strip_filename_comment(content)
        self.assertEqual(stripped_content, TestStripFilenameComment.CODE)


if __name__ == "__main__":
    unittest.main()
