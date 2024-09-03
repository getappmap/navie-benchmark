from os import path
import os
from pathlib import Path
from subprocess import run
from typing import Callable, Optional


from navie.editor import Editor
from navie.fences import extract_fenced_content

from .patch import (
    Patch,
    filter_patch_include_tests,
    git_diff,
)


class GenerateTest:

    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: Path,
        trajectory_file: str,
        test_file_path: Path,
        issue_text: str,
        observed_errors: list[str],
        python_version: str,
    ):
        self.log = log
        self.work_dir = work_dir
        self.trajectory_file = trajectory_file
        self.test_file_path = test_file_path
        self.issue_text = issue_text
        self.observed_errors = observed_errors
        self.python_version = python_version

    # Generate a code change and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(self, attempt: int, lint_errors: list = []) -> str:
        work_dir = path.join(self.work_dir, "test", str(attempt))

        plan = [
            f"""Reproduce the following issue with a test case.

<issue>
{self.issue_text}
</issue>

The name of the generated test case file should be: {self.test_file_path}.

Do not try and solve the issue. Just reproduce it with the test case.

The test should pass when the described issue is observed. For example, if the 
issue describes an exception, the test should assert that the exception is raised.

If the issue describes some output that is incorrect, the test should assert that
the incorrect output is produced.
"""
        ]
        if self.observed_errors:
            observed_errors_str = "\n".join(self.observed_errors)
            plan.append(
                f"""## Preventing test execution errors
                
Ensure that the following test execution errors do not occur:

<test-errors>
{observed_errors_str}
</test-errors>
"""
            )
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

        prompt = [
            f"""## Output

Output a completely new and self-contained test case, that is based on the original
test case code. 

Remove all other test classes and functions aside from the one that is being generated.

Never use the @skipIf annotation.

## Python environment

Do not use Python features that are not available in this Python version.

{self.python_version}
"""
        ]

        return Editor(work_dir, trajectory_file=self.trajectory_file).test(
            issue="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo",
        )

    # Invert the outcome of the test case, so that the test will now fail specifically
    # at the location where the issue was asserted.
    def invert(self, code: str, attempt: int, lint_errors: list = []) -> str:
        work_dir = path.join(self.work_dir, "invert-test", str(attempt))

        plan = [
            f"""Alter the test case code so that it will now FAIL when the issue is observed.

This test was written to PASS when the issue is observed. Now, the test should FAIL
specifically at the location where the presence of the bug was previously asserted.

When the bug is observed and the test fails, the following error message should be raised: "__BUG__HERE__"

<code>
{code}
</code>

<issue>
{self.issue_text}
</issue>
"""
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

        prompt = [
            f"""## Output

Output a completely new and self-contained test case, that is based on the original
test case code. 

Never use the @skipIf annotation.

## Python environment

Do not use Python features that are not available in this Python version.

{self.python_version}
"""
        ]

        return Editor(work_dir, trajectory_file=self.trajectory_file).test(
            issue="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /nocontext",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, test_file_name: Path, code: str) -> Optional[Patch]:
        content = extract_fenced_content(code)
        if not content:
            self.log("generate-test", "No changes detected")
            return None

        all_content = "\n".join(content)

        test_dir = path.dirname(test_file_name)
        os.makedirs(test_dir, exist_ok=True)
        with open(test_file_name, "w") as f:
            f.write(all_content)

        run(["git", "add", "-N", "."], check=True)

        self.log("generate-test", f"Generated test file: {test_file_name}")

        patch_str = filter_patch_include_tests(git_diff())

        if not patch_str:
            self.log("workflow/generate-test", "No changes detected")
            return None

        self.log("generate-test", f"Generated test patch:\n{patch_str}")

        return Patch(patch_str)
