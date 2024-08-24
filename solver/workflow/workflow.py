from os import listdir, path
from pathlib import Path
import subprocess
from typing import Callable, List
from uuid import uuid4

from navie.editor import Editor
from navie.fences import extract_fenced_content

from .patch import Patch
from .linter import Flake8Linter
from .generate_code import GenerateCode
from .generate_test import GenerateTest
from .choose_test_file import choose_test_file


class Workflow:
    def __init__(
        self, log, navie_work_dir, issue_text, file_limit=1, generate_retry_limit=5
    ):
        self.log = log
        self.navie_work_dir = navie_work_dir
        self.issue_text = issue_text
        self.file_limit = file_limit
        self.generate_retry_limit = generate_retry_limit

        self.edit_test_patch = None
        self.patch = None

    def run(self):
        self.log("workflow", "Running workflow")

        plan = self.generate_plan()
        self.generate_test(plan)
        self.generate_code(plan)

    def generate_plan(self):
        editor = Editor(self.navie_work_dir)
        issue_text = "\n\n".join(
            [
                self.issue_text,
                f"In the Problem section, restate the issue in your own words. Retain as much detail as you can, but clean up the language and formatting.",
                f"Limit your solution to modify at most {self.file_limit} file(s).",
                "Do not plan specific code changes. Just design the solution.",
            ]
        )
        return editor.plan(
            issue_text,
            options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )

    def generate_test(self, code_plan):
        self.clean_git_state()

        # Choose a test file
        editor = Editor(path.join(self.navie_work_dir, "generate-test"))

        edit_test_file = choose_test_file(self.log, editor.work_dir, self.issue_text)
        if not edit_test_file:
            return

        test_plan = editor.ask(
            f"""Modify {edit_test_file} to include a test for the following code.

The test should pass only when the issue is fixed as per the following plan:

<plan>
{code_plan}
</plan>

Do not modify any code besides the named test file. Do not generate code. Just design the test.
""",
            options=r"/noprojectinfo",
            question_name="test_plan",
            prompt="""## Output

Output a list of conditions that the code should satisfy to reproduce the issue.

Do not describe the conditions of the issue. Describe the conditions that the test
should check for to ensure that the issue is fixed.

The list of conditions should be in bullet list format.

* Do not modify any code besides the named test file
* Do not generate code. Just design the test.
* Ensure that if the issue is present in the code, the test FAILS.
* When the issue is fixed, the test should PASS.
""",
        )

        self.log("workflow", f"Test file: {edit_test_file}")
        self.log("workflow", f"Plan:\n{test_plan}")

        existing_test_files = "\n".join(listdir(Path(edit_test_file).parent))

        test_file_answer = editor.ask(
            f"""Generate a new test file name based on the existing test file name, that is relevant to the issue being fixed.

<base-file-name>
{edit_test_file}
</base-file-name>

Avoid using any of the following names, because these files already exist:

<existing-files>
{existing_test_files}
</existing-files>

<test-plan>
{test_plan}
</test-plan>

Output the file name, and nothing else. Do not include directory paths.
""",
            options=r"/noprojectinfo",
            question_name="test_file_name",
        )
        test_file_name = (
            "\n".join(extract_fenced_content(test_file_answer)).strip().split("\n")[0]
        )
        test_file_path = str(Path(edit_test_file).parent / test_file_name)

        generator = GenerateTest(self.log, editor.work_dir, test_plan, self.file_limit)

        def generate(attempt, lint_errors: list = []):
            test_patch = generator.generate(attempt, lint_errors)
            return generator.apply(test_file_path, test_patch)

        self.edit_test_patch = self.implement_plan(generate)

        self.clean_git_state()

        if self.edit_test_patch:
            self.log("generate-test", f"Patch:\n{self.edit_test_patch}")

    def generate_code(self, plan):
        self.clean_git_state()

        generator = GenerateCode(self.log, self.navie_work_dir, plan, self.file_limit)

        def generate(attempt, lint_errors: list = []):
            code = generator.generate(attempt, lint_errors)
            return generator.apply(attempt, code)

        self.patch = self.implement_plan(generate)

        self.clean_git_state()

        if self.patch:
            self.log("generate-code", f"Patch:\n{self.patch}")

    def implement_plan(self, generator: Callable[[int, List[str]], None]) -> Patch:
        generate_attempt = 1
        lint_errors = []
        patch = None
        while not patch and generate_attempt <= self.generate_retry_limit:
            self.log(
                "workflow",
                f"Making attempt {generate_attempt} to generate code that lints cleanly",
            )
            lint_errors.sort()

            distinct_lint_errors = list(set(lint_errors))
            patch = generator(generate_attempt, distinct_lint_errors)

            generate_attempt += 1

            if not patch:
                self.log("workflow", "Patch is empty, retrying")
                continue

            lint_clean = True
            for file_path in patch.list_files():
                linter = Flake8Linter()
                file_lint_errors = linter.lint(file_path)
                patch_lines = patch.modified_lines(file_path)
                lint_errors_in_patch = linter.select_lint_errors(
                    file_lint_errors, patch_lines
                )
                if lint_errors_in_patch:
                    lint_errors_in_patch_str = "\n".join(lint_errors_in_patch)
                    self.log(
                        "workflow", f"Code has lint errors: {lint_errors_in_patch_str}"
                    )
                    lint_errors.extend(file_lint_errors)
                    lint_clean = False

            if lint_clean:
                self.log("workflow", "Code lints cleanly")
            else:
                patch = None
                self.log("workflow", "Reverting code changes due to lint errors")
                subprocess.run(["git", "checkout", "."], check=True)

        return patch

    def clean_git_state(self):
        first_commit_hash = (
            subprocess.check_output("git rev-list --max-parents=0 HEAD", shell=True)
            .strip()
            .decode("utf-8")
        )

        cmd = f"git reset --hard {first_commit_hash} && git clean -fdxq"
        subprocess.run(cmd, shell=True, check=True)

        self.log("workflow", "Cleaned git state")
