from pathlib import Path
from typing import TypedDict, Optional

from solver.workflow.patch import Patch


class Solution(TypedDict):
    instance_id: str
    edit_test_file: Optional[Path]
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
    code_patch_score: Optional[int]
    appmap_data_test_status: Optional[str]
    appmap_data_file_count: Optional[int]
    appmap_data_context_size: Optional[int]


SCORE_THRESHOLD = 2


def meets_score_threshold(code_patch_score: Optional[int]) -> bool:
    return code_patch_score is not None and code_patch_score >= SCORE_THRESHOLD
