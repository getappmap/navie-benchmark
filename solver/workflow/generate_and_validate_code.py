from pathlib import Path
from typing import Callable, List, Optional
import docker

from solver.workflow.work_dir import WorkDir
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
        work_dir: WorkDir,
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        test_spec: TestSpec,
        solve_listeners: List[SolveListener],
    ):
        self.limits = limits
        self.log = log
        self.work_dir = work_dir
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
"""
    )


def generate_and_validate_code(
    context: Context,
    plan: str,
    generate_code: Callable[[WorkDir, str, List[str]], Optional[Patch]],
    run_test: Callable[[WorkDir, Patch, List[Patch]], RunTestResult],
    summarize_test_errors: Callable[[WorkDir, str], str],
    pass_to_pass_test_file: Optional[Path],
    test_patch: Optional[Patch],
    test_patch_inverted: Optional[Patch],
) -> Result:
    def is_optimal_code_patch(result: CodePatchResult) -> bool:
        """
        Determine if a code patch is optimal for the available tests.
        If patch files are not available, then "optimality" can be less than
        it would strictly be if all tests were available.
        """

        def patch_is_optimal() -> bool:
            return result.patch is not None

        def pass_to_pass_test_is_optimal() -> bool:
            return (
                not pass_to_pass_test_file
                or result.pass_to_pass_test_status == TestStatus.PASSED
            )

        def test_patch_is_optimal() -> bool:
            return not test_patch or result.test_patch_status == TestStatus.FAILED

        def inverted_patch_is_optimal() -> bool:
            return (
                not test_patch_inverted
                or result.inverted_patch_status == TestStatus.PASSED
            )

        return (
            patch_is_optimal()
            and pass_to_pass_test_is_optimal()
            and test_patch_is_optimal()
            and inverted_patch_is_optimal()
        )

    def retry_generate_code(
        max_attempts: int,
        func: Callable[[int], List[CodePatchResult]],
    ) -> List[CodePatchResult]:
        """
        Try up to max_attempts times to generate an optimal code patch.
        """
        accumulator = []
        for attempt in range(1, max_attempts + 1):
            results = func(attempt)
            optimal_results = [
                result for result in results if is_optimal_code_patch(result)
            ]
            if optimal_results:
                return optimal_results

            accumulator.extend(results)
        return accumulator

    test_errors = set()

    def collect_errors(work_dir: WorkDir, run_test_result: RunTestResult):
        if run_test_result.test_status == TestStatus.ERROR:
            if run_test_result.test_output:
                errors = summarize_test_errors(work_dir, run_test_result.test_output)
                test_errors.add(errors)

    def generate_patch(attempt: int) -> List[CodePatchResult]:
        for listener in context.solve_listeners:
            listener.on_start_patch(PatchType.CODE)

        def notify_and_return(
            patch: Optional[CodePatchResult],
        ) -> List[CodePatchResult]:
            for listener in context.solve_listeners:
                listener.on_end_patch()

            return [code_patch_result] if patch else []

        generate_code_dir = context.work_dir.generate_code(attempt)
        code_patch = generate_code(generate_code_dir, plan, list(test_errors))
        if not code_patch:
            return notify_and_return(None)

        pass_to_pass_test_status = None
        test_patch_status = None
        inverted_patch_status = None
        if pass_to_pass_test_file:
            context.log(
                "generate-and-validate-code",
                f"Running pass-to-pass test for attempt {attempt}",
            )
            empty_patch_for_edit_test_file = empty_patch(pass_to_pass_test_file)

            work_dir = generate_code_dir.run_pass_to_pass()
            run_test_result = run_test(
                work_dir,
                empty_patch_for_edit_test_file,
                [code_patch],
            )
            pass_to_pass_test_status = run_test_result.test_status
            for listener in context.solve_listeners:
                listener.on_run_test(
                    TestType.PASS_TO_PASS,
                    [code_patch],
                    empty_patch_for_edit_test_file,
                    pass_to_pass_test_status,
                )

            collect_errors(work_dir, run_test_result)

        if test_patch:
            context.log(
                "generate-and-validate-code",
                f"Running test patch for attempt {attempt}",
            )
            work_dir = generate_code_dir.run_test_patch()
            run_test_result = run_test(work_dir, test_patch, [code_patch])
            test_patch_status = run_test_result.test_status
            for listener in context.solve_listeners:
                listener.on_run_test(
                    TestType.PASS_TO_FAIL,
                    [code_patch],
                    test_patch,
                    test_patch_status,
                )

            collect_errors(work_dir, run_test_result)

        if test_patch_inverted:
            context.log(
                "generate-and-validate-code",
                f"Running inverted test patch for attempt {attempt}",
            )

            work_dir = generate_code_dir.run_test_inverted_patch()
            run_test_result = run_test(
                work_dir,
                test_patch_inverted,
                [code_patch],
            )
            inverted_patch_status = run_test_result.test_status
            for listener in context.solve_listeners:
                listener.on_run_test(
                    TestType.FAIL_TO_PASS,
                    [code_patch],
                    test_patch_inverted,
                    inverted_patch_status,
                )

            collect_errors(work_dir, run_test_result)

        code_patch_result = CodePatchResult(
            patch=code_patch,
            pass_to_pass_test_status=pass_to_pass_test_status,
            test_patch_status=test_patch_status,
            inverted_patch_status=inverted_patch_status,
        )

        if (
            pass_to_pass_test_status == TestStatus.PASSED
            and test_patch_status == TestStatus.FAILED
            and inverted_patch_status == TestStatus.PASSED
        ):
            context.log(
                "generate-and-validate-code",
                "Code patch succeeded in the pass-to-pass test, failed the test patch, and passed the inverted test patch.",
            )
        elif (
            pass_to_pass_test_status == TestStatus.PASSED
            and not test_patch
            and not test_patch_inverted
        ):
            context.log(
                "generate-and-validate-code",
                "Code patch succeeded the pass-to-pass test, and there are no other tests to run.",
            )
        elif (
            pass_to_pass_test_status == TestStatus.PASSED
            or test_patch_status == TestStatus.FAILED
            or inverted_patch_status == TestStatus.PASSED
        ):
            context.log(
                "generate-and-validate-code",
                "Code patch passed at least one test, but not all.",
            )
        else:
            context.log(
                "generate-and-validate-code",
                "Code patch failed all tests.",
            )

        return notify_and_return(code_patch_result)

    code_patches = retry_generate_code(
        context.limits.code_status_retry_limit, generate_patch
    )

    optimal_patch = next(
        (patch for patch in code_patches if is_optimal_code_patch(patch)), None
    )

    return Result(
        optimal_patch.patch if optimal_patch else None,
        code_patches,
    )
