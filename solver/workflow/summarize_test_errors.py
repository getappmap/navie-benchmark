from typing import List, Optional

from navie.editor import Editor

from solver.workflow.work_dir import WorkDir


def summarize_test_errors(
    log, dir: WorkDir, trajectory_file: str, test_output: str
) -> str:
    work_dir = dir.summarize_test_errors()
    editor = Editor(
        work_dir.path, log_dir=work_dir.root.path_name, trajectory_file=trajectory_file
    )
    question = f"""Extract specific errors from this log that caused a test to fail.

Print the failure lines, and nothing else. If there is a stack trace with file names
and line numbers, be sure to include it.

If an error is repeated multiple times, print it only once.

Ignore errors like "error: patch with only garbage", as these are unrelated and benign.

<test-output>
{test_output}
</test-output>
"""

    errors = editor.ask(
        question,
        options="/nocontext /noclassify",
    )
    log(
        "summarize-test-errors",
        f"Extracted test errors: {errors}",
    )
    return errors
