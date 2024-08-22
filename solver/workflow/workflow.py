from os import path
import subprocess

from navie.editor import Editor

from .linter import Flake8Linter
from .generator import Generator
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
        self.patch = None
        while not self.patch and generate_attempt <= self.generate_retry_limit:
            self.log(
                "workflow",
                f"Making attempt {generate_attempt} to generate code that lints cleanly",
            )
            editor = Editor(
                path.join(self.navie_work_dir, "generate", str(generate_attempt))
            )

            generator = Generator(self.log, editor, self.plan_doc, self.file_limit)
            code = generator.generate(self.lint_errors)
            patch = generator.apply(code)

            generate_attempt += 1

            if not patch:
                self.log("workflow", "Patch is empty, retrying")
                continue

            lint_clean = True
            for file_path in patch.list_files():
                linter = Flake8Linter()
                lint_errors = linter.lint(file_path)
                patch_lines = patch.modified_lines(file_path)
                lint_errors_in_patch = linter.select_lint_errors(
                    lint_errors, patch_lines
                )
                if lint_errors_in_patch:
                    lint_errors_in_patch_str = "\n".join(lint_errors_in_patch)
                    self.log(
                        "workflow", f"Code has lint errors: {lint_errors_in_patch_str}"
                    )
                    self.lint_errors.extend(lint_errors)
                    lint_clean = False

            if lint_clean:
                self.patch = patch
                self.log("workflow", "Code lints cleanly")
                self.log("workflow", f"Patch:\n{self.patch}")
            else:
                self.log("workflow", "Reverting code changes due to lint errors")
                subprocess.run(["git", "checkout", "."], check=True)

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
        self.plan_doc = self.editor.plan(
            issue_text,
            options=r"/noprojectinfo /exclude=\btests?\b|\btesting\b|\btest_|_test\b",
        )
