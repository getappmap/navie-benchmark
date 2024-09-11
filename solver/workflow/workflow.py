from os import getcwd, listdir, path
from pathlib import Path
import subprocess
from typing import Callable, List, Optional

import docker
import yaml

from solver.harness.python_version import python_version_for_test_spec
from solver.workflow.collect_appmap_context import collect_appmap_context_from_directory
from solver.workflow.generate_plan import GeneratePlan
from solver.workflow.observe_test import ObserveTest, is_observable
from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.test_spec import TestSpec

from navie.editor import Editor
from navie.fences import extract_fenced_content

from .summarize_test_errors import summarize_test_errors
from .choose_code_files import choose_code_files
from .work_dir import WorkDir
from .workflow_limits import WorkflowLimits
from .solve_listener import SolveListener, TestStatus
from .generate_and_validate_code import (
    CodePatchResult,
    Context as GenerateCodeContext,
    empty_patch,
    generate_and_validate_code,
)
from .generate_and_validate_test import (
    TestPatchResult,
    Context as GenerateTestContext,
    generate_and_validate_test,
    is_optimal_test_patch,
    patch_score,
)
from .choose_test_file import choose_test_files
from .generate_code import GenerateCode
from .generate_test import GenerateTest
from .linter import Flake8Linter
from .lint_repair import LintRepairResult, lint_repair
from .patch import Patch
from .run_test import RunTest, RunTestResult

TEST_PASSED = 1
TEST_FAILED_WITH_SIGNAL_ERROR = 2
TEST_FAILED = 3


