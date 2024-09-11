import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from solver.workflow.choose_test_file import ask_for_test_files, choose_test_files
from solver.workflow.work_dir import WorkDir


class TestAskForTestFiles(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("./work/directory", write_sequence=False)
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

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
        )
        assert results is not None
        result = results[0]

        self.assertEqual(result, Path("work/directory/test_file.py"))

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_multiple_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: test_file1.py -->\n<!-- file: test_file2.py -->"
        )

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            2,
            set(),
            1,
        )
        self.assertEqual(results, [Path("test_file1.py"), Path("test_file2.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_no_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = False
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = ""

        result = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
        )
        self.assertEqual(result, [])
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

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
        )
        self.assertEqual(results, [Path("work/directory/test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_remove_line_numbers_from_path(self, exists_mock, Editor_mock):
        test = "test_file.py:1-10"

        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = f"<!-- file: {test} -->"

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
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

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
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

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            set(),
            1,
        )
        self.assertEqual(results, [Path("test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_with_non_empty_not_test_files(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = (
            "<!-- file: work/directory/test_file.py -->"
        )

        not_test_files = {Path("work/directory/known_test_file.py")}
        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            1,
            not_test_files,
            1,
        )

        editor_instance_mock.search.assert_called_once_with(
            """Identify 1 test files that are most related to the issue. Put the most relevant file first,
followed by less relevant files.

The files must all be different.

<issue>
Sample issue content
</issue>
Do not emit any of the following files, because they are already known:

work/directory/known_test_file.py
""",
            prompt="""## Output format
    
Output the results as one file path on each line, and nothing else.

Do not include line numbers or any location within the file. Just the file path.

## Examples
        
path/to/test_1.py
    """,
            options="/noprojectinfo /noformat /noclassify /include=test /tokenlimit=3000",
            extension="txt",
        )

        self.assertEqual(results, [Path("work/directory/test_file.py")])


if __name__ == "__main__":
    unittest.main()


class TestChooseTestFiles(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("./work/directory", write_sequence=False)
        self.trajectory_file = os.path.join(self.work_dir.path_name, "trajectory.jsonl")
        self.issue_content = "Sample issue content"

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_choose_test_files_single_attempt(self, ask_for_test_files_mock):
        ask_for_test_files_mock.return_value = [
            Path("test_file1.py"),
            Path("test_file2.py"),
        ]

        results = choose_test_files(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 2
        )
        self.assertEqual(results, [Path("test_file1.py"), Path("test_file2.py")])
        ask_for_test_files_mock.assert_called_once()

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_choose_test_files_multiple_attempts(self, ask_for_test_files_mock):
        ask_for_test_files_mock.side_effect = [
            [Path("test_file1.py")],
            [Path("test_file2.py")],
            [],
        ]

        results = choose_test_files(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 2
        )
        self.assertEqual(results, [Path("test_file1.py"), Path("test_file2.py")])
        self.assertEqual(ask_for_test_files_mock.call_count, 2)

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_choose_test_files_repeated_files(self, ask_for_test_files_mock):
        ask_for_test_files_mock.side_effect = [
            [Path("test_file1.py")],
            [Path("test_file1.py"), Path("test_file2.py")],
            [Path("test_file2.py")],
        ]

        results = choose_test_files(
            self.log_mock, self.work_dir, self.trajectory_file, self.issue_content, 3
        )
        self.assertEqual(
            results,
            [
                Path("test_file1.py"),
                Path("test_file2.py"),
            ],
        )
        self.assertEqual(ask_for_test_files_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
