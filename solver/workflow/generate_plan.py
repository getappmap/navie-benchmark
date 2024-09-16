from pathlib import Path
from typing import Callable, Optional

from swebench.harness.test_spec import TestSpec

from navie.editor import Editor

from .work_dir import WorkDir


class GeneratePlan:

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

    def run(
        self, edit_code_file: Path, context: Optional[dict[str, str]] = None
    ) -> str:
        context_str = None
        if context:
            context_str = "\n".join(
                [
                    f"""<code-snippet location="{k}"><![CDATA[{v}
]]></code-snippet>
"""
                    for k, v in context.items()
                ]
            )
        editor = Editor(
            self.work_dir.plan().path_name,
            log_dir=self.work_dir.root.path_name,
            trajectory_file=self.trajectory_file,
        )
        return editor.plan(
            self.issue(edit_code_file),
            context=context_str,
            context_format="xml",
            options=r"/noprojectinfo /noclassify /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    def issue(self, edit_code_file: Path) -> str:
        return f"""Plan a solution to the following issue, by modifying the code in the file {edit_code_file}:

<issue>
{self.issue_text}
</issue>

In the Problem section, restate the issue in your own words. Retain as much detail as you can, but clean up the language and formatting.

Do not plan specific code changes. Just design the solution.

Do not modify files other than {edit_code_file}.
"""
