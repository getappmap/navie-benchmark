from os import getcwd
from posixpath import relpath
import re
import subprocess

from unidiff import PatchSet
from solver.steps.choose_test_file import choose_test_file

from navie.editor import Editor
from navie.format_instructions import xml_format_instructions
from navie.extract_changes import extract_changes
from solver.steps.patch import filter_patch_exclude_tests, git_diff


class Workflow:
    def __init__(
        self, log, navie_work_dir, issue_text, file_limit=1, generate_retry_limit=5
    ):
        self.log = log
        self.navie_work_dir = navie_work_dir
        self.issue_text = issue_text
        self.file_limit = file_limit
        self.generate_retry_limit = generate_retry_limit

        self.editor = None
        self.plan_doc = None
        self.test_file = None
        self.lint_errors = []
        self.code = None
        self.patch = None

    def run(self):
        self.log("workflow", "Running workflow")
        self.clean_git_state()
        self.choose_test_file()

        self.editor = Editor(self.navie_work_dir)
        self.plan()

        generate_attempt = 1
        while not self.patch and generate_attempt <= self.generate_retry_limit:
            self.log(
                "workflow",
                f"Making attempt {generate_attempt} to generate code that lints cleanly",
            )
            self.generate()
            self.apply()

            generate_attempt += 1

    def clean_git_state(self):
        first_commit_hash = (
            subprocess.check_output("git rev-list --max-parents=0 HEAD", shell=True)
            .strip()
            .decode("utf-8")
        )

        cmd = f"git reset --hard {first_commit_hash} && git clean -fdxq"
        subprocess.run(cmd, shell=True, check=True)

        return self

    def choose_test_file(self):
        # Choose a test file
        self.test_file = choose_test_file(
            self.log, self.navie_work_dir, self.issue_text
        )

    def plan(self):
        issue_text = "\n\n".join(
            [
                self.issue_text,
                f"In the Problem section, restate the issue in your own words. Retain as much detail as you can, but clean up the language and formatting.",
                f"Limit your solution to modify at most {self.file_limit} file(s).",
                "Do not plan specific code changes. Just design the solution.",
            ]
        )
        self.plan_doc = self.editor.plan(issue_text)

    def generate(self):
        plan = [
            self.plan_doc,
        ]
        if self.lint_errors:
            lint_prompt = [
                "## Avoid these lint errors",
            ]
            lint_prompt.extend(self.lint_errors)
            plan.append("\n\n".join(lint_prompt))

        self.code = self.editor.generate(
            plan="\n\n".join(plan), prompt=xml_format_instructions()
        )

    def apply(self):
        changes = extract_changes(self.code)
        changed_files = set([change.file for change in changes])
        if len(changed_files) > self.file_limit:
            self.log(
                "workflow",
                f"Found {len(changes)} changes, but the limit is {self.file_limit}",
            )

        for change in changes:
            change.file = relpath(change.file, getcwd())
            self.editor.apply(change.file, change.modified, search=change.original)

        file_paths = [change.file for change in changes]
        file_paths_str = ", ".join(file_paths)
        self.log("workflow", f"Applied code changes to {file_paths_str}")

        patch = filter_patch_exclude_tests(git_diff())
        if self.lint(file_paths, patch):
            self.patch = patch
            self.log("workflow", f"Patch:\n{self.patch}")
        else:
            self.log("workflow", "Reverting code changes due to lint errors")
            subprocess.run(["git", "checkout", "."], check=True)

    def lint(self, file_paths, patch):
        lint_errors = []

        # Parse the patch using unidiff
        line_numbers_in_patch = set()
        parsed_patch = PatchSet.from_string(patch)
        for patched_file in parsed_patch:
            for hunk in patched_file:
                for line in hunk.target_lines():
                    if line.is_added or line.is_removed:
                        line_numbers_in_patch.add(line.target_line_no)

        # You can now use line_numbers_in_patch as needed
        self.log("workflow", f"Line numbers in patch: {line_numbers_in_patch}")

        def extract_line_numbers_from_lint_output(lint_output):
            line_number_pattern = re.compile(r":(\d+):")
            line_numbers = set()
            for line in lint_output.split("\n"):
                match = line_number_pattern.search(line)
                if match:
                    line_numbers.add(int(match.group(1)))
            return line_numbers

        def run_lint_command(lint_command, file_path):
            command = []
            command.extend(lint_command)
            command.append(file_path)
            self.log("workflow", f"Running lint command: {' '.join(command)}")
            lint_result = subprocess.run(command, capture_output=True)
            lint_error_str = lint_result.stdout.decode("utf-8").strip()

            if lint_error_str:
                command_name = lint_command[0]

                line_numbers_in_lint = extract_line_numbers_from_lint_output(
                    lint_error_str
                )
                self.log(
                    "workflow",
                    f"Line numbers in {command_name} lint errors: {line_numbers_in_lint}",
                )
                line_numbers_in_patch_and_lint = line_numbers_in_patch.intersection(
                    line_numbers_in_lint
                )

                lint_errors_in_patch = [
                    line
                    for line in lint_error_str.split("\n")
                    if any(
                        f":{line_num}:" in line
                        for line_num in line_numbers_in_patch_and_lint
                    )
                ]

                if lint_errors_in_patch:
                    lint_errors_in_patch_str = "\n".join(lint_errors_in_patch)
                    print(
                        f"Lint errors for {command_name} on {file_path}:\n{lint_errors_in_patch_str}"
                    )
                    lint_errors.append("\n".join(lint_errors_in_patch))

        flake8_lint_command = [
            "flake8",
            "--extend-ignore=BLK100,C402,C408,C416,D,E122,E124,E127,E128,E131,E201,E202,E203,E221,E225,E231,E251,E261,E265,E266,E302,E303,E305,E402,E501,E502,E713,E731,F401,F841,W291,W293",
        ]

        for file_path in file_paths:
            run_lint_command(flake8_lint_command, file_path)
            # run_lint_command(pylint_lint_command, file_path)

        if lint_errors:
            self.lint_errors.extend(lint_errors)
            return False

        self.log("workflow", "Code lints cleanly")
        return True
