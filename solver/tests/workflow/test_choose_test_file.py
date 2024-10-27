import os
import unittest
from unittest.mock import ANY, MagicMock, patch
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
    def test_ignore_previously_listed(self, exists_mock, Editor_mock):
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
            {Path("work/directory/test_file.py")},
            1,
        )
        self.assertEqual(results, [])

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
    def test_extract_files_from_mixed_content(self, exists_mock, Editor_mock):
        mixed_content_response = """
Based on the context, I'll identify the most relevant test files related to ordering issues with model inheritance and Meta.ordering expressions.

1. tests/ordering/tests.py
This is the most relevant test file as it contains tests specifically for ordering behavior, including tests for F() expressions in ordering and inheritance scenarios. It contains test cases for Meta.ordering and order_by() behavior.

2. tests/invalid_models_tests/test_models.py
This file contains tests for validation of model ordering configurations, including tests for invalid ordering expressions and inheritance-related ordering issues.

3. tests/queries/tests.py
This file contains many tests related to query ordering behavior, including tests for ordering with inheritance and expressions.

I ranked them in this order because:

1. tests/ordering/tests.py is specifically focused on ordering behavior and contains the most relevant tests for this issue
2. tests/invalid_models_tests/test_models.py tests validation of ordering configurations which is relevant to Meta.ordering issues
3. tests/queries/tests.py contains general query tests including ordering tests, but is less focused on the specific inheritance + Meta.ordering scenario
"""
        exists_mock.side_effect = lambda x: x.endswith(".py")
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = mixed_content_response

        results = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            3,
            set(),
            1,
        )
        self.assertEqual(
            results,
            [
                Path("tests/ordering/tests.py"),
                Path("tests/invalid_models_tests/test_models.py"),
                Path("tests/queries/tests.py"),
            ],
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
            self.issue_content,
            prompt=ANY,
            options="/noprojectinfo /noformat /noclassify /include=test /noterms /tokenlimit=3000",
            extension="txt",
        )

        self.assertEqual(results, [Path("work/directory/test_file.py")])

    @patch("solver.workflow.choose_test_file.Editor")
    @patch("solver.workflow.choose_test_file.os.path.exists")
    def test_remove_duplicates(self, exists_mock, Editor_mock):
        exists_mock.return_value = True
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.side_effect = [
            "<!-- file: test_file1.py -->\n<!-- file: test_file2.py -->",
            "<!-- file: test_file2.py -->\n<!-- file: test_file3.py -->",
            "<!-- file: test_file1.py -->\n<!-- file: test_file4.py -->",
        ]

        not_test_files = set()
        new_files = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            4,
            not_test_files,
            1,
        )
        self.assertEqual(new_files, [Path("test_file1.py"), Path("test_file2.py")])
        self.assertEqual(not_test_files, {Path("test_file1.py"), Path("test_file2.py")})

        new_files = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            4,
            not_test_files,
            2,
        )
        self.assertEqual(new_files, [Path("test_file3.py")])
        self.assertEqual(
            not_test_files,
            {Path("test_file1.py"), Path("test_file2.py"), Path("test_file3.py")},
        )

        new_files = ask_for_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            4,
            not_test_files,
            3,
        )
        self.assertEqual(new_files, [Path("test_file4.py")])
        self.assertEqual(
            not_test_files,
            {
                Path("test_file1.py"),
                Path("test_file2.py"),
                Path("test_file3.py"),
                Path("test_file4.py"),
            },
        )


class TestChooseTestFiles(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("./work/directory", write_sequence=False)
        self.trajectory_file = os.path.join(self.work_dir.path_name, "trajectory.jsonl")
        self.issue_content = "Sample issue content"
        self.validate_true = lambda x, y: True
        self.validate_false = lambda x, y: False

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_choose_test_files_single_attempt(self, ask_for_test_files_mock):
        ask_for_test_files_mock.return_value = [
            Path("test_file1.py"),
            Path("test_file2.py"),
        ]

        results = choose_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            2,
            self.validate_true,
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
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            2,
            self.validate_true,
        )
        self.assertEqual(results, [Path("test_file1.py"), Path("test_file2.py")])
        self.assertEqual(ask_for_test_files_mock.call_count, 2)

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_choose_test_files_stop_attempts(self, ask_for_test_files_mock):
        ask_for_test_files_mock.side_effect = [
            [Path("test_file1.py")],
            [Path("test_file2.py")],
            [Path("test_file3.py")],
            [Path("test_file4.py")],
        ]

        results = choose_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            3,
            self.validate_true,
        )
        self.assertEqual(
            results,
            [
                Path("test_file1.py"),
                Path("test_file2.py"),
                Path("test_file3.py"),
            ],
        )
        self.assertEqual(ask_for_test_files_mock.call_count, 3)

    @patch("solver.workflow.choose_test_file.ask_for_test_files")
    def test_invalid_test_files_are_filtered_out(self, ask_for_test_files_mock):
        ask_for_test_files_mock.return_value = [Path("test_file1.p")]

        results = choose_test_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            2,
            self.validate_false,
        )
        self.assertEqual(results, [])
        self.assertEqual(ask_for_test_files_mock.call_count, 3)


if __name__ == "__main__":
    unittest.main()
