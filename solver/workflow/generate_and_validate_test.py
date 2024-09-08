from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, TypedDict

import docker

from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTestResult
from solver.workflow.solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)
from solver.workflow.work_dir import WorkDir
from solver.workflow.workflow_limits import WorkflowLimits


class TestPatchResult(TypedDict):
    test_patch: Optional[Patch]
    inverted_patch: Optional[Patch]
    edit_test_file: Path


def is_optimal_test_patch(patch: Optional[TestPatchResult]) -> bool:
    if not patch:
        return False

    return True if patch["test_patch"] and patch["inverted_patch"] else False


# Assign patches a score; one for patch, one for inverted patch
def patch_score(patch: TestPatchResult) -> int:
    score = 0
    if patch["test_patch"]:
        score += 1
    if patch["inverted_patch"]:
        score += 1
    return score


class Context:
    def __init__(
        self,
        limits: WorkflowLimits,
        log: Callable[[str, str], None],
        work_dir: WorkDir,
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        solve_listeners: Sequence[SolveListener],
    ):
        self.limits = limits
        self.log = log
        self.work_dir = work_dir
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.solve_listeners = solve_listeners


def retry_generate_test(
    max_attempts: int,
    func: Callable[[int], List[TestPatchResult]],
) -> List[TestPatchResult]:
    """
    Try up to max_attempts times to generate an optimal test patch result.
    A test patch result consists of a test patch and an inverted test patch that
    pass, and fail, respectively. If an optimal test patch result is found, it is
    returned along with all test patch results. If no optimal test patch result is
    found, None is returned along with all test patch results.
    """
    accumulator: List[TestPatchResult] = []
    for attempt in range(1, max_attempts + 1):
        test_results = func(attempt)
        optimal_tests = [
            result for result in test_results if is_optimal_test_patch(result)
        ]
        if optimal_tests:
            return optimal_tests

        accumulator.extend(test_results)

    return accumulator


def validate_test_patch(
    context: Context,
    test_dir: WorkDir,
    test_patch: Patch,
    run_test: Callable[[WorkDir, Patch], RunTestResult],
) -> Tuple[bool, Optional[str]]:
    run_test_result = run_test(test_dir.run_test_patch(), test_patch)

    for listener in context.solve_listeners:
        listener.on_run_test(
            TestType.PASS_TO_FAIL,
            [],
            test_patch,
            run_test_result.test_status,
        )

    test_status = run_test_result.test_status
    if test_status == TestStatus.PASSED:
        context.log("workflow", "Test passed. Accepting test.")
        return True, None
    else:
        context.log("workflow", "Test did not pass. Discarding test.")
        observed_error = run_test_result.test_output
        if observed_error and len(observed_error) > 10000:
            context.log(
                "workflow",
                f"Observed error is too long ({len(observed_error)} characters). Truncating it to 10000 characters.",
            )
            observed_error = observed_error[:10000] + "..."

        return False, observed_error


def validate_test_inverted_patch(
    context: Context,
    work_dir: WorkDir,
    inverted_patch: Patch,
    run_test: Callable[[WorkDir, Patch], RunTestResult],
) -> bool:
    inverted_run_test_result = run_test(work_dir, inverted_patch)

    for listener in context.solve_listeners:
        listener.on_run_test(
            TestType.FAIL_TO_PASS,
            [],
            inverted_patch,
            inverted_run_test_result.test_status,
        )

    inverted_test_status = inverted_run_test_result.test_status

    if inverted_test_status == TestStatus.PASSED:
        context.log("workflow", "Inverted test passed; this should not happen.")
        return False
    elif inverted_test_status == TestStatus.FAILED and (
        inverted_run_test_result.test_output
        and "__BUG__HERE__" in inverted_run_test_result.test_output
    ):
        context.log(
            "workflow",
            "Inverted test failed with the expected marker error. Accepting test.",
        )
        return True
    else:
        marker_error_present = inverted_run_test_result.contains_error("__BUG__HERE__")
        context.log(
            "workflow",
            f"Inverted test resulted in status {inverted_test_status.value}.",
        )
        context.log(
            "workflow",
            f"Marker error present: {marker_error_present}.",
        )
        context.log(
            "workflow",
            "Inverted test did not FAIL with the expected marker error. Discarding test.",
        )
        return False


