from os import path
import os
from pathlib import Path
from typing import Optional

import docker

from solver.workflow.execute_container import build_run_test_image, execute_container
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.log_parsers import MAP_REPO_TO_PARSER
from swebench.harness.test_spec import TestSpec

from ..harness.make_test_directives import make_test_directives
from ..harness.make_run_commands import (
    make_run_test_command,
)

from .patch import Patch
from .solve_listener import TestStatus


class RunTestResult:
    def __init__(
        self, test_status: TestStatus, test_output: Optional[str], run_succeeded: bool
    ):
        self.test_status = test_status
        self.test_output = test_output
        self.run_succeeded = run_succeeded

    def contains_error(self, error_str):
        return error_str in self.test_output

    def __str__(self):
        return f"RunTestResult(test_status={self.test_status}, run_succeeded={self.run_succeeded})"


DEFAULT_TIMEOUT = 120


class RunTest:
    def __init__(
        self,
        log,
        work_dir: Path,
        repo: str,
        version: str,
        test_spec: TestSpec,
        timeout=DEFAULT_TIMEOUT,
    ):
        self.log = log
        self.work_dir = work_dir
        self.timeout = timeout
        self.repo = repo
        self.version = version
        self.test_spec = test_spec
        self.code_patches = []

    def run(
        self, docker_client: docker.DockerClient, test_patch: Patch
    ) -> RunTestResult:
        test_files = test_patch.list_files()

        if len(test_files) != 1:
            raise ValueError(f"Expected exactly one test file, got {len(test_files)}")

        test_file = test_files[0]

        self.log("run-test", f"Running tests {test_file} in {self.work_dir}")

        run_test_image_name = build_run_test_image(
            self.log, docker_client, self.test_spec
        )

        config = MAP_REPO_VERSION_TO_SPECS[self.test_spec.repo][self.test_spec.version]
        user = "root" if not config.get("execute_test_as_nonroot", False) else "nonroot"
        test_directives = make_test_directives(self.repo, [test_file])
        run_test_command = " ".join(
            [
                make_run_test_command(self.repo, self.version, test_directives),
                "2>&1 | tee /tmp/run_test.log",
            ]
        )

        env_name = "testbed"
        repo_directory = f"/{env_name}"
        test_script_lines = [
            f"""#!/bin/bash

cd {repo_directory}
source /opt/miniconda3/bin/activate
conda activate {env_name}
"""
        ]

        for code_patch_index, code_patch in enumerate(self.code_patches):
            test_script_lines.append(f"git apply /tmp/code_{code_patch_index}.patch")

        test_script_lines.append("git apply /tmp/test.patch")
        test_script_lines.append(run_test_command)

        test_script = "\n".join(test_script_lines)

        os.makedirs(self.work_dir, exist_ok=True)

        script_file = path.join(self.work_dir, "run_test.sh")
        with open(script_file, "w") as f:
            f.write(str(test_script))
        patch_file = path.join(self.work_dir, "test.patch")
        with open(patch_file, "w") as f:
            f.write(str(test_patch))
        for code_patch_index, code_patch in enumerate(self.code_patches):
            code_patch_file = path.join(self.work_dir, f"code_{code_patch_index}.patch")
            with open(code_patch_file, "w") as f:
                f.write(str(code_patch))

        volumes = {
            path.abspath(patch_file): {
                "bind": "/tmp/test.patch",
                "mode": "ro",
            },
            path.abspath(script_file): {
                "bind": "/tmp/run_test.sh",
                "mode": "ro",
            },
        }
        for code_patch_index, code_patch in enumerate(self.code_patches):
            code_patch_file = path.join(self.work_dir, f"code_{code_patch_index}.patch")
            volumes[path.abspath(code_patch_file)] = {
                "bind": f"/tmp/code_{code_patch_index}.patch",
                "mode": "ro",
            }

        succeeded, test_status, test_output = execute_container(
            self.log,
            docker_client,
            run_test_image_name,
            self.test_spec,
            self.timeout,
            user,
            volumes,
            self.work_dir,
        )

        if not test_status:
            log_parser = MAP_REPO_TO_PARSER[self.repo]
            if not log_parser:
                raise ValueError(f"No log parser found for repo {self.repo}")

            test_status_dict: dict[str, str] = {}
            if test_output:
                test_status_dict.update(log_parser(test_output))

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
