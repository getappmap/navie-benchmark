from json import dumps
from os import path
import os
from pathlib import Path
from typing import Callable, Optional
import docker

from solver.harness.build_extended_image import build_extended_image
from swebench.harness.test_spec import TestSpec
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER


from solver.harness.make_run_commands import make_run_test_prep_commands

from solver.workflow.solve_listener import TestStatus


def run_script_in_container(
    log,
    docker_client: docker.DockerClient,
    work_dir: Path,
    test_spec: TestSpec,
    script: str,
    volumes: dict[str, dict[str, str]],
    timeout: int,
    container_fn: Optional[Callable[[docker.models.containers.Container], None]] = None,
) -> tuple[bool, TestStatus | None, Optional[str]]:
    run_test_image_name = build_run_test_image(
        log,
        docker_client,
        test_spec,
    )

    config = MAP_REPO_VERSION_TO_SPECS[test_spec.repo][test_spec.version]
    user = "root" if not config.get("execute_test_as_nonroot", False) else "nonroot"

    os.makedirs(work_dir, exist_ok=True)

    script_file = path.join(work_dir, "run_test.sh")
    with open(script_file, "w") as f:
        f.write(str(script))

    volumes.update(
        {
            path.abspath(script_file): {
                "bind": "/tmp/run_test.sh",
                "mode": "ro",
            },
        }
    )

    return execute_container(
        log,
        docker_client,
        run_test_image_name,
        test_spec,
        timeout,
        user,
        volumes,
        work_dir,
        container_fn=container_fn,
    )


def read_test_output(log, work_dir: Path) -> Optional[str]:
    test_output_file = work_dir / "run_test.log"
    if not test_output_file.exists():
        log("read-test-output", f"Test output file {test_output_file} does not exist")
        return None

    with test_output_file.open("r") as f:
        return f.read()


def parse_test_status(log, repo: str, test_output: Optional[str]) -> TestStatus:
    log_parser = MAP_REPO_TO_PARSER[repo]
    if not log_parser:
        raise ValueError(f"No log parser found for repo {repo}")

    test_status_dict: dict[str, str] = {}
    if test_output:
        try:
            parsed_status = log_parser(test_output)
            if parsed_status:
                test_status_dict.update(parsed_status)
        except Exception as e:
            log("parse-test-status", f"Failed to parse test status: {e}")
            log("parse-test-status", f"Test output: {test_output}")

    # If the test status is not found, assume that the test was not run due to a setup error.
    if test_status_dict:
        test_status_str = ", ".join(
            f"{test_name}: {status}" for test_name, status in test_status_dict.items()
        )
        log(
            "parse-test-status",
            f"Test status: {test_status_str}",
        )

        def any_status(status_name: str) -> bool:
            return any(
                status for status in test_status_dict.values() if status == status_name
            )

        if any_status(TestStatus.ERROR.value):
            test_status = TestStatus.ERROR
        elif any_status(TestStatus.FAILED.value):
            test_status = TestStatus.FAILED
        else:
            test_status = TestStatus.PASSED

        log("parse-test-status", f"Overall test status: {test_status}")
    else:
        log(
            "run-test",
            "No test status was detected in the output file",
        )
        test_status = TestStatus.ERROR

    return test_status


def build_run_test_image(
    log: Callable,
    docker_client: docker.DockerClient,
    test_spec: TestSpec,
) -> str:
    instance_image_name = test_spec.instance_image_key.split(":")[0]
    run_test_image_name = ".".join([instance_image_name, "run_test"])

    instance_image = docker_client.images.get(test_spec.instance_image_key)
    instance_image_created_at = instance_image.attrs["Created"]

    # Docker build an image based on instance_image and extended with run_test_prep_commands
    test_image = None
    try:
        test_image = docker_client.images.get(run_test_image_name)
    except docker.errors.ImageNotFound:
        pass

    if test_image and test_image.attrs["Created"] < instance_image_created_at:
        log(
            "build-test-image",
            f"Rebuilding test image {run_test_image_name} because the instance image has been updated.",
        )
        test_image = None

    if not test_image:
        log(
            "build-test-image",
            f"Building test image {run_test_image_name}...",
        )
        run_test_prep_commands = make_run_test_prep_commands(
            MAP_REPO_VERSION_TO_SPECS[test_spec.repo][test_spec.version],
            "testbed",
        )
        build_extended_image(
            log,
            docker_client,
            instance_image,
            run_test_prep_commands,
            run_test_image_name,
        )

    return run_test_image_name


def execute_container(
    log: Callable,
    docker_client: docker.DockerClient,
    run_test_image_name: str,
    test_spec: TestSpec,
    timeout: int,
    user: str,
    volumes: dict,
    work_dir: Path,
    container_fn: Optional[Callable[[docker.models.containers.Container], None]] = None,
) -> tuple[bool, Optional[TestStatus], Optional[str]]:

    work_dir.mkdir(parents=True, exist_ok=True)

    error_log_file = work_dir / "run_test_error.log"
    log_file = work_dir / "run_test.log"
    image_name_file = work_dir / "image_name"
    volumes_file = work_dir / "volumes.json"

    with image_name_file.open("w") as f:
        f.write(str(run_test_image_name))

    with volumes_file.open("w") as f:
        f.write(dumps(volumes, indent=2))

    container = None
    succeeded = False
    test_status = None
    test_output = None
    try:
        container = docker_client.containers.run(
            image=run_test_image_name,
            command="/tmp/run_test.sh",
            entrypoint="/bin/bash",
            user=user,
            detach=True,
            platform=test_spec.platform,
            volumes=volumes,  # type: ignore
        )
        result = container.wait(timeout=timeout)

        exit_code = result["StatusCode"]
        if exit_code == 0:
            succeeded = True
    except Exception as e:
        log("execute-container", f"{e.__class__.__name__}: {e}")
        test_status = TestStatus.ERROR
        with error_log_file.open("w") as f:
            f.write(str(e))

    if container:
        try:
            test_output = container.logs().decode("utf-8")

            if container_fn:
                container_fn(container)

            container.remove()
        except Exception as e:
            log("execute-container", f"Failed to get logs and shut down container: {e}")

    if test_output:
        log("execute-container", f"Saved output to log file: {log_file}")
        with log_file.open("w") as f:
            f.write(test_output)

    return succeeded, test_status, test_output
