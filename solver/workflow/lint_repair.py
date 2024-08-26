from typing import Callable, List, Optional

from .linter import Linter
from .patch import Patch


class LintRepairResult:
    def __init__(self, attempts: int, patch: Optional[Patch]):
        self.attempts = attempts
        self.patch = patch


def lint_repair(
    log: Callable[[str, str], None],
    step_name: str,
    max_retries: int,
    linter: Linter,
    generator: Callable[[int, List[str]], Patch],
    clean_repo: Callable[[], None],
) -> LintRepairResult:
    log_label = "/".join([step_name, "lint-repair"])
    generate_attempt = 1
    lint_errors = []
    patch = None

    while not patch and generate_attempt <= max_retries:
        log(
            log_label,
            f"Making attempt {generate_attempt} to generate code that lints cleanly",
        )
        lint_errors.sort()

        distinct_lint_errors = list(set(lint_errors))
        patch = generator(generate_attempt, distinct_lint_errors)

        generate_attempt += 1

        if not patch:
            log(log_label, "Patch is empty, retrying")
            continue

        lint_clean = True
        for file_path in patch.list_files():
            file_lint_errors = linter.lint(file_path)
            patch_lines = patch.modified_lines(file_path)
            lint_errors_in_patch = linter.select_lint_errors(
                file_lint_errors, patch_lines
            )
            if lint_errors_in_patch:
                lint_errors_in_patch_str = "\n".join(lint_errors_in_patch)
                log(log_label, f"Code has lint errors: {lint_errors_in_patch_str}")
                lint_errors.extend(file_lint_errors)
                lint_clean = False

        if lint_clean:
            log(log_label, "Code lints cleanly")
        else:
            patch = None
            log(log_label, "Reverting code changes due to lint errors")
            clean_repo()

    return LintRepairResult(generate_attempt - 1, patch)
