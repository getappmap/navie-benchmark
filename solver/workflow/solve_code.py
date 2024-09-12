from solver.workflow.choose_code_files import choose_code_files
from solver.workflow.collect_appmap_context import collect_appmap_context_from_directory
from solver.workflow.generate_and_validate_code import CodePatchResult, Context as GenerateCodeContext, generate_and_validate_code
from solver.workflow.generate_code import GenerateCode
from solver.workflow.generate_plan import GeneratePlan
from solver.workflow.observe_test import ObserveTest, is_observable
from solver.workflow.patch import Patch
from solver.workflow.solve_base import SolveBase
from solver.workflow.solve_listener import TestStatus
from solver.workflow.work_dir import WorkDir
from solver.workflow.workflow_limits import WorkflowLimits
from swebench.harness.test_spec import TestSpec


import docker
import yaml


from pathlib import Path
from typing import Callable, List, Optional


class SolveCode(SolveBase):
    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: Path,
        docker_client: docker.DockerClient,
        test_spec: TestSpec,
        issue_text: str,
        limits: WorkflowLimits,
        edit_test_file: Optional[Path],
        test_patch: Optional[Patch],
        inverted_patch: Optional[Patch],
    ):
        super().__init__(log, work_dir, docker_client, test_spec, issue_text, limits)

        self.edit_test_file = edit_test_file
        self.test_patch = test_patch
        self.inverted_patch = inverted_patch

        self.observe_enabled = True
        self.observed_context: Optional[dict[str, str]] = None
        self.code_patch: Optional[Patch] = None

    def solve(self):
        if self.observe_enabled:
            self.observe_test()

        # TODO: Utilize runtime context, if available
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

    def observe_test(self):
        if not self.test_patch:
            self.log("workflow", "No test patch to observe")
            return None

        if not is_observable(self.log, self.test_spec):
            self.log("workflow", f"Instance {self.test_spec.instance_id} is not observable")

        observe_dir = self.work_dir.observe_test_patch()
        observe_test = ObserveTest(
            self.log,
            observe_dir.path,
            self.test_spec,
        )
        observe_test_result = observe_test.run(self.docker_client, self.test_patch)
        if (
            observe_test_result
            and observe_test_result.test_status == TestStatus.PASSED
            and observe_test_result.appmap_dir
        ):
            self.log(
                "workflow",
                f"Collecting appmap context from {observe_test_result.appmap_dir}",
            )
            self.observed_context = collect_appmap_context_from_directory(
                self.log, observe_test_result.appmap_dir
            )
            observe_appmap_files = list(
                observe_test_result.appmap_dir.rglob("*.appmap.json")
            )
            for listener in self.solve_listeners:
                listener.on_observe_test_patch(
                    observe_test_result.test_status,
                    observe_appmap_files,
                    self.observed_context,
                )
        else:
            self.log(
                "workflow",
                f"No appmap context collected. Test status: {observe_test_result.test_status if observe_test_result else "None"}",
            )

    def generate_plan(self, edit_code_file: Path) -> str:
        return GeneratePlan(
            self.log,
            self.work_dir,
            self.trajectory_file,
            self.issue_text,
        ).run(edit_code_file, self.observed_context)

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
