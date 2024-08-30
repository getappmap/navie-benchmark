import unittest

from solver.workflow.linter import Flake8Linter


class TestFlake8Linter(unittest.TestCase):
    def setUp(self):
        self.linter = Flake8Linter()

    def test_lint(self):
        lint_errors = self.linter.lint(__file__)
        self.assertIsInstance(lint_errors, list)
        self.assertGreater(len(lint_errors), 0)

    def test_select_lint_errors(self):
        lint_errors = [
            "solver/workflow/workflow.py:54:1: BLK100 Black would make changes.",
            "solver/workflow/workflow.py:54:1: W293 blank line contains whitespace",
            "solver/workflow/workflow.py:56:13: E303 too many blank lines (2)",
        ]
        line_numbers = {54}
        selected_errors = self.linter.select_lint_errors(lint_errors, line_numbers)
        self.assertEqual(len(selected_errors), 2)
        self.assertIn(
            "solver/workflow/workflow.py:54:1: BLK100 Black would make changes.",
            selected_errors,
        )
        self.assertIn(
            "solver/workflow/workflow.py:54:1: W293 blank line contains whitespace",
            selected_errors,
        )

    def test_lint_error_line_number(self):
        lint_error_line = (
            "solver/workflow/workflow.py:54:1: BLK100 Black would make changes."
        )
        line_number = self.linter.lint_error_line_number(lint_error_line)
        self.assertEqual(line_number, 54)

        lint_error_line = (
            "solver/workflow/workflow.py:56:13: E303 too many blank lines (2)"
        )
        line_number = self.linter.lint_error_line_number(lint_error_line)
        self.assertEqual(line_number, 56)

        lint_error_line = "invalid format"
        line_number = self.linter.lint_error_line_number(lint_error_line)
        self.assertIsNone(line_number)


if __name__ == "__main__":
    unittest.main()
