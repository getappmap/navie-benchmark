from json import dumps
from pathlib import Path
from typing import Callable, Optional
import docker

from solver.harness.build_extended_image import build_extended_image
from swebench.harness.test_spec import TestSpec
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS

from solver.harness.make_run_commands import make_run_test_prep_commands

from solver.workflow.solve_listener import TestStatus


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
            container.remove()
        except Exception as e:
            log("execute-container", f"Failed to get logs and shut down container: {e}")

    if test_output:
        log("execute-container", f"Saved output to log file: {log_file}")
        with log_file.open("w") as f:
            f.write(test_output)

    return succeeded, test_status, test_output
