from abc import abstractmethod
import re
from subprocess import run
from typing import List, Optional, Set

from navie.editor import Editor

FLAKE8_LINT_COMMAND = [
    "flake8",
    "--extend-ignore=BLK100,C402,C408,C416,D,E122,E124,E127,E128,E131,E201,E202,E203,E221,E225,E231,E251,E261,E265,E266,E302,E303,E305,E402,E501,E502,E713,E731,F401,F841,W291,W292,W293",
]


class Linter:
    def __init__(self, lint_command: List[str]) -> None:
        self.lint_command = lint_command

    def lint(self, file_path: str) -> List[str]:
        command = []
        command.extend(self.lint_command)
        command.append(file_path)
        lint_result = run(command, capture_output=True)
        lint_error_str = lint_result.stdout.decode("utf-8").strip()
        return lint_error_str.split("\n")

    def select_lint_errors(
        self, lint_error_lines: List[str], line_numbers: Set[int]
    ) -> List[str]:
        result = []
        for line in lint_error_lines:
            line_number = self.lint_error_line_number(line)
            if line_number in line_numbers:
                result.append(line)
        return result

    @abstractmethod
    def lint_error_line_number(self, lint_error_line: str) -> Optional[int]:
        pass


class Flake8Linter(Linter):
    # Representative errors:
    # solver/workflow/workflow.py:54:1: BLK100 Black would make changes.
    # solver/workflow/workflow.py:54:1: W293 blank line contains whitespace
    # solver/workflow/workflow.py:56:13: E303 too many blank lines (2)
    LINE_NUMBER_PATTERN = re.compile(r"^[^:]+:(\d+):[^:]+:")

    def __init__(self) -> None:
        super().__init__(FLAKE8_LINT_COMMAND)

    def lint_error_line_number(self, lint_error_line: str) -> Optional[int]:
        match = Flake8Linter.LINE_NUMBER_PATTERN.search(lint_error_line)
        if match:
            return int(match.group(1))

        return None
