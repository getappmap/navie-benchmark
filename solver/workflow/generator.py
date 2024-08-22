from os import getcwd
from posixpath import relpath
from typing import Callable

from navie.editor import Editor
from navie.format_instructions import xml_format_instructions
from navie.extract_changes import extract_changes

from .patch import Patch, filter_patch_exclude_tests, git_diff


class Generator:

    def __init__(
        self,
        log: Callable[[str, str], None],
        editor: Editor,
        plan: str,
        file_limit: int = 1,
    ):
        self.log = log
        self.editor = editor
        self.plan = plan
        self.file_limit = file_limit

    # Generate a code change plan and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(self, lint_errors: list = []) -> str:
        plan = [
            self.plan,
        ]
        prompt = [
            f"""## Output format

{xml_format_instructions()}
"""
        ]
        if lint_errors:
            lint_errors_str = "\n".join(lint_errors)
            lint_error_avoidance_plan = self.editor.ask(
                f"""Generate a simple set of instructions that will ensure that the following
lint errors do not occur when code is generated for the plan.

These instructions will be appended to the plan as a reminder to avoid these lint errors.

Do not generate a complete plan, just generate a bullet list of instructions.

## Lint errors

{lint_errors_str}

## Plan

{self.plan}
""",
                options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
                question_name="lint_error_avoidance_plan",
            )

            lint_errors_str = "\n".join(lint_errors)
            plan.append(lint_error_avoidance_plan)
            plan.append(
                "Detailed code, which explicitly avoids lint errors, is now presented."
            )

        return self.editor.generate(
            plan="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, code: str) -> Patch:
        changes = extract_changes(code)
        changed_files = set([change.file for change in changes])
        if len(changed_files) > self.file_limit:
            self.log(
                "workflow/generator",
                f"Found {len(changes)} changes, but the limit is {self.file_limit}",
            )

        for change in changes:
            change.file = relpath(change.file, getcwd())
            self.editor.apply(change.file, change.modified, search=change.original)

        file_paths = [change.file for change in changes]
        file_paths_str = ", ".join(file_paths)
        self.log("workflow/generator", f"Applied code changes to {file_paths_str}")

        return Patch(filter_patch_exclude_tests(git_diff()))
