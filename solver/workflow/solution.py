from typing import TypedDict, Optional

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
    code_patch_score: Optional[int]
    appmap_data_test_status: Optional[str]
    appmap_data_file_count: Optional[int]
    appmap_data_context_size: Optional[int]
