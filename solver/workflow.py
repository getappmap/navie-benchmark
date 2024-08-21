import subprocess
from solver.steps.choose_test_file import choose_test_file

from navie.editor import Editor
from navie.format_instructions import xml_format_instructions
from navie.extract_changes import extract_changes


class Workflow:
    def __init__(self, log, navie_work_dir, issue_text, file_limit=1):
        self.log = log
        self.navie_work_dir = navie_work_dir
        self.issue_text = issue_text
        self.file_limit = file_limit

        self.test_file = None

    def run(self):
        self.log("workflow", "Running workflow")
        self.clean_git_state()
        self.choose_test_file()
        self.plan()

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
        editor = Editor(self.navie_work_dir)

        issue_text = "\n\n".join(
            [
                self.issue_text,
                f"In the Problem section, restate the issue in your own words. Retain as much detail as you can, but clean up the language and formatting.",
                f"Limit your solution to modify at most {self.file_limit} file(s).",
                "Do not plan specific code changes. Just design the solution.",
            ]
        )
        editor.plan(issue_text)
        code = editor.generate(prompt=xml_format_instructions())
        changes = extract_changes(code)
        if len(changes) > self.file_limit:
            self.log(
                "workflow",
                f"Found {len(changes)} changes, but the limit is {self.file_limit}",
            )

        for change in changes:
            editor.apply(change.file, change.modified, search=change.original)

        # Capture a diff of the changes

        # Revert the source directory
