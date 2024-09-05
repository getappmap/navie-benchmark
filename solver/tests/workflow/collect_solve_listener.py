from pathlib import Path
from typing import List, Optional
from solver.workflow.patch import Patch
from solver.workflow.solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)


def trim_patch(patch: Optional[Patch], max_chars=200) -> Optional[str]:
    if patch is None:
        return None

    return str(patch)[:max_chars]


class CollectSolveListener(SolveListener):
    def __init__(self):
        self.messages: List[tuple] = []

    def on_solve_start(self, navie_work_dir: Path):
        self.messages.append(("on_solve_start", navie_work_dir))

    def on_edit_test_file(self, edit_test_file: Path):
        self.messages.append(("on_edit_test_file", edit_test_file))

    def on_start_patch(self, patch_name: PatchType):
        self.messages.append(("on_start_patch", patch_name.value))

    def on_lint_repair(self, attempts: int, succeeded: bool):
        self.messages.append(("on_lint_repair", attempts, succeeded))

    def on_end_patch(self):
        self.messages.append(("on_end_patch",))

    def on_test_patch(self, patch: Patch):
        self.messages.append(("on_test_patch", trim_patch(patch)))

    def on_test_inverted_patch(self, patch: Patch):
        self.messages.append(("on_test_inverted_patch", trim_patch(patch)))

    def on_run_test(
        self,
        test_type: TestType,
        code_patches: List[Patch],
        test_patch: Optional[Patch],
        test_status: TestStatus,
    ):
        self.messages.append(
            (
                "on_run_test",
                test_type.value,
                [trim_patch(p) for p in code_patches],
                trim_patch(test_patch),
                test_status.value,
            )
        )

    def on_code_patch(
        self,
        patch: Patch,
        pass_to_pass: bool,
        pass_to_fail: bool,
        fail_to_pass: bool,
        score: Optional[int],
    ):
        self.messages.append(
            ("on_code_patch", patch, pass_to_pass, pass_to_fail, fail_to_pass, score)
        )

    def on_completed(self):
        self.messages.append(("on_completed",))

    def __str__(self) -> str:
        return "\n".join([str(message) for message in self.messages])
