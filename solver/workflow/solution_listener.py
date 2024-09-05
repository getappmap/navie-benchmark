from enum import Enum
import json
from typing import TypedDict, Optional, List, cast
from pathlib import Path
from time import time

from solver.workflow.solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)
from solver.workflow.patch import Patch


class Solution(TypedDict):
    instance_id: str
    code_patch: Optional[Patch]
    test_patch: Optional[Patch]
    test_inverted_patch: Optional[Patch]
    num_sent_chars: int
    num_received_chars: int
    elapsed_time: float
    lint_repair_count: int
    test_generation_attempts: int
    code_generation_attempts: int
    pass_to_pass: bool
    pass_to_fail: bool
    fail_to_pass: bool
    code_patch_score: int


def solution_to_plain_types(solution: Solution) -> dict:
    # Convert all Patch and Path objects to strings
    solution_attrs = solution.copy()
    for key, value in solution_attrs.items():
        if isinstance(value, (Patch, Path)):
            solution_attrs[key] = str(value)
    return cast(dict, solution_attrs)


class SolutionListener(SolveListener):
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.navie_work_dir: Optional[Path] = None
        self.test_generation_attempts = 0
        self.test_inverted_generation_attempts = 0
        self.code_generation_attempts = 0
        self.edit_test_file: Optional[Path] = None
        self.test_patch: Optional[Patch] = None
        self.test_inverted_patch: Optional[Patch] = None
        self.code_patch: Optional[Patch] = None
        self.pass_to_pass: bool = False
        self.pass_to_fail: bool = False
        self.fail_to_pass: bool = False

        self.lint_repair_count: int = 0
        self.patch_name_in_progress: Optional[PatchType] = None

    def build_solution(self) -> Solution:
        assert self.navie_work_dir
        assert self.start_time
        assert self.end_time

        (num_sent_chars, num_received_chars) = SolutionListener.count_llm_chars(
            self.navie_work_dir / "trajectory.jsonl"
        )

        elapsed_time = self.end_time - self.start_time

        return Solution(
            code_patch=self.code_patch,
            test_patch=self.test_patch,
            test_inverted_patch=self.test_inverted_patch,
            num_sent_chars=num_sent_chars,
            num_received_chars=num_received_chars,
            elapsed_time=elapsed_time,
            lint_repair_count=self.lint_repair_count,
            test_generation_attempts=self.test_generation_attempts,
            code_generation_attempts=self.code_generation_attempts,
            pass_to_pass=self.pass_to_pass,
            pass_to_fail=self.pass_to_fail,
            fail_to_pass=self.fail_to_pass,
            code_patch_score=self.score,
        )

    @staticmethod
    def count_llm_chars(trajectory_file: Path) -> tuple[int, int]:
        if not trajectory_file.exists():
            print(f"WARNING - Trajectory file {trajectory_file} does not exist.")
            return (0, 0)

        num_sent_chars = 0
        num_received_chars = 0
        with open(trajectory_file) as f:
            record = f.readlines()
            for i, line in enumerate(record):
                record = json.loads(line)
                if record["type"] == "sent":
                    num_sent_chars += len(record["message"]["content"])
                elif record["type"] == "received":
                    num_received_chars += len(record["message"]["content"])

        return (num_sent_chars, num_received_chars)

    def on_solve_start(self, navie_work_dir: Path):
        self.navie_work_dir = navie_work_dir
        self.start_time = time()

    def on_edit_test_file(self, edit_test_file: Path):
        self.edit_test_file = edit_test_file

    def on_start_patch(self, patch_name: PatchType):
        self.patch_name_in_progress = patch_name

        if patch_name == PatchType.TEST:
            self.test_generation_attempts += 1
        elif patch_name == PatchType.TEST_INVERTED:
            self.test_inverted_generation_attempts += 1
        elif patch_name == PatchType.CODE:
            self.code_generation_attempts += 1

    def on_lint_repair(self, attempts: int, succeeded: bool):
        self.lint_repair_count += attempts - 1

    def on_end_patch(self):
        self.patch_name_in_progress = None

    def on_test_patch(self, patch: Patch):
        self.test_patch = patch

    def on_test_inverted_patch(self, patch: Patch):
        self.test_inverted_patch = patch

    def on_code_patch(
        self,
        patch: Patch,
        pass_to_pass: bool,
        pass_to_fail: bool,
        fail_to_pass: bool,
        score: int,
    ):
        self.code_patch = patch
        self.pass_to_pass = pass_to_pass
        self.pass_to_fail = pass_to_fail
        self.fail_to_pass = fail_to_pass
        self.score = score

    def on_run_test(
        self,
        test_type: TestType,
        code_patches: List[Patch],
        test_patch: Patch,
        test_status: TestStatus,
    ):
        self.test_type_in_progress = test_type

    def on_completed(self):
        self.end_time = time()