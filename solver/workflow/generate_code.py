from os import getcwd, path
from posixpath import relpath
from typing import Callable, Optional
import traceback


from navie.editor import Editor
from navie.format_instructions import xml_format_instructions
from navie.extract_changes import extract_changes

from .linter import generate_lint_error_avoidance_plan
from .patch import (
    Patch,
    filter_patch_exclude_tests,
    git_diff,
)


class GenerateCode:

    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: str,
        plan: str,
        file_limit: int = 1,
    ):
        self.log = log
        self.work_dir = work_dir
        self.plan = plan
        self.file_limit = file_limit

    # Generate a code change plan and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(self, attempt: int, lint_errors: list = []) -> str:
        work_dir = path.join(self.work_dir, "generate", str(attempt))

        plan = [
            self.plan,
        ]
        if lint_errors:
            lint_error_avoidance_plan = generate_lint_error_avoidance_plan(
                work_dir, self.plan, lint_errors
            )
            plan.append(lint_error_avoidance_plan)
            plan.append(
                "Detailed code, which explicitly avoids lint errors, is now presented."
            )

        prompt = [
            f"""## Output format

{xml_format_instructions()}
"""
        ]

        editor = Editor(path.join(self.work_dir, "generate", str(attempt)))
        return editor.generate(
            plan="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, attempt: int, code: str) -> Optional[Patch]:
        changes = extract_changes(code)
        changed_files = set([change.file for change in changes])
        if len(changed_files) > self.file_limit:
            self.log(
                "workflow/generate-code",
                f"Found {len(changes)} changes, but the limit is {self.file_limit}",
            )

        editor = Editor(path.join(self.work_dir, "apply", str(attempt)))
        for change in changes:
            change.file = relpath(change.file, getcwd())
            if not change.original:
                self.log(
                    "apply",
                    f"WARNING - No original text provided for {change.file}. Ignoring patch.",
                )
                continue

            try:
                editor.apply(change.file, change.modified, search=change.original)
            except:
                self.log(
                    "apply",
                    f"Failed to apply change to {change.file}: {traceback.format_exc()}",
                )

        file_paths = [change.file for change in changes]
        file_paths_str = ", ".join(file_paths)
        self.log("workflow/generate-code", f"Applied code changes to {file_paths_str}")

        patch_str = filter_patch_exclude_tests(git_diff())

        if not patch_str:
            self.log("workflow/generate-code", "No changes detected")
            return None

        return Patch(patch_str)
