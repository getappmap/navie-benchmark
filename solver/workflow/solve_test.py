from navie.editor import Editor
from navie.fences import extract_fenced_content
from solver.workflow.assert_behavior import AssertBehavior
from solver.workflow.choose_test_file import choose_test_files
from solver.workflow.generate_and_validate_test import (
    Context as GenerateTestContext,
    TestPatchResult,
    generate_and_validate_test,
    is_optimal_test_patch,
    patch_score,
)
from solver.workflow.generate_test import GenerateTest
from solver.workflow.patch import Patch
from solver.workflow.solve_base import SolveBase
from solver.workflow.validate_test import validate_test
from solver.workflow.work_dir import WorkDir
from solver.workflow.workflow_limits import WorkflowLimits
from swebench.harness.test_spec import TestSpec


import docker


from os import listdir
from pathlib import Path
from typing import Callable, List, Optional


class SolveTest(SolveBase):
    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: Path,
        docker_client: docker.DockerClient,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
    ):
        super().__init__(log, work_dir, docker_client, test_spec, issue_text, limits)

        self.edit_test_file: Optional[Path] = None
        self.test_patch: Optional[Patch] = None
        self.inverted_patch: Optional[Patch] = None

    def solve(self):
        edit_test_files = self.choose_test_files()
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

    def choose_test_files(self) -> List[Path] | None:
        def validate(work_dir: WorkDir, test_path: Path) -> bool:
            return validate_test(
                self.log, work_dir.path, self.docker_client, self.test_spec, test_path
            )

        return choose_test_files(
            self.log,
            self.work_dir,
            self.trajectory_file,
            self.issue_text,
            self.limits.test_files_limit,
            validate,
        )

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

        assertion_hint = AssertBehavior(
            self.log, self.work_dir, self.trajectory_file, self.issue_text
        ).assert_fixed()

        generator = GenerateTest(
            self.log,
            work_dir,
            self.trajectory_file,
            self.test_command,
            test_file_path,
            self.issue_text,
            assertion_hint,
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

        assertion_hint = AssertBehavior(
            self.log, self.work_dir, self.trajectory_file, self.issue_text
        ).assert_actual()

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
            assertion_hint,
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