def generate_tests_for_test_file(
    context: Context,
    work_dir: WorkDir,
    edit_test_file: Path,
    generate_test: Callable[[WorkDir, Path, List[str]], Optional[Patch]],
    run_test: Callable[[WorkDir, Patch], RunTestResult],
    invert_test: Callable[[WorkDir, Patch], Optional[Patch]],
) -> List[TestPatchResult]:

    observed_errors = []

    def generate_test_and_inverted_patches(
        attempt: int,
    ) -> Tuple[Optional[Patch], Optional[Patch]]:
        test_dir = work_dir.test(attempt)

        def generate_test_patch() -> Optional[Patch]:
            for listener in context.solve_listeners:
                listener.on_start_patch(PatchType.TEST)

            try:
                test_patch = generate_test(test_dir, edit_test_file, observed_errors)
                if test_patch:
                    accept, observed_error = validate_test_patch(
                        context, test_dir, test_patch, run_test
                    )
                    if observed_error:
                        observed_errors.append(observed_error)

                    if not accept:
                        test_patch = None

                return test_patch
            finally:
                for listener in context.solve_listeners:
                    listener.on_end_patch()

        def generate_inverted_patch(test_patch: Patch) -> Optional[Patch]:
            for listener in context.solve_listeners:
                listener.on_start_patch(PatchType.TEST_INVERTED)

            try:
                inverted_patch = invert_test(test_dir.invert(), test_patch)
                if inverted_patch:
                    accept = validate_test_inverted_patch(
                        context, test_dir, inverted_patch, run_test
                    )
                    if not accept:
                        inverted_patch = None

                return inverted_patch
            finally:
                for listener in context.solve_listeners:
                    listener.on_end_patch()

        test_patch = generate_test_patch()
        inverted_patch = None
        if test_patch:
            inverted_patch = generate_inverted_patch(test_patch)

        return test_patch, inverted_patch

    def generate_patch_result(
        attempt: int,
    ) -> List[TestPatchResult]:
        test_patch, inverted_patch = generate_test_and_inverted_patches(attempt)
        if test_patch:
            return [
                {
                    "test_patch": test_patch,
                    "inverted_patch": inverted_patch,
                    "edit_test_file": edit_test_file,
                }
            ]

        return []

    return retry_generate_test(
        context.limits.test_status_retry_limit, generate_patch_result
    )


def generate_and_validate_test(
    context: Context,
    edit_test_files: List[Path],
    generate_test: Callable[[WorkDir, Path, List[str]], Optional[Patch]],
    run_test: Callable[[WorkDir, Patch], RunTestResult],
    invert_test: Callable[[WorkDir, Patch], Optional[Patch]],
) -> List[TestPatchResult]:
    """
    Try up to WorkflowLimits.test_files_limit times to generate a test patch. Each attempt uses a base
    test file from edit_test_files. If a test patch is generated, it is run and validated. If the test
    patch is optimal, it is returned. Otherwise, the process is repeated with a different base test file.


    If an optimal test patch is found, it is returned along with all test patch results. If no optimal
    test patch is found, None is returned along with all test patch results.
    """

    def attempt_generate_test(
        attempt: int,
    ) -> List[TestPatchResult]:
        edit_test_file = edit_test_files[(attempt - 1) % len(edit_test_files)]

        for listener in context.solve_listeners:
            listener.on_start_edit_test_file(edit_test_file)

        work_dir = context.work_dir.generate_test(edit_test_file, attempt)
        tests = generate_tests_for_test_file(
            context,
            work_dir,
            edit_test_file,
            generate_test,
            run_test,
            invert_test,
        )

        for listener in context.solve_listeners:
            listener.on_end_edit_test_file()

        return tests

    test_patch_results = retry_generate_test(
        context.limits.test_files_limit, attempt_generate_test
    )

    # Sort patches by score
    test_patch_results.sort(key=patch_score, reverse=True)

    return test_patch_results
