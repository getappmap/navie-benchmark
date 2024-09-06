import os
from pathlib import Path
from typing import List, Optional

from navie.editor import Editor
from navie.fences import extract_fenced_content


# Choose a test case file that is most related to the issue.
def choose_test_file(
    log, work_dir, trajectory_file, issue_content
) -> Optional[List[Path]]:
    tests_to_modify_str = Editor(
        os.path.join(work_dir, "choose"),
        log_dir=work_dir,
        trajectory_file=trajectory_file,
    ).search(
        f"""Identify a single test case that is most related to the following issue:

{issue_content}
""",
        format="""## Format instructions
        
Output the results as one file path on each line, and nothing else.

Do not include line numbers or any location within the file. Just the file path.
""",
        options="/noprojectinfo /noterms /noclassify /include=test",
        extension="txt",
    )

    tests_to_modify = []

    # Recognize all file paths like this: <!-- file: /home/runner/work/_temp/tmpcwaaevd8/sympy__sympy__1.11-3/sympy/printing/tests/test_pycode.py -->
    for line in tests_to_modify_str.split("\n"):
        file_start_index = line.find("<!-- file: ")
        file_end_index = line.find(" -->")
        if (
            file_start_index != -1
            and file_end_index != -1
            and file_end_index > file_start_index
        ):
            test_name = line[file_start_index + len("<!-- file: ") : file_end_index]
            tests_to_modify.append(test_name)

    # Also recognized the fenced output, which should just be a list of files.
    if len(tests_to_modify) == 0 and "```" in tests_to_modify_str:
        tests_to_modify_lines = "\n".join(extract_fenced_content(tests_to_modify_str))
        tests_to_modify.extend(tests_to_modify_lines.split("\n"))

    # Still nothing? Use the whole response.
    if len(tests_to_modify) == 0:
        tests_to_modify.extend(tests_to_modify_str.split("\n"))

    def resolve_test_path(test):
        if not os.path.exists(test):
            test_relative = test.lstrip("/")
            if os.path.exists(test_relative):
                return test_relative
        return test

    def remove_line_range(test: str) -> str:
        """
        The path may be generated with line numbers, like path/to/file.py:1-10
        Match the path without line numbers.
        """
        return test.split(":")[0]

    def make_relative(test: str) -> str:
        return os.path.relpath(test, os.getcwd())

    def make_path(test: str) -> Path:
        return Path(test)

    tests_to_modify = [resolve_test_path(test) for test in tests_to_modify]
    tests_to_modify = [remove_line_range(test) for test in tests_to_modify]
    tests_to_modify = [test for test in tests_to_modify if os.path.exists(test)]
    tests_to_modify = [make_relative(test) for test in tests_to_modify]

    if len(tests_to_modify) == 0:
        log(
            "choose-test-file", f"Found no existing test files in {tests_to_modify_str}"
        )
        return None

    # Preserve the LLM-recommended priority.
    unique_tests = set()
    result = []
    for test in tests_to_modify:
        if test not in unique_tests:
            result.append(test)
            unique_tests.add(test)

    log("choose-test-file", f"Recommended tests to modify: {", ".join(result)}")

    return [make_path(test) for test in result]
