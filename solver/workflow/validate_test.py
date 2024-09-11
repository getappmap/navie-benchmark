from pathlib import Path
import docker

from solver.workflow.generate_and_validate_code import empty_patch
from solver.workflow.solve_listener import TestStatus
from swebench.harness.test_spec import TestSpec

from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTest


def validate_test(
    log,
    work_dir: Path,
    docker_client: docker.DockerClient,
    test_spec: TestSpec,
    test_path: Path,
) -> bool:
    """
    Validate a test patch.
    """

    run_test = RunTest(
        log,
        work_dir,
        test_spec,
    )
    run_test_result = run_test.run(docker_client, empty_patch(test_path))
    return run_test_result.test_status == TestStatus.PASSED