class Workflow:
    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: Path,
        docker_client: docker.DockerClient,
        repo: str,
        version: str,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
    ):
        self.log = log
        self.work_dir = WorkDir(work_dir)
        self.docker_client = docker_client
        self.repo = repo
        self.version = version
        self.test_spec = test_spec
        self.issue_text = issue_text
        self.limits = limits

        trajectory_file: Path = work_dir / "trajectory.jsonl"
        trajectory_file.parent.mkdir(parents=True, exist_ok=True)
        self.trajectory_file = str(trajectory_file)

        self.solve_listeners: List[SolveListener] = []

        self.edit_test_file: Optional[Path] = None
        self.test_patch: Optional[Patch] = None
        self.inverted_patch: Optional[Patch] = None
        self.code_patch: Optional[Patch] = None

    @property
    def test_command(self) -> str:
        return MAP_REPO_VERSION_TO_SPECS[self.repo][self.version]["test_cmd"]

    @property
    def python_version(self) -> str:
        return python_version_for_test_spec(self.test_spec)

    def run(self):
        for listener in self.solve_listeners:
            listener.on_solve_start(self.work_dir.path)

        edit_test_files = choose_test_files(
            self.log,
            self.work_dir,
            self.trajectory_file,
            self.issue_text,
            self.limits.test_files_limit,
        )
        if edit_test_files:
            generate_test_result = self.generate_and_validate_test(edit_test_files)
            if generate_test_result:
                for listener in self.solve_listeners:
                    listener.on_test_patch(
                        generate_test_result["edit_test_file"],
                        generate_test_result["test_patch"],
                        generate_test_result["inverted_patch"],
                    )

                if generate_test_result["edit_test_file"]:
                    self.edit_test_file = generate_test_result["edit_test_file"]
                if generate_test_result["test_patch"]:
                    self.test_patch = generate_test_result["test_patch"]
                    self.write_patch_file("test", self.test_patch)
                if generate_test_result["inverted_patch"]:
                    self.inverted_patch = generate_test_result["inverted_patch"]
                    self.write_patch_file("test-inverted", self.inverted_patch)
            else:
                self.log(
                    "workflow",
                    f"No test patch generated. Choosing first test file {edit_test_files[0]}",
                )
                self.edit_test_file = edit_test_files[0]

        code_files = choose_code_files(
            self.log,
            self.work_dir,
            self.trajectory_file,
            self.issue_text,
            self.limits.code_files_limit,
        )
        if not code_files:
            self.log("workflow", "No code files chosen")
            code_files = []

        def patch_score(code_patch_result: CodePatchResult) -> int:
            score = 0
            if code_patch_result.pass_to_pass_test_status == TestStatus.PASSED:
                score += 1
            if code_patch_result.test_patch_status == TestStatus.FAILED:
                score += 1
            if code_patch_result.inverted_patch_status == TestStatus.PASSED:
                score += 1
            return score

        generate_code_results: list[CodePatchResult] = []
        code_patch: Optional[Patch] = None
        for code_file in code_files:
            self.log("workflow", f"Evaluating code file: {code_file}")

            plan = self.generate_plan(code_file)

            generate_code_result = generate_and_validate_code(
                GenerateCodeContext(
                    self.limits,
                    self.log,
                    self.work_dir,
                    self.docker_client,
                    self.repo,
                    self.version,
                    self.test_spec,
                    self.solve_listeners,
                ),
                plan,
                self.generate_code,
                self.run_test,
                self.summarize_test_errors,
                self.edit_test_file,
                self.test_patch,
                self.inverted_patch,
            )

            if generate_code_result.patch:
                self.log(
                    "workflow", "Optimal code patch generated (for available tests)"
                )

                self.code_patch = generate_code_result.patch
                score = max(
                    [
                        patch_score(code_patch_result)
                        for code_patch_result in generate_code_result.code_patches
                    ]
                )
                for listener in self.solve_listeners:
                    listener.on_code_patch(
                        generate_code_result.patch,
                        True,
                        self.test_patch != None,
                        self.inverted_patch != None,
                        score,
                    )

                break

            generate_code_results.extend(generate_code_result.code_patches)

        self.log("workflow", "Choosing best patch")

        if not code_patch and generate_code_results:
            # Sort code_patches by score
            code_patches = list(generate_code_results)
            code_patches.sort(
                key=lambda patch: patch_score(patch),
                reverse=True,
            )
            code_patch_result = code_patches[0]
            assert code_patch_result.patch
            self.code_patch = code_patch_result.patch

            for listener in self.solve_listeners:
                listener.on_code_patch(
                    self.code_patch,
                    code_patch_result.pass_to_pass_test_status == TestStatus.PASSED,
                    code_patch_result.test_patch_status == TestStatus.FAILED,
                    code_patch_result.inverted_patch_status == TestStatus.PASSED,
                    patch_score(code_patches[0]),
                )

            with (self.work_dir.path / "code_patches.yml").open("w") as f:
                f.write(
                    yaml.dump(
                        [p.to_h() for p in code_patches],
                    )
                )

        if self.code_patch:
            self.write_patch_file("code", self.code_patch)
        else:
            self.log("workflow", "No code patches generated")

        for listener in self.solve_listeners:
            listener.on_completed()

    def write_patch_file(self, patch_name: str, patch: Patch):
        patch_path = self.work_dir.path / f"{patch_name}.patch"
        self.log("workflow", f"Patch file generated to {patch_path}")
        with patch_path.open("w") as f:
            f.write(str(patch))

    def generate_plan(self, edit_code_file: Path) -> str:
        work_dir = self.work_dir.plan()

        context: Optional[dict[str, str]] = None

        if self.edit_test_file and is_observable(self.log, self.test_spec):
            observe_dir = work_dir.observe()
            observe_test = ObserveTest(
                self.log,
                observe_dir.path,
                self.test_spec,
            )
            appmap_data_dir = observe_test.run(
                self.docker_client, empty_patch(self.edit_test_file)
            )

            if appmap_data_dir:
                context = collect_appmap_context_from_directory(
                    self.log, appmap_data_dir
                )

        return GeneratePlan(
            self.log,
            work_dir,
            self.trajectory_file,
            self.issue_text,
        ).run(edit_code_file, context)

    def generate_and_validate_test(
        self, edit_test_files: List[Path]
    ) -> Optional[TestPatchResult]:
        def notify_listeners(patch: TestPatchResult) -> TestPatchResult:
            for listener in self.solve_listeners:
                listener.on_test_patch(
                    patch["edit_test_file"],
                    patch["test_patch"],
                    patch["inverted_patch"],
                )
            return patch

        patches = generate_and_validate_test(
            GenerateTestContext(
                self.limits,
                self.log,
                self.work_dir,
                self.docker_client,
                self.repo,
                self.version,
                self.solve_listeners,
            ),
            edit_test_files,
            self.generate_test,
            self.run_test,
            self.invert_test,
        )
        optimal_patches = [patch for patch in patches if is_optimal_test_patch(patch)]
        if optimal_patches:
            patch = optimal_patches[0]
            self.log(
                "workflow",
                f"Optimal test patch generated for {patch['edit_test_file']}",
            )
            return notify_listeners(patch)

        if not patches:
            self.log("workflow", "No test patches generated")
            return None

        self.log(
            "workflow",
            f"Choosing best test patch from {len(patches)} available patches",
        )

        patches.sort(key=patch_score, reverse=True)

        self.log(
            "workflow",
            f"Best test patch generated for {patches[0]['edit_test_file']}",
        )
        return notify_listeners(patches[0])

    def invert_test(self, work_dir: WorkDir, test_patch: Patch) -> Optional[Patch]:
        self.log("workflow", "Inverting test")

        self.clean_git_state()

        test_file_name = test_patch.list_files()[0]
        # Modify test_file_name so that the base file name now includes "_inverted".
        test_file_path = Path(test_file_name).parent / (
            Path(test_file_name).stem + "_inverted" + Path(test_file_name).suffix
        )

        generator = GenerateTest(
            self.log,
            work_dir,
            self.trajectory_file,
            self.test_command,
            test_file_path,
            self.issue_text,
            [],
            self.python_version,
        )

        def generate(attempt: int, lint_errors: list[str] = []) -> Optional[Patch]:
            patch = generator.invert(str(test_patch), attempt, lint_errors)
            return generator.apply(test_file_path, patch)

        lint_repair_result = self.lint_repair(
            "invert-test", self.limits.test_lint_retry_limit, generate
        )
        self.clean_git_state()

        test_patch_inverted = lint_repair_result.patch
        if not test_patch_inverted:
            self.log("invert-test", "Inverted test patch is empty.")
            return

        self.log(
            "invert-test",
            f"Test patch inverted after {lint_repair_result.attempts} attempts.",
        )

        return test_patch_inverted

    def generate_test(
        self,
        work_dir: WorkDir,
        edit_test_file: Path,
        observed_errors: list,
    ) -> Optional[Patch]:
        self.clean_git_state()

        editor = Editor(
            work_dir.path_name,
            log_dir=self.work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        )

        self.log("workflow", f"Adapting test file: {edit_test_file}")

        existing_test_files = "\n".join(listdir(Path(edit_test_file).parent))

        test_file_answer = editor.ask(
            f"""Generate a new test file name for a test that will address the following issue:

<issue>
{self.issue_text}
</issue>

Avoid using any of the following names, because these files already exist:

<existing-files>
{existing_test_files}
</existing-files>

Output the file name, and nothing else. Do not include directory paths.

Do not include directory names in the file name. Just choose a base file name.

## Environment

Python version: {self.python_version}
""",
            options=r"/noprojectinfo /nocontext /noclassify",
            question_name="test_file_name",
        )
        test_file_name = (
            "\n".join(extract_fenced_content(test_file_answer)).strip().split("\n")[0]
        )
        test_base_file_name = Path(test_file_name).name
        if test_base_file_name != test_file_name:
            self.log(
                "generate-test",
                f"WARNING: The test file name {test_file_name} is different from the base file name {test_base_file_name}. The base file name will be used.",
            )
        test_file_path = Path(edit_test_file).parent / test_base_file_name

        generator = GenerateTest(
            self.log,
            work_dir,
            self.trajectory_file,
            self.test_command,
            test_file_path,
            self.issue_text,
            observed_errors,
            self.python_version,
        )

        def generate(attempt, lint_errors: list = []):
            test_patch = generator.generate(edit_test_file, attempt, lint_errors)
            return generator.apply(test_file_path, test_patch)

        lint_repair_result = self.lint_repair(
            "test", self.limits.test_lint_retry_limit, generate
        )

        test_patch = lint_repair_result.patch

        self.log(
            "generate-test",
            f"Test patch generated after {lint_repair_result.attempts} attempts.",
        )

        self.clean_git_state()

        return test_patch

    def run_test(
        self,
        work_dir: WorkDir,
        test_patch: Patch,
        code_patches: list[Patch] = [],
    ) -> RunTestResult:
        run_test = RunTest(
            self.log, work_dir.path, self.repo, self.version, self.test_spec
        )
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

    def generate_code(
        self, work_dir: WorkDir, plan: str, test_errors: List[str]
    ) -> Optional[Patch]:
        self.clean_git_state()

        generator = GenerateCode(
            self.log,
            work_dir,
            self.trajectory_file,
            plan,
            self.python_version,
            self.limits.file_limit,
        )

        def generate(attempt, lint_errors: List[str]):
            code = generator.generate(attempt, lint_errors, test_errors)
            return generator.apply(attempt, code)

        lint_repair_result = self.lint_repair(
            "code", self.limits.code_lint_retry_limit, generate
        )
        self.clean_git_state()

        patch = lint_repair_result.patch

        if not patch:
            self.log("generate-code", "Code patch is empty.")
            return

        self.log(
            "generate-code",
            f"Code patch generated after {lint_repair_result.attempts} attempts.",
        )

        return patch

    def lint_repair(
        self,
        step_name: str,
        max_retries: int,
        generator: Callable[[int, List[str]], Optional[Patch]],
    ) -> LintRepairResult:
        linter = Flake8Linter()

        def clean_repo():
            if not Workflow.in_git_controlled_source_dir():
                self.log("workflow", f"Current directory: {getcwd()}")
                self.log(
                    "workflow",
                    "It doesn't look like we are in an instance source directory. Not cleaning git repo.",
                )
                return

            subprocess.run(["git", "checkout", "."], check=True)

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

    def clean_git_state(self):
        if not Workflow.in_git_controlled_source_dir():
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
        subprocess.run(cmd, shell=True, check=True)

        self.log("workflow", "Cleaned git state")

    @staticmethod
    def in_git_controlled_source_dir():
        return Path(".git").exists() and path.split(getcwd())[-1] == "source"
