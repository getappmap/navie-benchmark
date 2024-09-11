from os import path
from pathlib import Path
import tarfile
from typing import Optional
import docker

from solver.harness.python_version import (
    python_version_for_test_spec,
    python_version_ok_for_test_spec,
)
from solver.workflow.solve_listener import TestStatus
from swebench.harness.test_spec import TestSpec

from solver.harness.make_run_commands import make_run_test_command
from solver.harness.make_test_directives import make_test_directives
from solver.workflow.execute_container import run_script_in_container
from solver.workflow.patch import Patch
from solver.workflow.run_test import DEFAULT_TIMEOUT, run_script_in_container


def is_observable(log, test_spec: TestSpec) -> bool:
    """
    Check if the test is observable.
    """

    if not python_version_ok_for_test_spec(test_spec, 3, 8):
        python_version = python_version_for_test_spec(test_spec)
        log(
            "observe-test",
            f"Python version {python_version} of {test_spec.instance_id} must be at least 3.8",
        )
        return False

    return True


class ObserveTestResult:
    def __init__(
        self,
        succeedeed: bool,
        test_status: Optional[TestStatus],
        test_output: Optional[str],
        appmap_dir: Optional[Path],
    ):
        self.succeedeed = succeedeed
        self.test_status = test_status
        self.test_output = test_output
        self.appmap_dir = appmap_dir


class ObserveTest:
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
        self.repo = test_spec.repo
        self.version = test_spec.version

    def run(
        self, docker_client: docker.DockerClient, test_patch: Patch
    ) -> Optional[ObserveTestResult]:
        """ "
        Run the test in the given patch and return the directory path where the AppMap data is stored.
        """

        def examine_appmap_dir() -> Optional[Path]:
            file_count_in_appmap_dir = len(
                list(appmap_extract_dir.rglob("*.appmap.json"))
            )
            self.log(
                "observe-test",
                f"Extracted {file_count_in_appmap_dir} AppMap data files to {appmap_extract_dir}",
            )
            if file_count_in_appmap_dir == 0:
                self.log(
                    "observe-test", f"No AppMap data found in {appmap_extract_dir}"
                )
                return None

            return appmap_extract_dir

        self.work_dir.mkdir(parents=True, exist_ok=True)

        appmap_extract_dir = self.work_dir / "appmap"
        if appmap_extract_dir.exists():
            self.log(
                "observe-test",
                f"AppMap data already exists in {appmap_extract_dir}, using cached data",
            )
            return ObserveTestResult(True, TestStatus.PASSED, None, appmap_extract_dir)

        if not is_observable(self.log, self.test_spec):
            self.log(
                "observe-test",
                f"Skipping {self.test_spec.instance_id} because it is not observable",
            )
            return None

        test_files = test_patch.list_files()

        if len(test_files) != 1:
            raise ValueError(f"Expected exactly one test file, got {len(test_files)}")

        test_file = test_files[0]

        self.log("observe-test", f"Running tests {test_file} in {self.work_dir}")

        test_directives = make_test_directives(self.repo, [test_file])
        run_test_command = " ".join(
            [
                make_run_test_command(self.repo, self.version, test_directives),
                "2>&1 | tee /tmp/run_test.log",
            ]
        )
        run_test_with_appmap_command = " ".join(
            ["APPMAP_DISPLAY_PARAMS=false appmap-python", run_test_command]
        )
        env_name = "testbed"
        repo_directory = f"/{env_name}"
        test_script_lines = [
            f"""#!/bin/bash

cd {repo_directory}
source /opt/miniconda3/bin/activate
conda activate {env_name}
pip install appmap

# Allow the test to fail and continue
set +e
"""
        ]

        test_script_lines.append("git apply /tmp/test.patch")
        test_script_lines.append(run_test_with_appmap_command)
        test_script_lines.append("tar -czf /tmp/appmap.tar.gz /testbed/tmp/appmap")

        test_script = "\n".join(test_script_lines)

        patch_file = path.join(self.work_dir, "test.patch")
        with open(patch_file, "w") as f:
            f.write(str(test_patch))

        volumes = {
            path.abspath(patch_file): {
                "bind": "/tmp/test.patch",
                "mode": "ro",
            },
        }
        appmap_tar_file = self.work_dir / "appmap.tar"
        appmap_extract_dir = self.work_dir / "appmap"
        appmap_extract_dir.mkdir(parents=True, exist_ok=True)

        def extract_appmap_data(container: docker.models.containers.Container):  # type: ignore
            # Tar and copy /testbed/tmp/appmap out of the container
            archive_generator, stat = container.get_archive("/testbed/tmp/appmap")
            with open(appmap_tar_file, "wb") as f:
                for chunk in archive_generator:
                    f.write(chunk)
            self.log("observe-test", f"Extracted AppMap data to {appmap_tar_file}")

        succeeded, test_status, test_output = run_script_in_container(
            self.log,
            docker_client,
            self.work_dir,
            self.test_spec,
            test_script,
            volumes,
            self.timeout,
            container_fn=extract_appmap_data,
        )
        if not succeeded:
            self.log("observe-test", f"Test failed with status {test_status}")
            self.log("observe-test", f"Test output: {test_output}")
            return ObserveTestResult(succeeded, test_status, test_output, None)

        if appmap_tar_file.exists():
            with tarfile.open(appmap_tar_file, "r") as tar:
                tar.extractall(path=appmap_extract_dir)

        return ObserveTestResult(True, test_status, test_output, examine_appmap_dir())
