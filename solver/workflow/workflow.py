from os import getcwd, listdir, path
from pathlib import Path
import subprocess
from typing import Callable, List, Optional, Tuple, Union

import docker
import yaml

from swebench.harness.constants import TestStatus
from swebench.harness.test_spec import TestSpec

from navie.editor import Editor
from navie.fences import extract_fenced_content

from .generate_and_validate_code import (
    CodePatchResult,
    Context as GenerateCodeContext,
    generate_and_validate_code,
)
from .code_environment import Environment
from .choose_test_file import choose_test_file
from .generate_code import GenerateCode
from .generate_test import GenerateTest
from .linter import Flake8Linter
from .lint_repair import LintRepairResult, lint_repair
from .patch import Patch
from .run_test import RunTest, RunTestResult

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


class GenerateTestResult:
    def __init__(self, test_patch: Optional[Patch], inverted_patch: Optional[Patch]):
        self.test_patch = test_patch
        self.inverted_patch = inverted_patch


class Workflow:
    def __init__(
        self,
        log: Callable[[str, str], None],
        navie_work_dir: Path,
        environment: Environment,
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
    ):
        self.log = log
        self.navie_work_dir = navie_work_dir
        self.environment = environment
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.test_spec = test_spec
        self.issue_text = issue_text
        self.limits = limits

        self.edit_test_file: Optional[Path] = None
        self.test_patch: Optional[Patch] = None
        self.inverted_patch: Optional[Patch] = None
        self.code_patch: Optional[Patch] = None

    def run(self):
        generate_test_result = self.generate_and_validate_test()
        if generate_test_result.test_patch:
            self.test_patch = generate_test_result.test_patch
            self.write_patch_file("test", self.test_patch)
        if generate_test_result.inverted_patch:
            self.inverted_patch = generate_test_result.inverted_patch
            self.write_patch_file("test-inverted", self.inverted_patch)

        plan = self.generate_plan()

        generate_code_result = generate_and_validate_code(
            GenerateCodeContext(
                self.limits,
                self.log,
                self.docker_client,
                self.repo,
                self.version,
                self.test_spec,
            ),
            plan,
            self.generate_code,
            self.run_test,
            self.edit_test_file,
            self.test_patch,
            self.inverted_patch,
        )

        if generate_code_result.patch:
            self.log("workflow", "Optimal code patch generated (for available tests)")
            self.code_patch = generate_code_result.patch
        elif generate_code_result.code_patches:
            self.log("workflow", "Choosing best patch")

            def patch_score(code_patch_result: CodePatchResult) -> int:
                score = 0
                if code_patch_result.pass_to_pass_test_status == TestStatus.PASSED:
                    score += 1
                if code_patch_result.test_patch_status == TestStatus.FAILED:
                    score += 1
                if code_patch_result.inverted_patch_status == TestStatus.PASSED:
                    score += 1
                return score

            # Sort code_patches by score
            code_patches = list(generate_code_result.code_patches)
            code_patches.sort(
                key=lambda patch: patch_score(patch),
                reverse=True,
            )
            self.code_patch = code_patches[0].patch

            with open(path.join(self.navie_work_dir, "code_patches.yml"), "w") as f:
                f.write(
                    yaml.dump(
                        [p.to_h() for p in code_patches],
                    )
                )
        else:
            self.log("workflow", "No code patches generated")

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

    def generate_and_validate_test(self) -> GenerateTestResult:
        limit = self.limits.test_status_retry_limit
        observed_errors = []

        test_patch = None
        inverted_patch = None

        # Re-run test generation up to the limit, or until a test patch is available.
        attempt = 1
        while attempt <= limit and not test_patch:
            test_patch = self.generate_test(attempt, observed_errors)
            if test_patch:
                run_test_result = self.run_test("test", attempt, test_patch)
                test_status = run_test_result.test_status
                if test_status == TestStatus.PASSED:
                    self.log(
                        "workflow",
                        "Test passed. Accepting test.",
                    )
                else:
                    self.log(
                        "workflow",
                        "Test did not pass. Discarding test.",
                    )
                    observed_error = run_test_result.test_output
                    # Truncate it, if it's too long.
                    if observed_error and len(observed_error) > 10000:
                        self.log(
                            "workflow",
                            f"Observed error is too long ({len(observed_error)} characters). Truncating it to 10000 characters.",
                        )
                        observed_error = observed_error[:10000] + "..."
                    if observed_error:
                        observed_errors.append(observed_error)
                    test_patch = None

            attempt += 1

        if test_patch:
            # For fun, let's also invert the test, then run it and look for the marker error.
            inverted_patch = self.invert_test(test_patch)
            if inverted_patch:
                inverted_run_test_result = self.run_test(
                    "inverted-test", 1, inverted_patch
                )
                inverted_test_status = inverted_run_test_result.test_status

                if inverted_test_status == TestStatus.PASSED:
                    self.log(
                        "workflow",
                        "Inverted test passed; this should not happen.",
                    )
                    inverted_patch = None

                if (
                    inverted_run_test_result.test_output
                    and "__BUG__HERE__" in inverted_run_test_result.test_output
                ):
                    self.log(
                        "workflow",
                        "Inverted test failed with the expected marker error. Accepting test.",
                    )
                else:
                    self.log(
                        "workflow",
                        "Inverted test did not fail with the expected marker error. Discarding test.",
                    )
                    inverted_patch = None

        return GenerateTestResult(test_patch, inverted_patch)

    @staticmethod
    def generate_test_work_dir(navie_work_dir: Union[Path, str], attempt: int) -> Path:
        if isinstance(navie_work_dir, str):
            navie_work_dir = Path(navie_work_dir)

        return navie_work_dir / "generate-test" / str(attempt)

    @staticmethod
    def generate_code_work_dir(navie_work_dir: Union[Path, str], attempt: int) -> Path:
        if isinstance(navie_work_dir, str):
            navie_work_dir = Path(navie_work_dir)

        return navie_work_dir / "generate-code" / str(attempt)

    def invert_test(self, test_patch: Patch) -> Optional[Patch]:
        self.log("workflow", "Inverting test")

        self.clean_git_state()

        test_file_name = test_patch.list_files()[0]
        # Modify test_file_name so that the base file name now includes "_inverted".
        test_file_path = Path(test_file_name).parent / (
            Path(test_file_name).stem + "_inverted" + Path(test_file_name).suffix
        )

        generator = GenerateTest(
            self.log,
            self.navie_work_dir,
            test_file_path,
            self.issue_text,
            [],
            self.environment.python_version,
        )

        def generate(attempt: int, lint_errors: list[str] = []) -> Optional[Patch]:
            patch = generator.invert(str(test_patch), attempt, lint_errors)
            return generator.apply(test_file_path, patch)

        lint_repair_result = self.lint_repair(
            "invert-test", self.limits.test_lint_retry_limit, generate
        )
        self.clean_git_state()

        test_patch_inverted = lint_repair_result.patch
        if not test_patch_inverted:
            self.log("invert-test", "Inverted test patch is empty.")
            return

        self.log(
            "invert-test",
            f"Test patch inverted after {lint_repair_result.attempts} attempts.",
        )
        self.log(
            "invert-test",
            f"Inverted test patch:\n{test_patch_inverted}",
        )

        return test_patch_inverted

    def generate_test(self, attempt: int, observed_errors: list) -> Optional[Patch]:
        self.clean_git_state()

        editor = Editor(Workflow.generate_test_work_dir(self.navie_work_dir, attempt))

        edit_test_file = choose_test_file(self.log, editor.work_dir, self.issue_text)
        if not edit_test_file:
            return

        if not self.edit_test_file:
            self.edit_test_file = edit_test_file

        self.log("workflow", f"Test file to be modified: {edit_test_file}")

        existing_test_files = "\n".join(listdir(Path(edit_test_file).parent))

        test_file_answer = editor.ask(
            f"""Generate a new test file name for a test that will address the following issue:

<issue>
{self.issue_text}
</issue>

Avoid using any of the following names, because these files already exist:

<existing-files>
{existing_test_files}
</existing-files>

Output the file name, and nothing else. Do not include directory paths.

Do not include directory names in the file name. Just choose a base file name.

## Environment

Python version: {self.environment.python_version}

Available packages: {self.environment.packages}
""",
            options=r"/noprojectinfo /nocontext",
            question_name="test_file_name",
        )
        test_file_name = (
            "\n".join(extract_fenced_content(test_file_answer)).strip().split("\n")[0]
        )
        test_base_file_name = Path(test_file_name).name
        if test_base_file_name != test_file_name:
            self.log(
                "generate-test",
                f"WARNING: The test file name {test_file_name} is different from the base file name {test_base_file_name}. The base file name will be used.",
            )
        test_file_path = Path(edit_test_file).parent / test_base_file_name

        generator = GenerateTest(
            self.log,
            editor.work_dir,
            test_file_path,
            self.issue_text,
            observed_errors,
            self.environment.python_version,
        )

        def generate(attempt, lint_errors: list = []):
            test_patch = generator.generate(attempt, lint_errors)
            return generator.apply(test_file_path, test_patch)

        lint_repair_result = self.lint_repair(
            "test", self.limits.test_lint_retry_limit, generate
        )

        test_patch = lint_repair_result.patch

        self.log(
            "generate-test",
            f"Test patch generated after {lint_repair_result.attempts} attempts.",
        )

        self.clean_git_state()

        return test_patch

    def run_test(
        self,
        step,
        attempt: int,
        test_patch: Patch,
        code_patches: list[Patch] = [],
    ) -> RunTestResult:
        self.log("workflow", f"Running test for attempt {attempt}")
        work_dir = path.join(
            Workflow.generate_test_work_dir(
                self.navie_work_dir,
                attempt,
            ),
            step,
        )
        run_test = RunTest(self.log, work_dir, self.repo, self.version, self.test_spec)
        if code_patches:
            run_test.code_patches = code_patches
        return run_test.run(self.docker_client, test_patch)

    def generate_code(self, plan, attempt) -> Optional[Patch]:
        self.clean_git_state()

        work_dir = Workflow.generate_code_work_dir(self.navie_work_dir, attempt)

        generator = GenerateCode(
            self.log,
            work_dir,
            plan,
            self.environment.python_version,
            self.limits.file_limit,
        )

        def generate(attempt, lint_errors: list = []):
            code = generator.generate(attempt, lint_errors)
            return generator.apply(attempt, code)

        lint_repair_result = self.lint_repair(
            "code", self.limits.code_lint_retry_limit, generate
        )
        self.clean_git_state()

        patch = lint_repair_result.patch

        if not patch:
            self.log("generate-code", "Code patch is empty.")
            return

        self.log(
            "generate-code",
            f"Code patch generated after {lint_repair_result.attempts} attempts.",
        )

        return patch

    def lint_repair(
        self,
        step_name: str,
        max_retries: int,
        generator: Callable[[int, List[str]], Optional[Patch]],
    ) -> LintRepairResult:
        linter = Flake8Linter()

        def clean_repo():
            if not Workflow.in_git_controlled_source_dir():
                self.log("workflow", f"Current directory: {getcwd()}")
                self.log(
                    "workflow",
                    "It doesn't look like we are in an instance source directory. Not cleaning git repo.",
                )
                return

            subprocess.run(["git", "checkout", "."], check=True)

        return lint_repair(
            self.log,
            step_name,
            max_retries,
            linter,
            generator,
            clean_repo,
        )

    def clean_git_state(self):
        if not Workflow.in_git_controlled_source_dir():
            self.log("workflow", f"Current directory: {getcwd()}")
            self.log(
                "workflow",
                "It doesn't look like we are in an instance source directory. Not cleaning git state.",
            )
            return

        first_commit_hash = (
            subprocess.check_output("git rev-list --max-parents=0 HEAD", shell=True)
            .strip()
            .decode("utf-8")
        )

        cmd = f"git reset --hard {first_commit_hash} && git clean -fdxq"
        subprocess.run(cmd, shell=True, check=True)

        self.log("workflow", "Cleaned git state")

    @staticmethod
    def in_git_controlled_source_dir():
        return Path(".git").exists() and path.split(getcwd())[-1] == "source"
