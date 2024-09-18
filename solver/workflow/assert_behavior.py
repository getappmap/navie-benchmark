from typing import Callable

from navie.editor import Editor

from solver.workflow.work_dir import WorkDir


class AssertBehavior:
    def __init__(
        self,
        log: Callable[[str, str], None],
        work_dir: WorkDir,
        trajectory_file: str,
        issue_text: str,
    ):
        self.log = log
        self.work_dir = work_dir
        self.trajectory_file = trajectory_file
        self.issue_text = issue_text

    def assert_actual(self) -> str:
        work_dir = self.work_dir.assert_actual()

        plan = [
            f"""Generate a Python assertion of the actual behavior of the code, as described in the following issue.

It's essential that you assert how the code is actually behaving in the reported issue, not how it would behave
if the issue was fixed.

<issue>
{self.issue_text}
</issue>

Generate only the assertion, not the entire test case.
"""
        ]
        return Editor(
            work_dir.path_name,
            log_dir=work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        ).generate(
            plan="\n\n".join(plan),
            options=r"/nocontext /noprojectinfo /noclassify",
        )

    def assert_fixed(self) -> str:
        work_dir = self.work_dir.assert_fixed()

        plan = [
            f"""Generate a Python assertion of the fixed behavior of the code, as described in the following issue.

It's essential that you assert how the fixed could should behave.

<issue>
{self.issue_text}
</issue>

Generate only the assertion, not the entire test case.
"""
        ]
        return Editor(
            work_dir.path_name,
            log_dir=work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        ).generate(
            plan="\n\n".join(plan),
            options=r"/nocontext /noprojectinfo /noclassify",
        )
