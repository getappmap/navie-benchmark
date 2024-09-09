from typing import List
import unittest
from unittest.mock import Mock, call
from pathlib import Path

from solver.workflow.work_dir import WorkDir
from swebench.harness.test_spec import TestSpec

from solver.tests.workflow.collect_solve_listener import (
    CollectSolveListener,
    trim_patch,
)
from solver.workflow.generate_and_validate_code import (
    empty_patch,
    generate_and_validate_code,
    Context,
)
from solver.workflow.workflow_limits import WorkflowLimits
from solver.workflow.solve_listener import (
    PatchType,
    SolveListener,
    TestStatus,
    TestType,
)
from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTestResult

EXAMPLE_CODE_PATCH = """
diff --git a/file_1 b/file_1
index 123..456 789
--- a/file_1
+++ b/file_1
@@ -1,1 +1,1 @@
-Original code
+Modified code
"""

EXAMPLE_TEST_PATCH = """
diff --git a/test_file b/test_file
index 123..456 789
--- a/test_file
+++ b/test_file
@@ -1,1 +1,1 @@
-Original test code
+Modified test code
"""

EXAMPLE_TEST_PATCH_INVERTED = """
diff --git a/test_file b/test_file
index 123..456 789
--- a/test_file
+++ b/test_file
@@ -1,1 +1,1 @@
-Modified test code
+Inverted test code
"""


