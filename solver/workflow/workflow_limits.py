FILE_LIMIT = 1
TEST_FILES_LIMIT = 1
TEST_LINT_RETRY_LIMIT = 3
TEST_STATUS_RETRY_LIMIT = 2
CODE_LINT_RETRY_LIMIT = 3
CODE_STATUS_RETRY_LIMIT = 2


class WorkflowLimits:
    def __init__(
        self,
        file_limit: int = FILE_LIMIT,
        test_files_limit: int = TEST_FILES_LIMIT,
        test_lint_retry_limit: int = TEST_LINT_RETRY_LIMIT,
        test_status_retry_limit: int = TEST_STATUS_RETRY_LIMIT,
        code_lint_retry_limit: int = CODE_LINT_RETRY_LIMIT,
        code_status_retry_limit: int = CODE_STATUS_RETRY_LIMIT,
    ):
        """
        Create a new WorkflowLimits object.

        Args:
            file_limit (int): The maximum number of files that the LLM will be prompted to modify.
            test_files_limit (int): The number of different existing test case files that will be selected for modification into a test patch.
            test_lint_retry_limit (int): The maximum number of times to retry linting a test patch.
            test_status_retry_limit (int): The maximum number of times to retry running a test patch. This retry is activated by test failures.
            code_lint_retry_limit (int): The maximum number of times to retry linting a code patch.
            code_status_retry_limit (int): The maximum number of times to retry running a code patch. This retry is activated by test failures.
        """
        self.file_limit = file_limit
        self.test_files_limit = test_files_limit
        self.test_lint_retry_limit = test_lint_retry_limit
        self.test_status_retry_limit = test_status_retry_limit
        self.code_lint_retry_limit = code_lint_retry_limit
        self.code_status_retry_limit = code_status_retry_limit

    def __str__(self):
        return f"file={self.file_limit}, test_files={self.test_files_limit}, test_lint_retry={self.test_lint_retry_limit}, test_status_retry={self.test_status_retry_limit}, code_lint_retry={self.code_lint_retry_limit}, code_status_retry={self.code_status_retry_limit}"

    @staticmethod
    def from_dict(data: dict):
        return WorkflowLimits(
            file_limit=data.get("file", FILE_LIMIT),
            test_files_limit=data.get("test_files", TEST_FILES_LIMIT),
            test_lint_retry_limit=data.get("test_lint_retry", TEST_LINT_RETRY_LIMIT),
            test_status_retry_limit=data.get(
                "test_status_retry", TEST_STATUS_RETRY_LIMIT
            ),
            code_lint_retry_limit=data.get("code_lint_retry", CODE_LINT_RETRY_LIMIT),
            code_status_retry_limit=data.get(
                "code_status_retry", CODE_STATUS_RETRY_LIMIT
            ),
        )

    @staticmethod
    def limit_names():
        return [
            "file",
            "test_files",
            "test_lint_retry",
            "test_status_retry",
            "code_lint_retry",
            "code_status_retry",
        ]
