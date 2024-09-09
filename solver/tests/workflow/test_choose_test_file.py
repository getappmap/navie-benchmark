import os
import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from solver.workflow.choose_test_file import choose_test_file
from solver.workflow.work_dir import WorkDir


class TestChooseTestFile(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("./work/directory", write_sequence = False)
        self.trajectory_file = os.path.join(self.work_dir.path_name, "trajectory.jsonl")
        self.issue_content = "Sample issue content"

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_single_test_file(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: work/directory/test_file.py -->"
        )

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
        assert results is not None
        result = results[0]

        self.assertEqual(result, Path("work/directory/test_file.py"))
        self.log_mock.assert_called_with(
            "choose-test-file",
            "Recommended tests to modify: work/directory/test_file.py",
        )

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_multiple_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: test_file1.py -->\n<!-- file: test_file2.py -->"
        )

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 2
        )
        self.assertEqual(results, [Path("test_file1.py"), Path("test_file2.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_no_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = False
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = ""

        result = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
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

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
        self.assertEqual(results, [Path("work/directory/test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_remove_line_numbers_from_path(self, exists_mock, Editor_mock):
        test = "test_file.py:1-10"

        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = f"<!-- file: {test} -->"

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
        self.assertEqual(results, [Path("test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    @patch("solver.workflow.choose_test_file.os.getcwd")
    def test_invalid_file_paths(self, getcwd_mock, exists_mock, Editor_mock):
        getcwd_mock.return_value = "/other/directory"
        exists_mock.side_effect = lambda x: x == "/work/directory/valid_test_file.py"
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = "<!-- file: /work/directory/invalid_test_file.py -->\n<!-- file: /work/directory/valid_test_file.py -->"

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
        self.assertEqual(results, [Path("../../work/directory/valid_test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_improper_formatting_in_fenced_content(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "```python\n<!-- file: test_file.py -->\n```"
        )

        results = choose_test_file(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 1
        )
        self.assertEqual(results, [Path("test_file.py")])


if __name__ == "__main__":
    unittest.main()
