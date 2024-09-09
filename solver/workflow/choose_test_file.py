import os
from pathlib import Path
from typing import List, Optional

from navie.editor import Editor
from solver.workflow.choose_code_files import extract_file_paths
from solver.workflow.work_dir import WorkDir


# Choose test case files that are most related to the issue.
def choose_test_files(
    log, work_dir: WorkDir, trajectory_file: str, issue_content: str, num_files: int
) -> Optional[List[Path]]:
    examples = "\n".join([f"path/to/test_{i}.py" for i in range(1, num_files + 1)])
    token_limit = 3000 * num_files

    tests_to_modify_str = Editor(
        work_dir.choose_test_files().path_name,
        log_dir=work_dir.root.path_name,
        trajectory_file=trajectory_file,
    ).search(
        issue_content,
        prompt=f"""## Task

Identify {num_files} test files that are most related to the issue. Put the most relevant file first,
followed by less relevant files.

The files must all be different.

Example:

{examples}
        
Output the results as one file path on each line, and nothing else.

Do not include line numbers or any location within the file. Just the file path.
""",
        options=f"/noprojectinfo /noclassify /include=test /tokenlimit={token_limit}",
        extension="txt",
    )

    tests_to_modify = extract_file_paths(tests_to_modify_str)

    if not tests_to_modify:
        log(
            "choose-test-file", f"Found no existing test files in {tests_to_modify_str}"
        )
        return None

    log(
        "choose-test-file", f"Recommended tests to modify: {", ".join([str(file) for file in tests_to_modify])}"
    )

    return tests_to_modify
