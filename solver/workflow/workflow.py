from os import listdir, path
from pathlib import Path
import subprocess
from typing import Callable, List, Optional

import docker

from navie.editor import Editor
from navie.fences import extract_fenced_content
from swebench.harness.test_spec import TestSpec

from .code_environment import DetectEnvironment, Environment
from .choose_test_file import choose_test_file
from .generate_code import GenerateCode
from .generate_test import (
    GenerateTest,
    test_failure_identity_string as build_test_failure_identity_string,
)
from .linter import Flake8Linter
from .lint_repair import LintRepairResult, lint_repair
from .patch import Patch
from .run_test import RunTest

FILE_LIMIT = 1
TEST_LINT_RETRY_LIMIT = 3
TEST_STATUS_RETRY_LIMIT = 3
CODE_LINT_RETRY_LIMIT = 5
CODE_STATUS_RETRY_LIMIT = 5

TEST_PASSED = 1
TEST_FAILED_WITH_SIGNAL_ERROR = 2
TEST_FAILED = 3


class WorkflowLimits:
    def __init__(
        self,
        file_limit: int = FILE_LIMIT,
        test_lint_retry_limit: int = TEST_LINT_RETRY_LIMIT,
        test_status_retry_limit: int = TEST_STATUS_RETRY_LIMIT,
        code_lint_retry_limit: int = CODE_LINT_RETRY_LIMIT,
        code_status_retry_limit: int = CODE_STATUS_RETRY_LIMIT,
    ):
        self.file_limit = file_limit
        self.test_lint_retry_limit = test_lint_retry_limit
        self.test_status_retry_limit = test_status_retry_limit
        self.code_lint_retry_limit = code_lint_retry_limit
        self.code_status_retry_limit = code_status_retry_limit

    def __str__(self):
        return f"file={self.file_limit}, test_lint_retry={self.test_lint_retry_limit}, test_status_retry={self.test_status_retry_limit}, code_lint_retry={self.code_lint_retry_limit}, code_status_retry={self.code_status_retry_limit}"

    @staticmethod
    def from_dict(data: dict):
        return WorkflowLimits(
            file_limit=data.get("file", FILE_LIMIT),
            test_lint_retry_limit=data.get("test_lint_retry", TEST_LINT_RETRY_LIMIT),
            test_status_retry_limit=data.get(
                "test_status_retry", TEST_STATUS_RETRY_LIMIT
            ),
            code_lint_retry_limit=data.get("code_lint_retry", CODE_LINT_RETRY_LIMIT),
            code_status_retry_limit=data.get(
                "code_status_retry", CODE_STATUS_RETRY_LIMIT
            ),
        )

    @staticmethod
    def limit_names():
        return [
            "file",
            "test_lint_retry",
            "test_status_retry",
            "code_lint_retry",
            "code_status_retry",
        ]


