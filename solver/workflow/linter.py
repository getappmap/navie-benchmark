from abc import abstractmethod
import re
from subprocess import run

from navie.editor import Editor

FLAKE8_LINT_COMMAND = [
    "flake8",
    "--extend-ignore=BLK100,C402,C408,C416,D,E122,E124,E127,E128,E131,E201,E202,E203,E221,E225,E231,E251,E261,E265,E266,E302,E303,E305,E402,E501,E502,E713,E731,F401,F841,W291,W292,W293",
]


def generate_lint_error_avoidance_plan(work_dir: str, plan, lint_errors: list) -> str:
    lint_errors_str = "\n".join(lint_errors)
    return Editor(work_dir).ask(
        f"""Generate a simple set of instructions that will ensure that the following
lint errors do not occur when code is generated for the plan.

These instructions will be appended to the plan as a reminder to avoid these lint errors.

Do not generate a complete plan, just generate a bullet list of instructions.

## Lint errors

{lint_errors_str}

## Plan

{plan}
""",
        options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        question_name="lint_error_avoidance_plan",
    )


class Linter:
    def __init__(self, lint_command: list) -> None:
        self.lint_command = lint_command

    def lint(self, file_path: str) -> list:
        command = []
        command.extend(self.lint_command)
        command.append(file_path)
        lint_result = run(command, capture_output=True)
        lint_error_str = lint_result.stdout.decode("utf-8").strip()
        return lint_error_str.split("\n")

    def select_lint_errors(self, lint_error_lines: list, line_numbers: set) -> list:
        result = []
        for line in lint_error_lines:
            line_number = self.lint_error_line_number(line)
            if line_number in line_numbers:
                result.append(line)
        return result

    @abstractmethod
    def lint_error_line_number(self, lint_error_line):
        pass


class Flake8Linter(Linter):
    # Representative errors:
    # solver/workflow/workflow.py:54:1: BLK100 Black would make changes.
    # solver/workflow/workflow.py:54:1: W293 blank line contains whitespace
    # solver/workflow/workflow.py:56:13: E303 too many blank lines (2)
    LINE_NUMBER_PATTERN = re.compile(r"^[^:]+:(\d+):[^:]+:")

    def __init__(self) -> None:
        super().__init__(FLAKE8_LINT_COMMAND)

    def lint_error_line_number(self, lint_error_line):
        match = Flake8Linter.LINE_NUMBER_PATTERN.search(lint_error_line)
        if match:
            return int(match.group(1))

        return None
