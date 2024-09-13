import unittest
from swebench.harness.log_parsers import parse_log_sympy
from swebench.harness.constants import TestStatus


class TestParseLogSympy(unittest.TestCase):
    def test_parse_log_sympy(self):
        log = """
        test_printing_cyclic ok
        test_printing_non_cyclic ok                                                 [OK]
        test_failure_case F
        test_error_case E
        """
        expected_output = {
            "test_printing_cyclic": TestStatus.PASSED.value,
            "test_printing_non_cyclic": TestStatus.PASSED.value,
            "test_failure_case": TestStatus.FAILED.value,
            "test_error_case": TestStatus.ERROR.value,
        }
        self.assertEqual(parse_log_sympy(log), expected_output)


if __name__ == "__main__":
    unittest.main()