class Workflow:
    def __init__(
        self,
        log: callable,
        navie_work_dir: Path,
        environment: Environment,
        repo: str,
        version: str,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
    ):
        self.log = log
        self.navie_work_dir = navie_work_dir
        self.environment = environment
        self.repo = repo
        self.version = version
        self.test_spec = test_spec
        self.issue_text = issue_text
        self.limits = limits

        self.test_failure_identity_string = build_test_failure_identity_string(
            self.test_spec.instance_id
        )

        self.test_patch = None
        self.code_patch = None

    def run(self):
        plan = self.generate_plan()
        self.test_patch = self.generate_and_validate_test(plan)
        if self.test_patch:
            self.write_patch_file("test", self.test_patch)

        self.code_patch = self.generate_code(plan)
        if self.code_patch:
            self.write_patch_file("code", self.code_patch)

    def write_patch_file(self, patch_name: str, patch: Patch):
        patch_path = path.join(self.navie_work_dir, f"{patch_name}.patch")
        self.log(
            "workflow",
            f"Patch file generated to {patch_path}:\n{patch}",
        )
        with open(patch_path, "w") as f:
            f.write(str(patch))

    def generate_plan(self):
        editor = Editor(self.navie_work_dir)
        issue_text = f"""{self.issue_text}

In the Problem section, restate the issue in your own words. Retain as much detail as you can, but clean up the language and formatting.

Limit your solution to modify at most {self.limits.file_limit} file(s).

Do not plan specific code changes. Just design the solution.
"""

        return editor.plan(
            issue_text,
            options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    def generate_and_validate_test(self, plan) -> Optional[Patch]:
        limit = self.limits.test_status_retry_limit

        # Re-run test generation up to the limit, or until a test patch is available.
        attempt = 0
        test_patch = None
        while attempt < limit and not test_patch:
            test_patch = self.generate_test(plan)
            if test_patch:
                run_status = self.run_test()
                if run_status == TEST_PASSED:
                    self.log("workflow", "Test passed unexpectedly. Regenerating test.")
                    test_patch = None
                elif run_status == TEST_FAILED:
                    self.log("workflow", "Test failed without the signal error.")
                    test_patch = None
                elif run_status == TEST_FAILED_WITH_SIGNAL_ERROR:
                    self.log(
                        "workflow",
                        "Test failed with the signal error. Accepting test.",
                    )

            attempt += 1

        return test_patch

    def generate_test(self, code_plan) -> Optional[Patch]:
        self.clean_git_state()
        self.detect_environment()

        # Choose a test file
        editor = Editor(path.join(self.navie_work_dir, "generate-test"))

        edit_test_file = choose_test_file(self.log, editor.work_dir, self.issue_text)
        if not edit_test_file:
            return

        test_plan = editor.ask(
            f"""Modify {edit_test_file} to include a test for the following code.

The test should pass only when the issue is fixed as per the following plan:

<plan>
{code_plan}
</plan>

When the test fails, it should output the following string in the test failure message: {self.test_failure_identity_string}

Do not modify any code besides the named test file. 

Do not output actual code. Just design the test.
""",
            options=r"/noprojectinfo",
            question_name="test_plan",
            prompt="""## Output

Output a list of conditions that the code should satisfy to reproduce the issue.

Do not describe the conditions of the issue. Describe the conditions that the test
should check for to ensure that the issue is fixed.

The list of conditions should be in bullet list format.

* Do not modify any code besides the named test file
* Do not generate code. Just design the test.
* Ensure that if the issue is present in the code, the test FAILS.
* When the issue is fixed, the test should PASS.
""",
        )

        self.log("workflow", f"Test file: {edit_test_file}")
        self.log("workflow", f"Plan:\n{test_plan}")

        existing_test_files = "\n".join(listdir(Path(edit_test_file).parent))

        test_file_answer = editor.ask(
            f"""Generate a new test file name based on the existing test file name, that is relevant to the issue being fixed.

<base-file-name>
{edit_test_file}
</base-file-name>

Avoid using any of the following names, because these files already exist:

<existing-files>
{existing_test_files}
</existing-files>

<test-plan>
{test_plan}
</test-plan>

Output the file name, and nothing else. Do not include directory paths.

## Environment

Python version: {self.python_version}

Available packages: {self.packages}
""",
            options=r"/noprojectinfo",
            question_name="test_file_name",
        )
        test_file_name = (
            "\n".join(extract_fenced_content(test_file_answer)).strip().split("\n")[0]
        )
        test_file_path = str(Path(edit_test_file).parent / test_file_name)

        generator = GenerateTest(
            self.log, editor.work_dir, test_plan, self.python_version, self.packages
        )

        def generate(attempt, lint_errors: list = []):
            test_patch = generator.generate(attempt, lint_errors)
            return generator.apply(test_file_path, test_patch)

        lint_repair_result = self.lint_repair(
            "test", self.limits.test_lint_retry_limit, generate
        )

        test_patch = lint_repair_result.patch
        self.limits.test_status_retry_limit = max(
            0, self.limits.test_status_retry_limit - lint_repair_result.attempts
        )
        self.log(
            "generate-test",
            f"Test patch generated after {lint_repair_result.attempts} attempts. Setting test status retry limit to {self.limits.test_status_retry_limit}.",
        )

        self.clean_git_state()

        if test_patch:
            self.log(
                "generate-test",
                f"Patch file generated to :\n{test_patch}",
            )
            return test_patch

    def run_test(self) -> int:
        self.log("workflow", "Running test")
        run_test = RunTest(
            self.log, self.navie_work_dir, self.repo, self.version, self.test_spec
        )
        run_test_result = run_test.run(self.docker_client, self.test_patch)

        if run_test_result.succeeded:
            self.log("workflow", "Test passed unexpectedly")
            return TEST_PASSED
        else:
            self.log("workflow", "Test failed")
            contains_signal_error = run_test_result.contains_error(
                self.test_failure_identity_string
            )
            if contains_signal_error:
                self.log("workflow", "Test failure contains signal error.")
                return TEST_FAILED_WITH_SIGNAL_ERROR
            else:
                self.log("workflow", "Test failure does not contain signal error.")
                return TEST_FAILED

    def generate_code(self, plan) -> Optional[Patch]:
        self.clean_git_state()
        self.detect_environment()

        generator = GenerateCode(
            self.log,
            self.navie_work_dir,
            plan,
            self.python_version,
            self.packages,
            self.limits.file_limit,
        )

        def generate(attempt, lint_errors: list = []):
            code = generator.generate(attempt, lint_errors)
            return generator.apply(attempt, code)

        lint_repair_result = self.lint_repair(
            "code", self.limits.code_lint_retry_limit, generate
        )

        patch = lint_repair_result.patch
        self.limits.code_status_retry_limit = max(
            0, self.limits.code_status_retry_limit - lint_repair_result.attempts
        )
        self.log(
            "generate-code",
            f"Test patch generated after {lint_repair_result.attempts} attempts. Setting test status retry limit to {self.limits.code_status_retry_limit}.",
        )

        self.clean_git_state()

        return patch

    def lint_repair(
        self,
        step_name: str,
        max_retries: int,
        generator: Callable[[int, List[str]], None],
    ) -> LintRepairResult:
        linter = Flake8Linter()
        clean_repo = lambda: subprocess.run(["git", "checkout", "."], check=True)
        return lint_repair(
            self.log,
            step_name,
            max_retries,
            linter,
            generator,
            clean_repo,
        )

    def clean_git_state(self):
        first_commit_hash = (
            subprocess.check_output("git rev-list --max-parents=0 HEAD", shell=True)
            .strip()
            .decode("utf-8")
        )

        cmd = f"git reset --hard {first_commit_hash} && git clean -fdxq"
        subprocess.run(cmd, shell=True, check=True)

        self.log("workflow", "Cleaned git state")
