from os import getcwd, path
from posixpath import relpath
from typing import Callable, List, Optional
import traceback


from navie.editor import Editor
from navie.format_instructions import xml_format_instructions
from navie.extract_changes import extract_changes
from solver.workflow.work_dir import WorkDir

from .patch import (
    Patch,
    filter_patch_exclude_tests,
    git_diff,
)


class GenerateCode:

    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: WorkDir,
        trajectory_file: str,
        plan: str,
        python_version: str,
        file_limit: int = 1,
    ):
        self.log = log
        self.work_dir = work_dir
        self.trajectory_file = trajectory_file
        self.plan = plan
        self.python_version = python_version
        self.file_limit = file_limit

    # Generate a code change plan and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(
        self, attempt: int, lint_errors: List[str] = [], test_errors: List[str] = []
    ) -> str:
        plan = [
            self.plan,
        ]
        if lint_errors:
            lint_errors_str = "\n".join(lint_errors)
            plan.append(
                f"""## Preventing linter errors
                
Ensure that the following lint errors do not occur:

<lint-errors>                        
{lint_errors_str}
</lint-errors>
"""
            )

        if test_errors:
            test_errors_str = "\n".join(test_errors)
            plan.append(
                f"""## Preventing test errors

Ensure that the following test errors do not occur:

<test-errors>
{test_errors_str}
</test-errors>
"""
            )

        prompt = [
            f"""## Output format

{xml_format_instructions()}

## Python environment

Do not use Python features that are not available in this Python version.

{self.python_version}
"""
        ]

        editor = Editor(
            self.work_dir.code(attempt).path_name,
            log_dir=self.work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        )
        return editor.generate(
            plan="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /noclassify /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, attempt: int, code: str) -> Optional[Patch]:
        changes = extract_changes(code)
        distinct_files = set(
            [path.relpath(change.file, getcwd()) for change in changes]
        )
        if len(distinct_files) > self.file_limit:
            self.log(
                "workflow/generate-code",
                f"Found {len(changes)} changes, but the limit is {self.file_limit}",
            )

        editor = Editor(
            self.work_dir.apply().path_name,
            log_dir=self.work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        )
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
            except Exception:
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
