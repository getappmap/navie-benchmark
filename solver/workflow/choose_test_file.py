import os
from pathlib import Path
from typing import Callable, List, Optional

from navie.editor import Editor
from solver.workflow.choose_code_files import extract_file_paths
from solver.workflow.work_dir import WorkDir


def ask_for_test_files(
        log,
        work_dir: WorkDir,
        trajectory_file: str,
        issue_content: str,
        num_files: int,
        tests_previously_listed: set[Path],
        attempt: int,
        ) -> List[Path]:

    examples = "\n".join([f"path/to/test_{i}.py" for i in range(1, num_files + 1)])
    token_limit = 3000 * num_files

    question = f"""Identify {num_files} test files that are most related to the issue. Put the most relevant file first,
followed by less relevant files.

The files must all be different.

<issue>
{issue_content}
</issue>
"""

    prompt = f"""## Output format
    
Output the results as one file path on each line, and nothing else.

Do not include line numbers or any location within the file. Just the file path.

## Examples
        
{examples}
    """

    if tests_previously_listed:
        known_files = "\n".join([str(file) for file in tests_previously_listed])
        question += f"""Do not emit any of the following files, because they are already known:

{known_files}
"""

    tests_to_modify_str = Editor(
        (work_dir.path / f"attempt-{attempt}"),
        log_dir=work_dir.root.path_name,
        trajectory_file=trajectory_file,
    ).search(
        question,
        prompt=prompt,
        options=f"/noprojectinfo /noformat /noclassify /include=test /tokenlimit={token_limit}",
        extension="txt",
    )

    files = extract_file_paths(tests_to_modify_str) or []
    files = [file for file in files if file not in tests_previously_listed]
    if not files:
        log("choose-test-file", f"Found no existing test files in {tests_to_modify_str}")
        return []
    
    log("choose-test-file", f"Found {len(files)} test files to modify on iteration {attempt}")
    return files


# Choose test case files that are most related to the issue.
def choose_test_files(
    log, work_dir: WorkDir, trajectory_file: str, issue_content: str, num_files: int, 
    validate: Callable[[WorkDir, Path], bool] 
) -> Optional[List[Path]]:
    work_dir = work_dir.choose_test_files()

    listed_test_files = set()
    validated_test_files = []    
    for attempt in range(1, 4):
        test_file_batch = ask_for_test_files(
            log,
            work_dir,
            trajectory_file,
            issue_content,
            num_files - len(validated_test_files),
            listed_test_files,
            attempt
        )
        for file in test_file_batch:
            validation_dir = work_dir.validate_test_file(file)
            if validate(validation_dir, file):
                validated_test_files.append(file)
            else:
                log("choose-test-file", f"Skipping {file} because validation failed.")

        if len(validated_test_files) >= num_files:
            break

    log(
        "choose-test-file", f"Recommended tests to modify: {", ".join([str(file) for file in validated_test_files])}"
    )


    return validated_test_files
