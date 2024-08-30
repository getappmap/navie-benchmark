import os
import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from solver.workflow.choose_test_file import choose_test_file


class TestChooseTestFile(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = "./work/directory"
        self.issue_content = "Sample issue content"

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_single_test_file(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: work/directory/test_file.py -->"
        )

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        assert result is not None
        # Convert to relative path to this dir
        result_rel = result.relative_to(self.work_dir)
        print(result_rel)

        self.assertEqual(result, Path("work/directory/test_file.py"))
        self.log_mock.assert_called_with(
            "choose_test_file", "Chose test file: work/directory/test_file.py"
        )

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_multiple_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: test_file1.py -->\n<!-- file: test_file2.py -->"
        )

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        self.assertEqual(result, Path("test_file1.py"))
        self.log_mock.assert_any_call(
            "choose-test-file",
            "Found multiple test files in <!-- file: test_file1.py -->\n<!-- file: test_file2.py -->",
        )

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_no_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = False
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = ""

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        self.assertIsNone(result)
        self.log_mock.assert_called_with(
            "choose-test-file", "Found no existing test files in "
        )

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_resolve_absolute_to_relative_path(self, exists_mock, Editor_mock):
        exists_mock.side_effect = lambda x: x == "work/directory/test_file.py"
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: /work/directory/test_file.py -->"
        )

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        self.assertEqual(result, Path("work/directory/test_file.py"))

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    @patch("solver.workflow.choose_test_file.os.getcwd")
    def test_invalid_file_paths(self, getcwd_mock, exists_mock, Editor_mock):
        getcwd_mock.return_value = "/other/directory"
        exists_mock.side_effect = lambda x: x == "/work/directory/valid_test_file.py"
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = "<!-- file: /work/directory/invalid_test_file.py -->\n<!-- file: /work/directory/valid_test_file.py -->"

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        self.assertEqual(result, Path("../../work/directory/valid_test_file.py"))
        self.log_mock.assert_called_with(
            "choose_test_file",
            "Chose test file: ../../work/directory/valid_test_file.py",
        )

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_improper_formatting_in_fenced_content(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "```python\n<!-- file: test_file.py -->\n```"
        )

        result = choose_test_file(self.log_mock, self.work_dir, self.issue_content)
        self.assertEqual(result, Path("test_file.py"))


if __name__ == "__main__":
    unittest.main()
