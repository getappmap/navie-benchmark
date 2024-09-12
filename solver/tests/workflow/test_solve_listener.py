from typing import List
from unittest.mock import patch
import pytest
from pathlib import Path
from solver.workflow.solution_listener import SolutionListener, solution_to_plain_types
from solver.workflow.solve_listener import (
    PatchType,
    TestType,
    TestStatus,
)
from solver.workflow.patch import Patch

TEST_PATCH = """diff --git a/sympy/geometry/tests/test_point2d_evaluate.py b/sympy/geometry/tests/test_point2d_evaluate.py
new file mode 100644
index 0000000..50e0f87
--- /dev/null
+++ b/sympy/geometry/tests/test_point2d_evaluate.py
@@ -0,0 +1,13 @@
+import pytest
+from sympy import S, evaluate
+from sympy.core.sympify import SympifyError
+
+def test_point2d_evaluate_false():
+    # Test that Point2D raises ValueError with evaluate(False)
+    with pytest.raises(ValueError, match="Imaginary coordinates are not permitted."):
+        with evaluate(False):
+            S('Point2D(Integer(1),Integer(2))')
+
+    # Test that Point2D works without evaluate(False)
+    assert S('Point2D(Integer(1),Integer(2))') is not None
+    assert S('Point2D(Integer(1),Integer(2))', evaluate=False) is not None
\\ No newline at end of file
"""

CODE_PATCH = """diff --git a/django/core/management/__init__.py b/django/core/management/__init__.py
index 1ba093e..e411e86 100644
--- a/django/core/management/__init__.py
+++ b/django/core/management/__init__.py
@@ -344,7 +344,7 @@ class ManagementUtility:
         # Preprocess options to extract --settings and --pythonpath.
         # These options could affect the commands that are available, so they
         # must be processed early.
-        parser = CommandParser(usage='%(prog)s subcommand [options] [args]', add_help=False, allow_abbrev=False)
+        parser = CommandParser(prog=self.prog_name, usage='%(prog)s subcommand [options] [args]', add_help=False, allow_abbrev=False)
         parser.add_argument('--settings')
         parser.add_argument('--pythonpath')
         parser.add_argument('args', nargs='*')  # catch-all
"""


class TestSolveListenerTestCase:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.instance_id = "django__django-11095"
        self.listener = SolutionListener(self.instance_id)

    @patch.object(SolutionListener, "count_llm_chars", return_value=(1000, 20))
    def test_minimal_events_received(self, mock_count_llm_chars):
        self.listener.on_solve_start(Path("path/to/work_dir"))
        self.listener.on_completed()

        solution = self.listener.build_solution()
        solution_attrs = solution_to_plain_types(solution)
        assert solution_attrs == {
            "instance_id": "django__django-11095",
            "edit_test_file": None,
            "code_patch": None,
            "test_patch": None,
            "test_inverted_patch": None,
            "num_sent_chars": 1000,
            "num_received_chars": 20,
            "elapsed_time": solution["elapsed_time"],
            "lint_repair_count": 0,
            "test_generation_attempts": 0,
            "code_generation_attempts": 0,
            "pass_to_pass": False,
            "pass_to_fail": False,
            "fail_to_pass": False,
            "code_patch_score": None,
            "appmap_data_test_status": None,
            "appmap_data_file_count": None,
            "appmap_data_context_size": None,
        }

    @patch.object(SolutionListener, "count_llm_chars", return_value=(1000, 20))
    def test_workflow_simulation(self, mock_count_llm_chars):
        # Simulate the workflow
        self.listener.on_solve_start(Path("path/to/work_dir"))
        self.listener.on_start_patch(PatchType.TEST)
        self.listener.on_lint_repair(2, True)
        self.listener.on_end_patch()
        self.listener.on_start_patch(PatchType.CODE)
        self.listener.on_end_patch()
        self.listener.on_test_patch(Path("edit_test_file.py"), Patch(TEST_PATCH), None)
        self.listener.on_run_test(
            TestType.PASS_TO_PASS, [], Patch(TEST_PATCH), TestStatus.PASSED
        )
        self.listener.on_observe_test_patch(
            TestStatus.PASSED,
            [Path("appmap_dir")],
            {
                "file1.appmap.json": "file-content-1",
                "file2.appmap.json": "file-content-2",
            },
        )
        self.listener.on_code_patch(Patch(CODE_PATCH), True, False, True, 2)
        self.listener.on_completed()

        solution = self.listener.build_solution()
        solution_attrs = solution_to_plain_types(solution)
        assert solution_attrs == {
            "instance_id": "django__django-11095",
            "edit_test_file": "edit_test_file.py",
            "code_patch": CODE_PATCH,
            "test_patch": TEST_PATCH,
            "test_inverted_patch": None,
            "num_sent_chars": 1000,
            "num_received_chars": 20,
            "elapsed_time": solution["elapsed_time"],
            "lint_repair_count": 1,
            "test_generation_attempts": 1,
            "code_generation_attempts": 1,
            "pass_to_pass": True,
            "pass_to_fail": False,
            "fail_to_pass": True,
            "code_patch_score": 2,
            "appmap_data_test_status": "PASSED",
            "appmap_data_file_count": 1,
            "appmap_data_context_size": sum(
                [len("file-content-1"), len("file-content-2")]
            ),
        }
