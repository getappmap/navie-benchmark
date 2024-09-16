from solver.workflow.solution_listener import SolutionListener
from solver.workflow.convert_to_plain_types import convert_to_plain_types
        solution_attrs = convert_to_plain_types(solution)
            "edit_test_file": None,
            "appmap_data_test_status": None,
            "appmap_data_file_count": None,
            "appmap_data_context_size": None,
        self.listener.on_observe_test_patch(
            TestStatus.PASSED,
            [Path("appmap_dir")],
            {
                "file1.appmap.json": "file-content-1",
                "file2.appmap.json": "file-content-2",
            },
        )
        solution_attrs = convert_to_plain_types(solution)
            "edit_test_file": "edit_test_file.py",
            "appmap_data_test_status": "PASSED",
            "appmap_data_file_count": 1,
            "appmap_data_context_size": sum(
                [len("file-content-1"), len("file-content-2")]
            ),