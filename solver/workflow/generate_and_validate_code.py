from pathlib import Path
from typing import Callable, List, Optional
import docker

from swebench.harness.test_spec import TestSpec

from .workflow_limits import WorkflowLimits
from .run_test import RunTestResult
from .solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)

from .patch import Patch


class Context:
    def __init__(
        self,
        limits: WorkflowLimits,
        log: Callable[[str, str], None],
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        test_spec: TestSpec,
        solve_listeners: List[SolveListener],
    ):
        self.limits = limits
        self.log = log
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.test_spec = test_spec
        self.solve_listeners = solve_listeners


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


def empty_patch(file_name: Path) -> Patch:
    return Patch(
        f"""diff --git a/{file_name} b/{file_name}
index 0000000..0000000
--- a/{file_name}
+++ b/{file_name}
"""
    )


def generate_and_validate_code(
    context: Context,
    plan: str,
    generate_code: Callable[[str, int], Optional[Patch]],
    run_test: Callable[[Patch, List[Patch], int], RunTestResult],
    pass_to_pass_test_file: Optional[Path],
    test_patch: Optional[Patch],
    test_patch_inverted: Optional[Patch],
) -> Result:
    limit = context.limits.code_status_retry_limit

    code_patch = None
    code_patches = []
    attempt = 1
    while attempt <= limit and not code_patch:
        for listener in context.solve_listeners:
            listener.on_start_patch(PatchType.CODE)

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
                empty_patch_for_edit_test_file = empty_patch(pass_to_pass_test_file)

                run_test_result = run_test(
                    empty_patch_for_edit_test_file, [code_patch], attempt
                )
                pass_to_pass_test_status = run_test_result.test_status
                for listener in context.solve_listeners:
                    listener.on_run_test(
                        TestType.PASS_TO_PASS,
                        [code_patch],
                        empty_patch_for_edit_test_file,
                        pass_to_pass_test_status,
                    )

            if test_patch:
                context.log(
                    "generate-and-validate-code",
                    f"Running test patch for attempt {attempt}",
                )
                run_test_result = run_test(test_patch, [code_patch], attempt)
                test_patch_status = run_test_result.test_status
                for listener in context.solve_listeners:
                    listener.on_run_test(
                        TestType.PASS_TO_FAIL,
                        [code_patch],
                        test_patch,
                        test_patch_status,
                    )

            if test_patch_inverted:
                context.log(
                    "generate-and-validate-code",
                    f"Running inverted test patch for attempt {attempt}",
                )
                run_test_result = run_test(test_patch_inverted, [code_patch], attempt)
                inverted_patch_status = run_test_result.test_status

                for listener in context.solve_listeners:
                    listener.on_run_test(
                        TestType.FAIL_TO_PASS,
                        [code_patch],
                        test_patch_inverted,
                        inverted_patch_status,
                    )

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

            for listener in context.solve_listeners:
                listener.on_end_patch()

        attempt += 1

    return Result(
        code_patch,
        code_patches,
    )
