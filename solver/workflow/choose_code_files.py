import os
from pathlib import Path
from typing import List, Optional

from navie.editor import Editor
from navie.fences import extract_fenced_content

from solver.workflow.is_test_file import test_regexp_patterns
from solver.workflow.work_dir import WorkDir


def choose_code_files(
    log, work_dir: WorkDir, trajectory_file: str, issue_content: str, num_files: int
) -> Optional[List[Path]]:
    examples = "\n".join([f"path/to/code_file_{i}.py" for i in range(1, num_files + 1)])
    token_limit = 3000 * num_files

    files_to_modify_str = Editor(
        work_dir.choose_code_files().path_name,
        log_dir=work_dir.root.path_name,
        trajectory_file=trajectory_file,
    ).search(
        issue_content,
        prompt=f"""## Task

Identify {num_files} code files that are are the most likely root causes of the issue. Put the most relevant file first,
followed by less relevant files.

The files must all be different.

Example:

{examples}
        
Output the results as one file path on each line, and nothing else.

Do not include line numbers or any location within the file. Just the file path.
""",
        options=f"/noprojectinfo /noformat /noclassify /exclude={"|".join(test_regexp_patterns)} /noterms /include=py /tokenlimit={token_limit}",
        extension="txt",
    )

    code_files = extract_file_paths(files_to_modify_str)
    if not code_files:
        log(
            "choose-code-file", f"Found no existing code files in {files_to_modify_str}"
        )
        return None

    log(
        "choose-code-file",
        f"Recommended code files to modify: {", ".join([ str(file) for file in code_files])}",
    )
    return code_files


def extract_file_paths(files_to_modify_str: str) -> Optional[List[Path]]:
    files_to_modify = []

    # Recognize all file paths like this: <!-- file: /home/runner/work/_temp/tmpcwaaevd8/sympy__sympy__1.11-3/sympy/printing/tests/test_pycode.py -->
    for line in files_to_modify_str.split("\n"):
        file_start_index = line.find("<!-- file: ")
        file_end_index = line.find(" -->")
        if (
            file_start_index != -1
            and file_end_index != -1
            and file_end_index > file_start_index
        ):
            file_name = line[file_start_index + len("<!-- file: ") : file_end_index]
            files_to_modify.append(file_name)

    # Also recognized the fenced output, which should just be a list of files.
    if len(files_to_modify) == 0 and "```" in files_to_modify_str:
        files_to_modify_lines = "\n".join(extract_fenced_content(files_to_modify_str))
        files_to_modify.extend(files_to_modify_lines.split("\n"))

    # Still nothing? Use the whole response.
    if len(files_to_modify) == 0:
        files_to_modify.extend(files_to_modify_str.split("\n"))

    def resolve_file_path(file_name):
        if not os.path.exists(file_name):
            file_name_relative = file_name.lstrip("/")
            if os.path.exists(file_name_relative):
                return file_name_relative
        return file_name

    def remove_extra_line_content(file_name: str) -> str | None:
        """
        There may be other content in the line, such as a bullet point or a numeric list prefix.
        """
        tokens = file_name.split()
        tokens = [token for token in tokens if len(token.split(".")) > 1]
        if len(tokens) == 0:
            return None

        tokens = [token.lstrip("`").rstrip("`") for token in tokens]
        return max(tokens, key=len)

    def remove_line_range(file_name: str) -> str:
        """
        The path may be generated with line numbers, like path/to/file.py:1-10
        Match the path without line numbers.
        """
        return file_name.split(":")[0]

    def make_relative(file_name: str) -> str:
        return os.path.relpath(file_name, os.getcwd())

    def make_path(file_name: str) -> Path:
        return Path(file_name)

    files_to_modify = [remove_extra_line_content(file) for file in files_to_modify]
    files_to_modify = [file for file in files_to_modify if file]
    files_to_modify = [resolve_file_path(file) for file in files_to_modify]
    files_to_modify = [remove_line_range(file) for file in files_to_modify]
    files_to_modify = [file for file in files_to_modify if os.path.exists(file)]
    files_to_modify = [make_relative(file) for file in files_to_modify]

    if len(files_to_modify) == 0:
        return None

    # Preserve the LLM-recommended priority.
    unique_files = set()
    result = []
    for file in files_to_modify:
        if file not in unique_files:
            result.append(file)
            unique_files.add(file)

    return [make_path(file) for file in result]
