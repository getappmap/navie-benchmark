from os import path
import os
from pathlib import Path
import re
from subprocess import run
from typing import Callable, Optional


from navie.editor import Editor
from navie.fences import extract_fenced_content
from solver.workflow.work_dir import WorkDir

from .patch import (
    Patch,
    filter_patch_include_tests,
    git_diff,
)

# Maximum length of observed errors to include in the test case. Beyond this, the error is probably too verbose to
# be useful. This value preserves all error logs within 3 standard deviations above the observed data.
OBSERVED_ERROR_LENGTH_LIMIT = 100 * 1000


def strip_filename_comment(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return content

    first_line = lines[0]
    while re.match(r"^<!--.*-->$", first_line.strip()):
        lines = lines[1:]
        if not lines:
            break

        first_line = lines[0]

    return "\n".join(lines)


class GenerateTest:

    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: WorkDir,
        trajectory_file: str,
        test_command: str,
        test_file_path: Path,
        issue_text: str,
        observed_errors: list[str],
        python_version: str,
    ):
        self.log = log
        self.work_dir = work_dir
        self.trajectory_file = trajectory_file
        self.test_command = test_command
        self.test_file_path = test_file_path
        self.issue_text = issue_text
        self.observed_errors = observed_errors
        self.python_version = python_version

    # Generate a code change and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(
        self, edit_test_file: Path, attempt: int, lint_errors: list = []
    ) -> str:
        work_dir = self.work_dir.code(attempt)

        plan = [
            f"""Reproduce the following issue with a test case. Generate exactly
one test case that reproduces the issue.

<issue>
{self.issue_text}
</issue>

The test case should be based on the existing test case file: {edit_test_file}.

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
            observed_errors_str = "\n".join(
                [
                    err
                    for err in observed_errors_str.split("\n")
                    if not "whitespace" in err.lower()
                ]
            )
            if len(observed_errors_str) > OBSERVED_ERROR_LENGTH_LIMIT:
                observed_errors_str = (
                    observed_errors_str[:OBSERVED_ERROR_LENGTH_LIMIT] + "..."
                )

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

The generated test case should include only one test. It should not include duplication
of existing test cases.

Remove all other test classes and functions aside from the one that is being generated.

Never use the @skipIf annotation.

## Test framework

The user will use the following command to run the test. Try to design the test to be compatible
with this command line:

    {self.test_command}

Unless the test command explicitly loads and uses pytest, don't import pytest. 
You may utilize the unittest module. You may also utilize imports that are already
present in the test file that you are going to modify.

## Python environment

Do not use Python features that are not available in this Python version.

{self.python_version}
"""
        ]

        return Editor(
            work_dir.path_name,
            log_dir=work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        ).test(
            issue="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /noclassify",
        )

    # Invert the outcome of the test case, so that the test will now fail specifically
    # at the location where the issue was asserted.
    def invert(self, code: str, attempt: int, lint_errors: list = []) -> str:
        work_dir = self.work_dir.invert()

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

## Python version

Do not use Python features that are not available in this Python version.

{self.python_version}

Do not write conditional logic in the test that checks the Python version. The specific
version of Python that you need has been installed and configured for this test. The
test will only ever run against the specified Python version.
"""
        ]

        return Editor(
            work_dir.path_name,
            log_dir=work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        ).test(
            issue="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo /noclassify /nocontext",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, test_file_name: Path, code: str) -> Optional[Patch]:
        content = extract_fenced_content(code)
        content = [strip_filename_comment(content_item) for content_item in content]

        if not content:
            self.log("generate-test", "No changes detected")
            return None

        if test_file_name.is_dir():
            self.log(
                "generate-test", f"Test file name is a directory: {test_file_name}"
            )
            return None

        all_content = "\n".join(content)

        test_dir = path.dirname(test_file_name)
        if test_dir:
            os.makedirs(test_dir, exist_ok=True)
        with open(test_file_name, "w") as f:
            f.write(all_content)

        run(["git", "add", "-N", "."], check=True)

        self.log("generate-test", f"Generated test file: {test_file_name}")

        patch_str = filter_patch_include_tests(git_diff())

        if not patch_str:
            self.log("generate-test", "No changes detected")
            return None

        return Patch(patch_str)
