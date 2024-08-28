from os import path
import os
from pathlib import Path

import docker

from solver.harness.build_extended_image import build_extended_image
from solver.ioutil import make_path
from solver.workflow.patch import Patch
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS, TestStatus
from swebench.harness.docker_build import build_instance_image
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER

from ..harness.make_test_directives import make_test_directives
from ..harness.make_run_commands import (
    make_run_test_command,
    make_run_test_prep_commands,
)


class RunTestResult:
    def __init__(self, test_status: TestStatus, test_output: str, run_succeeded: bool):
        self.test_status = test_status
        self.test_output = test_output
        self.run_succeeded = run_succeeded

    def contains_error(self, error_str):
        return error_str in self.test_output

    def __str__(self):
        return f"RunTestResult(test_status={self.test_status}, run_succeeded={self.run_succeeded})"


class RunTest:
    def __init__(self, log, work_dir, repo, version, test_spec):
        self.log = log
        self.work_dir = work_dir

        self.repo = repo
        self.version = version
        self.test_spec = test_spec

    def run(self, docker_client: docker.APIClient, test_patch: Patch) -> RunTestResult:
        test_files = test_patch.list_files()

        if len(test_files) != 1:
            raise ValueError(f"Expected exactly one test file, got {len(test_files)}")

        test_file = test_files[0]

        self.log("run-test", f"Running tests {test_file}...")

        instance_image_name = self.test_spec.instance_image_key.split(":")[0]
        run_test_image_name = ".".join([instance_image_name, "run_test"])

        build_instance_image(self.test_spec, docker_client, None, False)

        # Get configurations for how container should be created
        config = MAP_REPO_VERSION_TO_SPECS[self.test_spec.repo][self.test_spec.version]
        user = "root" if not config.get("execute_test_as_nonroot", False) else "nonroot"

        # Create the container
        self.log(
            "run-test",
            f"Creating run-test container for {self.test_spec.instance_id}...",
        )

        test_directives = make_test_directives(self.repo, [test_file])

        env_name = "testbed"
        repo_directory = f"/{env_name}"

        run_test_prep_commands = make_run_test_prep_commands(
            config,
            env_name,
        )

        # Build an image that extends the base image with the run_test_prep_commands already run
        instance_image = docker_client.images.get(self.test_spec.instance_image_key)
        instance_image_created_at = instance_image.attrs["Created"]

        # Docker build an image based on instance_image and extended with run_test_prep_commands
        test_image = None
        try:
            test_image = docker_client.images.get(run_test_image_name)
        except docker.errors.ImageNotFound:
            pass

        if test_image and test_image.attrs["Created"] < instance_image_created_at:
            self.log(
                "run-test",
                f"Rebuilding test image {run_test_image_name} because the instance image has been updated.",
            )
            test_image = None

        if not test_image:
            self.log(
                "run-test",
                f"Building test image {run_test_image_name}...",
            )
            test_image = build_extended_image(
                self.log,
                docker_client,
                instance_image,
                run_test_prep_commands,
                run_test_image_name,
            )

        run_test_command = " ".join(
            [
                make_run_test_command(self.repo, self.version, test_directives),
                "2>&1 | tee /tmp/run_test.log",
            ]
        )

        test_script = "\n".join(
            [
                "#!/bin/bash",
                "set -x",
                "",
            ]
            + [
                f"cd {repo_directory}",
                "source /opt/miniconda3/bin/activate",
                f"conda activate {env_name}",
                "git apply /tmp/test.patch",
                f"exec {run_test_command}",
            ]
        )

        os.makedirs(self.work_dir, exist_ok=True)
        error_log_file = path.join(self.work_dir, "run_test_error.log")
        log_file = path.join(self.work_dir, "run_test.log")
        with open(log_file, "w") as f:
            f.write("")
        script_file = path.join(self.work_dir, "run_test.sh")
        with open(script_file, "w") as f:
            f.write(str(test_script))
        patch_file = path.join(self.work_dir, "test.patch")
        with open(patch_file, "w") as f:
            f.write(str(test_patch))

        # Start the container
        self.log(
            "run-test",
            f"Running test {test_file}, with log available in {log_file}.",
        )

        succeeded = False
        try:
            docker_client.containers.run(
                image=run_test_image_name,
                command="/tmp/run_test.sh",
                entrypoint="/bin/bash",
                user=user,
                remove=True,
                platform=self.test_spec.platform,
                volumes={
                    path.abspath(patch_file): {
                        "bind": "/tmp/test.patch",
                        "mode": "ro",
                    },
                    path.abspath(script_file): {
                        "bind": "/tmp/run_test.sh",
                        "mode": "ro",
                    },
                    path.abspath(log_file): {
                        "bind": "/tmp/run_test.log",
                        "mode": "rw",
                    },
                },
            )
            succeeded = True
        except docker.errors.ContainerError as e:
            container_log = e.stderr.decode("utf-8")
            with open(error_log_file, "w") as f:
                f.write(container_log)
        except Exception as e:
            self.log("run-test", f"Unexpected error: {e}")
            with open(error_log_file, "w") as f:
                f.write(str(e))

        with open(log_file, "r") as f:
            test_output = f.read()

        log_parser = MAP_REPO_TO_PARSER[self.repo]
        test_status_dict = log_parser(test_output)

        # If the test status is not found, assume that the test was not run due to a setup error.
        if test_status_dict:
            test_status = TestStatus(test_status_dict.popitem()[1])
        else:
            self.log(
                "run-test",
                "No test status was detected in the output file",
            )
            test_status = TestStatus.ERROR

        self.log(
            "run-test",
            f"Test {test_file} completed with status {test_status}.",
        )

        return RunTestResult(test_status, test_output, succeeded)
