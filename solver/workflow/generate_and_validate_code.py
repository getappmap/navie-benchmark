from pathlib import Path
from typing import Callable, List, Optional

from solver.workflow.run_test import RunTestResult
from swebench.harness.constants import TestStatus

from .patch import Patch


class Context:
    def __init__(self, limits, log, docker_client, repo, version, test_spec):
        self.limits = limits
        self.log = log
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.test_spec = test_spec


class CodePatchResult:
    def __init__(
        self,
        patch: Optional[Patch],
        pass_to_pass_test_status: Optional[TestStatus],
        test_patch_status: Optional[TestStatus],
        inverted_patch_status: Optional[TestStatus],
    ):
        self.patch = patch
        self.pass_to_pass_test_status = pass_to_pass_test_status
        self.test_patch_status = test_patch_status
        self.inverted_patch_status = inverted_patch_status

    def __repr__(self):
        return (
            f"CodePatchResult(patch={self.patch}, "
            f"pass_to_pass_test_status={self.pass_to_pass_test_status}, "
            f"test_patch_status={self.test_patch_status}, "
            f"inverted_patch_status={self.inverted_patch_status})"
        )

    def to_h(self) -> dict[str, str]:
        result = {}
        if self.patch:
            result["patch"] = str(self.patch)
        if self.pass_to_pass_test_status:
            result["pass_to_pass_test_status"] = self.pass_to_pass_test_status.value
        if self.test_patch_status:
            result["test_patch_status"] = self.test_patch_status.value
        if self.inverted_patch_status:
            result["inverted_patch_status"] = self.inverted_patch_status.value
        return result


class Result:
    def __init__(self, patch: Optional[Patch], code_patches: List[CodePatchResult]):
        self.patch = patch
        self.code_patches = code_patches


def generate_and_validate_code(
    context: Context,
    plan: str,
    generate_code: Callable[[str, int], Optional[Patch]],
    run_test: Callable[[str, int, Patch, List[Patch]], RunTestResult],
    pass_to_pass_test_file: Optional[Path],
    test_patch: Optional[Patch],
    test_patch_inverted: Optional[Patch],
) -> Result:
    limit = context.limits.code_status_retry_limit

    code_patch = None
    code_patches = []
    attempt = 1
    while attempt <= limit and not code_patch:
        code_patch = generate_code(plan, attempt)
        pass_to_pass_test_status = None
        test_patch_status = None
        inverted_patch_status = None
        if code_patch:
            if pass_to_pass_test_file:
                context.log(
                    "generate-and-validate-code",
                    f"Running pass-to-pass test for attempt {attempt}",
                )
                empty_patch_for_edit_test_file = Patch(
                    f"""diff --git a/{pass_to_pass_test_file} b/{pass_to_pass_test_file}
index 0000000..0000000
--- a/{pass_to_pass_test_file}
+++ b/{pass_to_pass_test_file}
"""
                )

                run_test_result = run_test(
                    "code", attempt, empty_patch_for_edit_test_file, [code_patch]
                )
                pass_to_pass_test_status = run_test_result.test_status

            if test_patch:
                context.log(
                    "generate-and-validate-code",
                    f"Running test patch for attempt {attempt}",
                )
                run_test_result = run_test("code", attempt, test_patch, [code_patch])
                test_patch_status = run_test_result.test_status

            if test_patch_inverted:
                context.log(
                    "generate-and-validate-code",
                    f"Running inverted test patch for attempt {attempt}",
                )
                run_test_result = run_test(
                    "code", attempt, test_patch_inverted, [code_patch]
                )
                inverted_patch_status = run_test_result.test_status

            code_patch_result = CodePatchResult(
                patch=code_patch,
                pass_to_pass_test_status=pass_to_pass_test_status,
                test_patch_status=test_patch_status,
                inverted_patch_status=inverted_patch_status,
            )

            code_patches.append(code_patch_result)

            if (
                pass_to_pass_test_status == TestStatus.PASSED
                and test_patch_status == TestStatus.FAILED
                and inverted_patch_status == TestStatus.PASSED
            ):
                context.log(
                    "generate-and-validate-code",
                    "Code patch succeeded in the pass-to-pass test, failed the test patch, and passed the inverted test patch. Accepting code patch.",
                )
            elif (
                pass_to_pass_test_status == TestStatus.PASSED
                and not test_patch
                and not test_patch_inverted
            ):
                context.log(
                    "generate-and-validate-code",
                    "Code patch succeeded the pass-to-pass test, and there are no test patches to try. Accepting code patch.",
                )
            else:
                context.log(
                    "generate-and-validate-code",
                    "Code patch is not optimal. Will look for a better patch.",
                )
                code_patch = None

        attempt += 1

    return Result(
        code_patch,
        code_patches,
    )
