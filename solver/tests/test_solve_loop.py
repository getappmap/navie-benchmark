import unittest
from unittest.mock import patch, MagicMock
from solver.solve_loop import solve_loop


class TestMainFunction(unittest.TestCase):
    @patch("solver.solve_loop.load_instance_ids")
    @patch("solver.solve_loop.test_solver")
    @patch("solver.solve_loop.code_solver")
    @patch("solver.solve_loop.evaluate")
    @patch("solver.solve_loop.archive_test_logs")
    @patch("solver.solve_loop.archive_code_logs")
    @patch("solver.solve_loop.write_working_set")
    @patch("solver.solve_loop.confirm", return_value=True)
    def test_main_loop(
        self,
        mock_confirm,
        mock_write_working_set,
        mock_archive_code_logs,
        mock_archive_test_logs,
        mock_evaluate,
        mock_code_solver,
        mock_test_solver,
        mock_load_instance_ids,
    ):
        mock_load_instance_ids.return_value = ["instance1", "instance2"]
        mock_write_working_set.return_value = "new_instance_set"
        mock_test_solver_fn = MagicMock(return_value={"new_test_patch_count": 2})
        mock_test_solver.return_value = mock_test_solver_fn
        mock_code_solver_fn = MagicMock()
        mock_code_solver.return_value = mock_code_solver_fn
        mock_evaluate.return_value = MagicMock()

        # Define the arguments for the main function
        args = {
            "instance_set": "test_instance_set",
            "context_tokens": 8000,
            "context_token_limit_increase": 10,
            "temperature": 0.0,
            "temperature_increase": 0.1,
            "test_patch_solve_threshold": 1,
            "use_synthetic_tests": False,
            "num_runners": None,
            "runner_index": None,
            "min_test_solve_iterations": 1,
            "max_test_solve_iterations": 3,
        }

        solve_loop(**args)

        self.assertEqual(mock_test_solver.call_count, 1)
        self.assertEqual(mock_test_solver_fn.call_count, 3)
        self.assertEqual(mock_test_solver_fn.call_args_list[0], ((8000, 0),))
        self.assertEqual(mock_test_solver_fn.return_value, {"new_test_patch_count": 2})
        self.assertEqual(mock_test_solver_fn.call_args_list[1], ((8800, 0.1),))
        self.assertEqual(mock_test_solver_fn.call_args_list[2], ((9680, 0.2),))

        self.assertEqual(mock_code_solver.call_count, 1)
        self.assertEqual(mock_code_solver_fn.call_count, 1)
        self.assertEqual(list(mock_code_solver_fn.call_args_list[0]), [(8000,), {}])

        self.assertEqual(mock_evaluate.call_count, 1)
        self.assertEqual(mock_archive_test_logs.call_count, 1)
        self.assertEqual(mock_archive_code_logs.call_count, 1)
        self.assertEqual(mock_write_working_set.call_count, 2)


if __name__ == "__main__":
    unittest.main()
