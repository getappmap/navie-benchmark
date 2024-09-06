from pathlib import Path
from typing import Callable, List, Optional, TypedDict

import docker

from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTestResult
from solver.workflow.solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)
from solver.workflow.workflow_limits import WorkflowLimits


class TestPatchResult(TypedDict):
    test_patch: Optional[Patch]
    inverted_patch: Optional[Patch]
    edit_test_file: Path


def is_optimal_test_patch(patch: TestPatchResult) -> bool:
    return not not (patch["test_patch"] and patch["inverted_patch"])


class Context:
    def __init__(
        self,
        limits: WorkflowLimits,
        log: Callable[[str, str], None],
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        solve_listeners: List[SolveListener],
    ):
        self.limits = limits
        self.log = log
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.solve_listeners = solve_listeners


def generate_test_for_test_file(
    context: Context,
    edit_test_file: Path,
    attempt: int,
    generate_test: Callable[[Path, int, List[str]], Optional[Patch]],
    run_test: Callable[[Path, Patch, List[Patch]], RunTestResult],
    invert_test: Callable[[Patch], Optional[Patch]],
) -> Optional[TestPatchResult]:

    limit = context.limits.test_status_retry_limit
    test_patch_result: Optional[TestPatchResult] = None
    inverted_patch: Optional[Patch] = None
    observed_errors = []

    while attempt <= limit and not test_patch_result:
        try:
            for listener in context.solve_listeners:
                listener.on_start_patch(PatchType.TEST)

            test_patch = generate_test(edit_test_file, attempt, observed_errors)
            if not test_patch:
                return None

            work_dir = edit_test_file.parent / f"generate-test-{attempt}"
            run_test_result = run_test(work_dir, test_patch, [])

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
            else:
                context.log("workflow", "Test did not pass. Discarding test.")
                observed_error = run_test_result.test_output
                if observed_error and len(observed_error) > 10000:
                    context.log(
                        "workflow",
                        f"Observed error is too long ({len(observed_error)} characters). Truncating it to 10000 characters.",
                    )
                    observed_error = observed_error[:10000] + "..."
                if observed_error:
                    observed_errors.append(observed_error)
                test_patch = None

            for listener in context.solve_listeners:
                listener.on_end_patch()

        finally:
            attempt += 1

        if test_patch:
            for listener in context.solve_listeners:
                listener.on_start_patch(PatchType.TEST_INVERTED)

            work_dir = edit_test_file.parent / f"invert-test-{attempt}"
            inverted_patch = invert_test(test_patch)
            if inverted_patch:
                inverted_run_test_result = run_test(work_dir, inverted_patch, [])
                inverted_test_status = inverted_run_test_result.test_status

                if inverted_test_status == TestStatus.PASSED:
                    context.log(
                        "workflow", "Inverted test passed; this should not happen."
                    )
                    inverted_patch = None
                elif (
                    inverted_run_test_result.test_output
                    and "__BUG__HERE__" in inverted_run_test_result.test_output
                ):
                    context.log(
                        "workflow",
                        "Inverted test failed with the expected marker error. Accepting test.",
                    )
                else:
                    context.log(
                        "workflow",
                        "Inverted test did not fail with the expected marker error. Discarding test.",
                    )
                    inverted_patch = None

            for listener in context.solve_listeners:
                listener.on_end_patch()

        return TestPatchResult(
            test_patch=test_patch,
            inverted_patch=inverted_patch,
            edit_test_file=edit_test_file,
        )


def generate_and_validate_test(
    context: Context,
    edit_test_files: List[Path],
    generate_test: Callable[[Path, int, List[str]], Optional[Patch]],
    run_test: Callable[[Path, Patch, List[Patch]], RunTestResult],
    invert_test: Callable[[Patch], Optional[Patch]],
) -> tuple[Optional[TestPatchResult], List[TestPatchResult]]:
    """
    Try up to WorkflowLimits.test_files_limit times to generate a test patch. Each attempt uses a base
    test file from edit_test_files. If a test patch is generated, it is run and validated. If the test
    patch is optimal, it is returned. Otherwise, the process is repeated with a different base test file.


    If an optimal test patch is found, it is returned along with all test patch results. If no optimal
    test patch is found, None is returned along with all test patch results.
    """
    limit = context.limits.test_files_limit

    test_patch_results: List[TestPatchResult] = []
    test_patch_result: Optional[TestPatchResult] = None
    attempt = 0
    while attempt <= limit and not test_patch_result:
        edit_test_file = edit_test_files[attempt % len(edit_test_files)]

        for listener in context.solve_listeners:
            listener.on_start_edit_test_file(edit_test_file)

        test = generate_test_for_test_file(
            context, edit_test_file, attempt, generate_test, run_test, invert_test
        )
        attempt += 1

        for listener in context.solve_listeners:
            listener.on_end_edit_test_file()

        if not test:
            continue

        test_patch_results.append(test)
        if is_optimal_test_patch(test):
            test_patch_result = test

    # Assign patches a score; one for patch, one for inverted patch
    def patch_score(patch: TestPatchResult) -> int:
        score = 0
        if patch["test_patch"]:
            score += 1
        if patch["inverted_patch"]:
            score += 1
        return score

    # Sort patches by score
    test_patch_results.sort(key=patch_score, reverse=True)

    return (test_patch_result, test_patch_results)
