from os import path
from subprocess import run
from typing import Callable, Optional


from navie.editor import Editor
from navie.fences import extract_fenced_content

from .linter import generate_lint_error_avoidance_plan
from .patch import (
    Patch,
    filter_patch_include_tests,
    git_diff,
)


class GenerateTest:

    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: str,
        plan: str,
        python_version: str,
        packages: str,
    ):
        self.log = log
        self.work_dir = work_dir
        self.plan = plan
        self.python_version = python_version
        self.packages = packages

    # Generate a code change plan and return it as a string.
    # If lint_errors is provided, include prompting to avoid them.
    def generate(self, attempt: int, lint_errors: list = []) -> str:
        work_dir = path.join(self.work_dir, "test", str(attempt))

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
            f"""## Output

Output a completelly new and self-contained test case, that is based on the original
test case code. 

Remove all other test classes and functions aside from the one that is being generated.

Never use the @skipIf annotation.

## Python environment

Do not use Python features that are not available in this Python version.

Do not use any packages that are not available in this environment.

{self.python_version}

{self.packages}
"""
        ]

        return Editor(work_dir).test(
            issue="\n\n".join(plan),
            prompt="\n\n".join(prompt),
            options=r"/noprojectinfo",
        )

    # Apply code changes to the files in the current directory and return a patch.
    def apply(self, test_file_name: str, code: str) -> Optional[Patch]:
        content = extract_fenced_content(code)
        if not content:
            self.log("generate-test", "No changes detected")
            return None

        all_content = "\n".join(content)
        with open(test_file_name, "w") as f:
            f.write(all_content)

        run(["git", "add", "-N", "."], check=True)

        self.log("generate-test", f"Generated test file: {test_file_name}")

        patch_str = filter_patch_include_tests(git_diff())

        if not patch_str:
            self.log("workflow/generate-test", "No changes detected")
            return None

        return Patch(patch_str)
