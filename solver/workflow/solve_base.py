from solver.harness.python_version import python_version_for_test_spec
from solver.workflow.lint_repair import LintRepairResult, lint_repair
from solver.workflow.linter import Flake8Linter
from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTest, RunTestResult
from solver.workflow.solve_listener import SolveListener
from solver.workflow.summarize_test_errors import summarize_test_errors
from solver.workflow.work_dir import WorkDir
from solver.workflow.workflow_limits import WorkflowLimits
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.test_spec import TestSpec


import docker


import subprocess
from os import getcwd, path
from pathlib import Path
from typing import Callable, List, Optional


class SolveBase:
    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: Path,
        docker_client: docker.DockerClient,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
    ):
        self.log = log
        self.work_dir = WorkDir(work_dir)
        self.docker_client = docker_client
        self.test_spec = test_spec
        self.issue_text = issue_text
        self.limits = limits

        trajectory_file: Path = work_dir / "trajectory.jsonl"
        trajectory_file.parent.mkdir(parents=True, exist_ok=True)
        self.trajectory_file = str(trajectory_file)

        self.solve_listeners: List[SolveListener] = []

        self.code_patch: Optional[Patch] = None
        self.observed_context: Optional[dict[str, str]] = None

    @property
    def repo(self) -> str:
        return self.test_spec.repo

    @property
    def version(self) -> str:
        return self.test_spec.version

    @property
    def test_command(self) -> str:
        return MAP_REPO_VERSION_TO_SPECS[self.repo][self.version]["test_cmd"]

    @property
    def python_version(self) -> str:
        return python_version_for_test_spec(self.test_spec)

    def run_test(
        self,
        work_dir: WorkDir,
        test_patch: Patch,
        code_patches: list[Patch] = [],
    ) -> RunTestResult:
        run_test = RunTest(self.log, work_dir.path, self.test_spec)
        if code_patches:
            run_test.code_patches = code_patches
        return run_test.run(self.docker_client, test_patch)

    def summarize_test_errors(self, work_dir: WorkDir, test_output: str) -> str:
        return summarize_test_errors(
            self.log,
            work_dir,
            self.trajectory_file,
            test_output,
        )

    def write_patch_file(self, patch_name: str, patch: Patch):
        patch_path = self.work_dir.path / f"{patch_name}.patch"
        self.log("workflow", f"Patch file generated to {patch_path}")
        with patch_path.open("w") as f:
            f.write(str(patch))

    def clean_git_state(self):
        if not SolveBase.in_git_controlled_source_dir():
            self.log("workflow", f"Current directory: {getcwd()}")
            self.log(
                "workflow",
                "It doesn't look like we are in an instance source directory. Not cleaning git state.",
            )
            return

        first_commit_hash = (
            subprocess.check_output("git rev-list --max-parents=0 HEAD", shell=True)
            .strip()
            .decode("utf-8")
        )

        cmd = f"git reset --hard {first_commit_hash} && git clean -fdxq"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)

        self.log("workflow", "Cleaned git state")

    def lint_repair(
        self,
        step_name: str,
        max_retries: int,
        generator: Callable[[int, List[str]], Optional[Patch]],
    ) -> LintRepairResult:
        linter = Flake8Linter()

        def clean_repo():
            if not SolveBase.in_git_controlled_source_dir():
                self.log("workflow", f"Current directory: {getcwd()}")
                self.log(
                    "workflow",
                    "It doesn't look like we are in an instance source directory. Not cleaning git repo.",
                )
                return

            subprocess.run(["git", "checkout", "."], check=True, capture_output=True)

        lint_repair_result = lint_repair(
            self.log,
            step_name,
            max_retries,
            linter,
            generator,
            clean_repo,
        )

        for listener in self.solve_listeners:
            listener.on_lint_repair(
                lint_repair_result.attempts, lint_repair_result.patch != None
            )

        return lint_repair_result

    @staticmethod
    def in_git_controlled_source_dir():
        return Path(".git").exists() and path.split(getcwd())[-1] == "source"
