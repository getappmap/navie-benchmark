import os


FILE_LIMIT = 1
CONTEXT_TOKENS_LIMIT = 8000
TEST_FILES_LIMIT = 1
CODE_FILES_LIMIT = 1
TEST_LINT_RETRY_LIMIT = 3
TEST_STATUS_RETRY_LIMIT = 2
CODE_LINT_RETRY_LIMIT = 3
CODE_STATUS_RETRY_LIMIT = 2
CONCURRENCY_LIMIT = 4


class WorkflowLimits:
    def __init__(
        self,
        file_limit: int = FILE_LIMIT,
        context_tokens_limit: int = CONTEXT_TOKENS_LIMIT,
        test_files_limit: int = TEST_FILES_LIMIT,
        code_files_limit: int = CODE_FILES_LIMIT,
        test_lint_retry_limit: int = TEST_LINT_RETRY_LIMIT,
        test_status_retry_limit: int = TEST_STATUS_RETRY_LIMIT,
        code_lint_retry_limit: int = CODE_LINT_RETRY_LIMIT,
        code_status_retry_limit: int = CODE_STATUS_RETRY_LIMIT,
        concurrency_limit: int = CONCURRENCY_LIMIT,
    ):
        """
        Create a new WorkflowLimits object.

        Args:
            file_limit (int): The maximum number of files that the LLM will be prompted to modify.
            context_tokens (int): The maximum number of context tokens that Navie will be instructed to use.
            test_files_limit (int): The number of different existing test case files that will be selected for modification into a test patch.
            code_files_limit (int): The number of different existing code files that will be selected for modification into a code patch.
            test_lint_retry_limit (int): The maximum number of times to retry linting a test patch.
            test_status_retry_limit (int): The maximum number of times to retry running a test patch. This retry is activated by test failures.
            code_lint_retry_limit (int): The maximum number of times to retry linting a code patch.
            code_status_retry_limit (int): The maximum number of times to retry running a code patch. This retry is activated by test failures.
            concurrency_limit (int): The maximum number of concurrent instances that will be solved in parallel.
        """
        self.file_limit = file_limit
        self.context_tokens_limit = context_tokens_limit
        self.test_files_limit = test_files_limit
        self.code_files_limit = code_files_limit
        self.test_lint_retry_limit = test_lint_retry_limit
        self.test_status_retry_limit = test_status_retry_limit
        self.code_lint_retry_limit = code_lint_retry_limit
        self.code_status_retry_limit = code_status_retry_limit
        self.concurrency_limit = concurrency_limit

        if self.context_tokens_limit != CONTEXT_TOKENS_LIMIT:
            print(f"Setting APPMAP_NAVIE_TOKEN_LIMIT to {self.context_tokens_limit}")
            os.environ["APPMAP_NAVIE_TOKEN_LIMIT"] = str(self.context_tokens_limit)

    def __str__(self):
        return f"file={self.file_limit}, context_tokens={self.context_tokens_limit}, test_files={self.test_files_limit}, code_files={self.code_files_limit}, test_lint_retry={self.test_lint_retry_limit}, test_status_retry={self.test_status_retry_limit}, code_lint_retry={self.code_lint_retry_limit}, code_status_retry={self.code_status_retry_limit}, concurrency={self.concurrency_limit}"

    @staticmethod
    def from_dict(data: dict):
        return WorkflowLimits(
            file_limit=data.get("file", FILE_LIMIT),
            context_tokens_limit=data.get("context_tokens", CONTEXT_TOKENS_LIMIT),
            test_files_limit=data.get("test_files", TEST_FILES_LIMIT),
            code_files_limit=data.get("code_files", CODE_FILES_LIMIT),
            test_lint_retry_limit=data.get("test_lint_retry", TEST_LINT_RETRY_LIMIT),
            test_status_retry_limit=data.get(
                "test_status_retry", TEST_STATUS_RETRY_LIMIT
            ),
            code_lint_retry_limit=data.get("code_lint_retry", CODE_LINT_RETRY_LIMIT),
            code_status_retry_limit=data.get(
                "code_status_retry", CODE_STATUS_RETRY_LIMIT
            ),
            concurrency_limit=data.get("concurrency", CONCURRENCY_LIMIT),
        )

    @staticmethod
    def limit_names():
        return [
            "file",
            "context_tokens",
            "test_files",
            "code_files",
            "test_lint_retry",
            "test_status_retry",
            "code_lint_retry",
            "code_status_retry",
            "concurrency",
        ]
