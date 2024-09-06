import os
from pathlib import Path
from typing import Optional

from navie.editor import Editor
from navie.fences import extract_fenced_content


# Choose a test case file that is most related to the issue.
def choose_test_file(log, work_dir, trajectory_file, issue_content) -> Optional[Path]:
    test_to_modify_str = Editor(
        os.path.join(work_dir, "choose"),
        log_dir=work_dir,
        trajectory_file=trajectory_file,
    ).search(
        issue_content,
        prompt="""## Task

Identify a single test case that is most related to the issue.        
        
## Format instructions
        
Output the result as the file path, and nothing else.

Do not include line numbers or any location within the file. Just the file path.
""",
        options="/noprojectinfo /noterms /noclassify /include=test",
        extension="txt",
    )

    tests_to_modify = []

    # Recognize all file paths like this: <!-- file: /home/runner/work/_temp/tmpcwaaevd8/sympy__sympy__1.11-3/sympy/printing/tests/test_pycode.py -->
    for line in test_to_modify_str.split("\n"):
        if line.startswith("<!-- file: "):
            tests_to_modify.append(line[len("<!-- file: ") : -len(" -->")])

    # Also recognized the fenced output, which should just be a list of files.
    tests_to_modify_lines = "\n".join(extract_fenced_content(test_to_modify_str))
    tests_to_modify.extend(tests_to_modify_lines.split("\n"))

    def resolve_test_path(test):
        if not os.path.exists(test):
            test_relative = test.lstrip("/")
            if os.path.exists(test_relative):
                return test_relative
        return test

    def normalize_path(test: str) -> str:
        """
        The path may be generated with line numbers, like path/to/file.py:1-10
        Match the path without line numbers.
        """
        return test.split(":")[0]

    tests_to_modify = [resolve_test_path(test) for test in tests_to_modify]
    tests_to_modify = [normalize_path(test) for test in tests_to_modify]
    tests_to_modify = [test for test in tests_to_modify if os.path.exists(test)]

    if len(tests_to_modify) == 0:
        log("choose-test-file", f"Found no existing test files in {test_to_modify_str}")
        return None

    if len(tests_to_modify) > 1:
        log("choose-test-file", f"Found multiple test files in {test_to_modify_str}")

    test_file = tests_to_modify[0]
    test_file = os.path.relpath(test_file, os.getcwd())

    log("choose_test_file", f"Chose test file: {test_file}")

    return Path(test_file)
