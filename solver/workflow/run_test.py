from os import path
from pathlib import Path
from typing import Optional

import docker

from solver.workflow.execute_container import (
    parse_test_status,
    read_test_output,
    run_script_in_container,
)
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
        test_spec: TestSpec,
        timeout=DEFAULT_TIMEOUT,
    ):
        self.log = log
        self.work_dir = work_dir
        self.timeout = timeout
        self.test_spec = test_spec
        self.code_patches = []

    @property
    def repo(self):
        return self.test_spec.repo

    @property
    def version(self):
        return self.test_spec.version

    def run(
        self, docker_client: docker.DockerClient, test_patch: Patch
    ) -> RunTestResult:
        self.work_dir.mkdir(parents=True, exist_ok=True)

        log_file = self.work_dir / "run_test.log"
        if log_file.exists():
            self.log(
                "run-test",
                f"Log file {log_file} already exists, using cached data. Will assume that the test exit code is 0.",
            )
            test_output = read_test_output(self.log, self.work_dir)
            test_status = parse_test_status(self.log, self.test_spec.repo, test_output)
            return RunTestResult(test_status, test_output, True)

        test_files = test_patch.list_files()

        if len(test_files) != 1:
            raise ValueError(f"Expected exactly one test file, got {len(test_files)}")

        test_file = test_files[0]

        self.log("run-test", f"Running tests {test_file} in {self.work_dir}")

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
        }
        for code_patch_index, code_patch in enumerate(self.code_patches):
            code_patch_file = path.join(self.work_dir, f"code_{code_patch_index}.patch")
            volumes[path.abspath(code_patch_file)] = {
                "bind": f"/tmp/code_{code_patch_index}.patch",
                "mode": "ro",
            }

        succeeded, test_status, test_output = run_script_in_container(
            self.log,
            docker_client,
            self.work_dir,
            self.test_spec,
            test_script,
            volumes,
            self.timeout,
        )

        if not test_status:
            test_status = parse_test_status(self.log, self.test_spec.repo, test_output)

        self.log(
            "run-test",
            f"Test {test_file} completed with status {test_status}.",
        )

        return RunTestResult(test_status, test_output, succeeded)
