import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from solver.workflow.solve_code import SolveCode
from solver.workflow.solve_listener import TestStatus

class TestSolveCode(unittest.TestCase):
    def setUp(self):
        log = MagicMock()
        work_dir = MagicMock()
        docker_client = MagicMock()
        test_spec = MagicMock()
        issue_text = "Sample issue text"
        limits = MagicMock()
        limits.code_files_limit = 10
        limits.code_lint_retry_limit = 3
        edit_test_file = None
        test_patch = None
        inverted_patch = None
        observe_enabled = False

        self.solver = SolveCode(
            log=log,
            work_dir=work_dir,
            docker_client=docker_client,
            test_spec=test_spec,
            issue_text=issue_text,
            limits=limits,
            edit_test_file=edit_test_file,
            test_patch=test_patch,
            inverted_patch=inverted_patch,
            observe_enabled=observe_enabled
        )

        self.solver.generate_plan = MagicMock(return_value='Generated plan')

    @patch('solver.workflow.solve_code.choose_code_files')
    @patch('solver.workflow.solve_code.generate_and_validate_code')
    @patch('solver.workflow.solve_code.GeneratePlan')
    @patch('solver.workflow.solve_code.SolveBase.clean_git_state')
    @patch('solver.workflow.solve_code.SolveBase.write_patch_file')
    def test_solve_selects_optimal_code_patch(self,
                                              mock_write_patch_file,
                                              mock_clean_git_state,
                                              mock_GeneratePlan,
                                              mock_generate_and_validate_code,
                                              mock_choose_code_files):
        mock_choose_code_files.return_value = [Path('file1.py'), Path('file2.py')]

        non_optimal_result = MagicMock()
        non_optimal_result.patch = MagicMock(name='patch1')
        non_optimal_result.pass_to_pass_test_status = TestStatus.PASSED
        non_optimal_result.test_patch_status = TestStatus.PASSED
        non_optimal_result.inverted_patch_status = TestStatus.PASSED
        non_optimal_result.to_h.return_value = {
            'patch': 'patch1',
            'pass_to_pass_test_status': 'PASSED',
            'test_patch_status': 'PASSED',
            'inverted_patch_status': 'PASSED'
        }

        optimal_result = MagicMock()
        optimal_result.patch = MagicMock(name='patch2')
        optimal_result.pass_to_pass_test_status = TestStatus.PASSED
        optimal_result.test_patch_status = TestStatus.FAILED
        optimal_result.inverted_patch_status = TestStatus.PASSED
        optimal_result.to_h.return_value = {
            'patch': 'patch2',
            'pass_to_pass_test_status': 'PASSED',
            'test_patch_status': 'FAILED',
            'inverted_patch_status': 'PASSED'
        }

        non_optimal_generation = MagicMock()
        non_optimal_generation.patch = None
        non_optimal_generation.code_patches = [non_optimal_result]

        optimal_generation = MagicMock()
        optimal_generation.patch = optimal_result.patch
        optimal_generation.code_patches = [optimal_result]

        mock_generate_and_validate_code.side_effect = [non_optimal_generation, optimal_generation]

        self.solver.solve()

        self.assertEqual(self.solver.code_patch, optimal_generation.patch)
        mock_write_patch_file.assert_called_with('code', optimal_generation.patch)
        self.assertEqual(mock_generate_and_validate_code.call_count, 2)

if __name__ == '__main__':
    unittest.main()
