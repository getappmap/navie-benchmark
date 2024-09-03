from abc import abstractmethod
from enum import Enum
from pathlib import Path
from typing import List


from solver.workflow.patch import Patch


class PatchType(Enum):
    TEST = "test"
    TEST_INVERTED = "test_inverted"
    CODE = "code"


class TestType(Enum):
    PASS_TO_PASS = "pass_to_pass"
    PASS_TO_FAIL = "pass_to_fail"
    FAIL_TO_PASS = "fail_to_pass"


class TestStatus(Enum):
    FAILED = "FAILED"
    PASSED = "PASSED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class SolveListener:
    @abstractmethod
    def on_solve_start(self, navie_work_dir: Path):
        """Called when the solution process starts."""
        pass

    @abstractmethod
    def on_edit_test_file(self, edit_test_file: Path):
        """Called when the test file to be edited is determined."""
        pass

    @abstractmethod
    def on_start_patch(self, patch_name: PatchType):
        """Called when the process of creating a patch starts."""
        pass

    @abstractmethod
    def on_lint_repair(self, attempts: int, succeeded: bool):
        """Called after lint repair, indicating whether the lint repair succeeded or failed. Attempts may be 0, in which case the initial patch was lint-free."""
        pass

    @abstractmethod
    def on_end_patch(self):
        """Called to indicate that the in-progress patch has completed."""
        pass

    @abstractmethod
    def on_test_patch(self, patch: Patch):
        """Called when a test patch is generated."""
        pass

    @abstractmethod
    def on_test_inverted_patch(self, patch: Patch):
        """Called when an inverted test patch is generated."""
        pass

    @abstractmethod
    def on_code_patch(
        self,
        patch: Patch,
        pass_to_pass: bool,
        pass_to_fail: bool,
        fail_to_pass: bool,
        score: int,
    ):
        """Called when a code patch is generated."""
        pass

    @abstractmethod
    def on_run_test(
        self,
        test_type: TestType,
        code_patches: List[Patch],
        test_patch: Patch,
        test_status: TestStatus,
    ):
        """Called when running a test."""
        pass

    @abstractmethod
    def on_completed(self):
        """Called when the solution process completes, with or without error."""
        pass