class TestGenerateAndValidateCode(unittest.TestCase):
    def setUp(self):
        self.limits = WorkflowLimits(code_status_retry_limit=3)
        self.log = Mock()
        self.docker_client = Mock()
        self.work_dir = WorkDir("path/to/work_dir", write_sequence=False)
        self.repo = "test_repo"
        self.version = "1.0"
        self.test_spec = TestSpec(
            instance_id="test_instance",
            repo="test_repo",
            version="1.0",
            repo_script_list=[],
            eval_script_list=[],
            env_script_list=[],
            arch="x86_64",
            FAIL_TO_PASS=[],
            PASS_TO_PASS=[],
        )
        self.collect_solve_listener = CollectSolveListener()
        self.solve_listeners: List[SolveListener] = [self.collect_solve_listener]
        self.context = Context(
            self.limits,
            self.log,
            self.work_dir,
            self.docker_client,
            self.repo,
            self.version,
            self.test_spec,
            self.solve_listeners,
        )
        self.plan = "test_plan"
        self.generate_code = Mock()
        self.run_test = Mock()

    def test_generate_and_validate_code_successful_patch(self):
        patch = Patch(EXAMPLE_CODE_PATCH)
        self.generate_code.return_value = patch
        self.run_test.side_effect = [
            RunTestResult(TestStatus.PASSED, "PASSED", True),
            RunTestResult(TestStatus.FAILED, "FAILED", True),
            RunTestResult(TestStatus.PASSED, "PASSED", True),
        ]

        result = generate_and_validate_code(
            context=self.context,
            plan=self.plan,
            generate_code=self.generate_code,
            run_test=self.run_test,
            pass_to_pass_test_file=Path("test_file"),
            test_patch=Patch(EXAMPLE_TEST_PATCH),
            test_patch_inverted=Patch(EXAMPLE_TEST_PATCH),
        )

        self.assertEqual(
            self.collect_solve_listener.messages,
            [
                ("on_start_patch", PatchType.CODE.value),
                (
                    "on_run_test",
                    TestType.PASS_TO_PASS.value,
                    [trim_patch(patch)],
                    trim_patch(empty_patch(Path("test_file"))),
                    TestStatus.PASSED.value,
                ),
                (
                    "on_run_test",
                    TestType.PASS_TO_FAIL.value,
                    [trim_patch(patch)],
                    trim_patch(Patch(EXAMPLE_TEST_PATCH)),
                    TestStatus.FAILED.value,
                ),
                (
                    "on_run_test",
                    TestType.FAIL_TO_PASS.value,
                    [trim_patch(patch)],
                    trim_patch(Patch(EXAMPLE_TEST_PATCH)),
                    TestStatus.PASSED.value,
                ),
                ("on_end_patch",),
            ],
        )

        self.assertEqual(result.patch, patch)
        self.assertEqual(len(result.code_patches), 1)
        self.assertEqual(result.code_patches[0].patch, patch)
        self.assertEqual(
            result.code_patches[0].pass_to_pass_test_status, TestStatus.PASSED
        )
        self.assertEqual(result.code_patches[0].test_patch_status, TestStatus.FAILED)
        self.assertEqual(
            result.code_patches[0].inverted_patch_status, TestStatus.PASSED
        )

    def test_generate_and_validate_code_failed_patch(self):
        self.generate_code.return_value = Patch(EXAMPLE_CODE_PATCH)
        self.run_test.return_value = RunTestResult(TestStatus.FAILED, "FAILED", True)

        result = generate_and_validate_code(
            context=self.context,
            plan=self.plan,
            generate_code=self.generate_code,
            run_test=self.run_test,
            pass_to_pass_test_file=Path("test_file"),
            test_patch=Patch(EXAMPLE_TEST_PATCH),
            test_patch_inverted=Patch(EXAMPLE_TEST_PATCH),
        )

        self.assertIsNone(result.patch)
        self.assertEqual(len(result.code_patches), 3)
        self.assertEqual(
            [msg[0] for msg in self.collect_solve_listener.messages],
            [
                "on_start_patch",
                "on_run_test",
                "on_run_test",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_run_test",
                "on_run_test",
                "on_end_patch",
                "on_start_patch",
                "on_run_test",
                "on_run_test",
                "on_run_test",
                "on_end_patch",
            ],
        )

    def test_generate_and_validate_code_partial_success(self):
        self.generate_code.side_effect = [
            None,
            Patch(EXAMPLE_CODE_PATCH),
            Patch(EXAMPLE_CODE_PATCH),
        ]
        self.run_test.side_effect = [
            RunTestResult(
                test_status=TestStatus.PASSED, test_output="PASSED", run_succeeded=True
            ),
            RunTestResult(
                test_status=TestStatus.FAILED, test_output="FAILED", run_succeeded=True
            ),
            RunTestResult(
                test_status=TestStatus.FAILED, test_output="FAILED", run_succeeded=True
            ),
            RunTestResult(
                test_status=TestStatus.PASSED, test_output="PASSED", run_succeeded=True
            ),
            RunTestResult(
                test_status=TestStatus.FAILED, test_output="FAILED", run_succeeded=True
            ),
            RunTestResult(
                test_status=TestStatus.PASSED, test_output="PASSED", run_succeeded=True
            ),
        ]

        result = generate_and_validate_code(
            context=self.context,
            plan=self.plan,
            generate_code=self.generate_code,
            run_test=self.run_test,
            pass_to_pass_test_file=Path("test_file"),
            test_patch=Patch("test_patch"),
            test_patch_inverted=Patch("test_patch_inverted"),
        )

        self.assertEqual(result.patch, Patch(EXAMPLE_CODE_PATCH))
        self.assertEqual(len(result.code_patches), 2)

    def test_generate_and_validate_code_no_test_patches(self):
        patch = Patch(EXAMPLE_CODE_PATCH)
        self.generate_code.return_value = patch
        self.run_test.return_value = RunTestResult(
            test_status=TestStatus.PASSED, test_output="PASSED", run_succeeded=True
        )

        result = generate_and_validate_code(
            context=self.context,
            plan=self.plan,
            generate_code=self.generate_code,
            run_test=self.run_test,
            pass_to_pass_test_file=Path("test_file"),
            test_patch=None,
            test_patch_inverted=None,
        )

        self.assertEqual(result.patch, patch)
        self.assertEqual(len(result.code_patches), 1)
        self.assertEqual(result.code_patches[0].patch, patch)
        self.assertEqual(
            result.code_patches[0].pass_to_pass_test_status, TestStatus.PASSED
        )
        self.assertIsNone(result.code_patches[0].test_patch_status)
        self.assertIsNone(result.code_patches[0].inverted_patch_status)


if __name__ == "__main__":
    unittest.main()
