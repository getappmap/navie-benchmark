from os import path
import os
from pathlib import Path
from typing import List
import docker

from swebench.harness.test_spec import TestSpec
from solver.harness.make_run_commands import make_run_test_prep_commands
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.docker_build import build_instance_image


class Environment:
    def __init__(self, python_version: str, packages: str):
        self.python_version = python_version
        self.packages = packages


class DetectEnvironment:
    def __init__(
        self, log, work_dir: Path, repo: str, version: str, test_spec: TestSpec
    ):
        self.log = log
        self.work_dir = work_dir

        self.repo = repo
        self.version = version
        self.test_spec = test_spec

    def detect(self, docker_client: docker.DockerClient):
        self.log(
            "detect-environment",
            f"Detecting Python environment for {self.test_spec.instance_id}...",
        )

        environment_dir = path.join(self.work_dir, "environment")
        os.makedirs(environment_dir, exist_ok=True)

        python_version_file = path.join(environment_dir, "python_version.txt")
        packages_file = path.join(environment_dir, "packages.txt")

        if path.exists(python_version_file) and path.exists(packages_file):
            self.log("detect-environment", "Using cached environment...")
            with open(python_version_file, "r") as f:
                python_version = f.read().strip()
            with open(packages_file, "r") as f:
                packages = f.read()
            return Environment(python_version, packages)

        script_dir = path.join(self.work_dir, "scripts")
        os.makedirs(script_dir, exist_ok=True)

        build_instance_image(self.test_spec, docker_client, None, False)

        config = MAP_REPO_VERSION_TO_SPECS[self.test_spec.repo][self.test_spec.version]
        user = "root" if not config.get("execute_test_as_nonroot", False) else "nonroot"
        env_name = "testbed"

        prep_commands = make_run_test_prep_commands(
            config,
            env_name,
            custom_eval=False,
        )

        def make_script(prep_commands: List[str], output_command: str) -> str:
            script_lines = "\n".join(
                [f"    {line}" if line else "" for line in prep_commands]
            )
            return f"""#!/bin/bash

prep_commands_to_stderr() {{
  {{
{script_lines}
  }} 1>&2
}}

prep_commands_to_stderr

cd /{env_name}
source /opt/miniconda3/bin/activate
{output_command} 2>&1
"""

        def run_command(script_name: str, output_command) -> str:
            script_path = path.join(script_dir, script_name)

            script_body = make_script(prep_commands, output_command)

            with open(script_path, "w") as f:
                f.write(script_body)

            script_output = docker_client.containers.run(
                image=self.test_spec.instance_image_key,
                command=f"/tmp/{script_name}",
                entrypoint="/bin/bash",
                user=user,
                remove=True,
                stderr=False,
                stdout=True,
                platform=self.test_spec.platform,
                volumes={
                    path.abspath(script_path): {
                        "bind": f"/tmp/{script_name}",
                        "mode": "ro",
                    }
                },  # type: ignore
            )
            if not script_output:
                self.log(
                    "detect-environment",
                    f"No output from {script_name} for {self.test_spec.instance_id}",
                )
                return ""
            if not isinstance(script_output, bytes):
                self.log(
                    "detect-environment",
                    f"Output from {script_name} for {self.test_spec.instance_id} is not bytes",
                )
                return ""

            return script_output.decode("utf-8").strip()

        python_version = run_command("python_version.sh", "python --version")
        packages = run_command("list_packages.sh", "pip list")

        with open(python_version_file, "w") as f:
            f.write(python_version)
        with open(packages_file, "w") as f:
            f.write(packages)

        return Environment(python_version, packages)
