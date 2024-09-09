import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from solver.tests.workflow.collect_solve_listener import CollectSolveListener
from solver.tests.workflow.test_generate_and_validate_code import (
    EXAMPLE_TEST_PATCH,
    EXAMPLE_TEST_PATCH_INVERTED,
)
from solver.workflow.generate_and_validate_test import (
    generate_and_validate_test,
    Context,
)
from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTestResult
from solver.workflow.solve_listener import TestStatus
from solver.workflow.work_dir import WorkDir
from solver.workflow.workflow_limits import WorkflowLimits


class TestGenerateAndValidateTest(unittest.TestCase):
    def setUp(self):
        self.limits = WorkflowLimits(test_files_limit=3, test_status_retry_limit=2)
        self.log = Mock()
        self.docker_client = Mock()
        self.work_dir = WorkDir("path/to/work_dir", write_sequence=False)
        self.repo = "test_repo"
        self.version = "1.0"
        self.solve_listener: CollectSolveListener = CollectSolveListener()
        self.solve_listeners = [self.solve_listener]
        self.context = Context(
            self.limits,
            self.log,
            self.work_dir,
            self.docker_client,
            self.repo,
            self.version,
            self.solve_listeners,
        )
        self.edit_test_files = [Path("test_file_1.py"), Path("test_file_2.py")]
        self.maxDiff = None

    def emit_example_patch_on_file_index(self, file_index):
        def mock_generate_test(work_dir, edit_test_file, args):
            if edit_test_file == self.edit_test_files[file_index]:
                return Patch(EXAMPLE_TEST_PATCH)

        return mock_generate_test

    def emit_inverted_test(self):
        def mock_invert_test(work_dir, patch):
            return Patch(EXAMPLE_TEST_PATCH_INVERTED)

        return mock_invert_test

    def test_first_optimal_test_patch_accepted(self):
        """
        The first file emits an optimal test patch.
        """

        def mock_run_test(work_dir, patch):
            if patch == Patch(EXAMPLE_TEST_PATCH):
                return RunTestResult(
                    TestStatus.PASSED,
                    run_succeeded=True,
                    test_output="test-output",
                )
            elif patch == Patch(EXAMPLE_TEST_PATCH_INVERTED):
                return RunTestResult(
                    TestStatus.FAILED,
                    run_succeeded=True,
                    test_output="test-inverted-output __BUG__HERE__",
                )
            else:
                raise ValueError(f"Unexpected patch: {patch}")

        def mock_invert_test(work_dir, patch):
            return Patch(EXAMPLE_TEST_PATCH_INVERTED)

        with patch(
            "solver.workflow.generate_and_validate_test.is_optimal_test_patch",
            return_value=True,
        ):
            test_patch_results = generate_and_validate_test(
                self.context,
                self.edit_test_files,
                self.emit_example_patch_on_file_index(0),
                mock_run_test,
                self.emit_inverted_test(),
            )

        self.assertEqual(
            [msg[0] for msg in self.solve_listener.messages],
            [
                "on_start_edit_test_file",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_end_edit_test_file",
            ],
        )

        self.assertEqual(len(test_patch_results), 1)
        self.assertEqual(test_patch_results[0]["test_patch"], Patch(EXAMPLE_TEST_PATCH))
        self.assertEqual(
            test_patch_results[0]["inverted_patch"], Patch(EXAMPLE_TEST_PATCH_INVERTED)
        )

    def test_failed_test_skipped(self):
        """
        The first file does not emit a patch on any of the attempts.
        The second file emits an optimal test patch.
        """

        def mock_run_test(work_dir, patch):
            if patch == Patch(EXAMPLE_TEST_PATCH):
                return RunTestResult(
                    TestStatus.PASSED,
                    run_succeeded=True,
                    test_output="test-output",
                )
            elif patch == Patch(EXAMPLE_TEST_PATCH_INVERTED):
                return RunTestResult(
                    TestStatus.FAILED,
                    run_succeeded=True,
                    test_output="test-inverted-output __BUG__HERE__",
                )
            else:
                raise ValueError(f"Unexpected patch: {patch}")

        with patch(
            "solver.workflow.generate_and_validate_test.is_optimal_test_patch",
            return_value=True,
        ):
            test_patch_results = generate_and_validate_test(
                self.context,
                self.edit_test_files,
                self.emit_example_patch_on_file_index(1),
                mock_run_test,
                self.emit_inverted_test(),
            )

        self.assertEqual(
            [msg[0] for msg in self.solve_listener.messages],
            [
                # Two attempts at the first file
                "on_start_edit_test_file",
                "on_start_patch",
                "on_end_patch",
                "on_start_patch",
                "on_end_patch",
                "on_end_edit_test_file",
                # Second file succeeds on first attempt
                "on_start_edit_test_file",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_end_edit_test_file",
            ],
        )

        self.assertEqual(len(test_patch_results), 1)
        self.assertEqual(test_patch_results[0]["test_patch"], Patch(EXAMPLE_TEST_PATCH))
        self.assertEqual(
            test_patch_results[0]["inverted_patch"], Patch(EXAMPLE_TEST_PATCH_INVERTED)
        )

    def test_suboptimal_patch_accepted_and_sorted(self):
        """
        The first test file emits suboptimal test patches on all attempts.
        The second file emits no patches.
        """

        def mock_run_test(work_dir, patch):
            if patch == Patch(EXAMPLE_TEST_PATCH):
                return RunTestResult(
                    TestStatus.PASSED,
                    run_succeeded=True,
                    test_output="test-output",
                )
            elif patch == Patch(EXAMPLE_TEST_PATCH_INVERTED):
                # Has the marker error, but SKIPPED. Not valid.
                return RunTestResult(
                    TestStatus.SKIPPED,
                    run_succeeded=True,
                    test_output="test-inverted-output __BUG__HERE__",
                )
            else:
                raise ValueError(f"Unexpected patch: {patch}")

        with patch(
            "solver.workflow.generate_and_validate_test.is_optimal_test_patch",
            return_value=False,
        ):
            test_patch_results = generate_and_validate_test(
                self.context,
                self.edit_test_files,
                self.emit_example_patch_on_file_index(0),
                mock_run_test,
                self.emit_inverted_test(),
            )

        self.assertEqual(
            [msg[0] for msg in self.solve_listener.messages],
            [
                "on_start_edit_test_file",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_end_edit_test_file",
                "on_start_edit_test_file",
                "on_start_patch",
                "on_end_patch",
                "on_start_patch",
                "on_end_patch",
                "on_end_edit_test_file",
                "on_start_edit_test_file",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_end_patch",
                "on_end_edit_test_file",
            ],
        )

        self.assertEqual(len(test_patch_results), 4)
        for result in test_patch_results:
            self.assertEqual(result["test_patch"], Patch(EXAMPLE_TEST_PATCH))
            self.assertEqual(result["inverted_patch"], None)


if __name__ == "__main__":
    unittest.main()
