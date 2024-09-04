from typing import TypedDict, Optional

from solver.workflow.solve_listener import SolveListener


class Solution(TypedDict):
    pass_to_pass_file: Optional[str]
    code_patch: Optional[str]
    test_patch: Optional[str]
    test_inverse_patch: Optional[str]
    num_llm_tokens: int
    elapsed_time: float
    test_generation_attempts: int
    code_generation_attempts: int
    pass_to_pass: bool
    pass_to_fail: bool
    fail_to_pass: bool
    score: int
