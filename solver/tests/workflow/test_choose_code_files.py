import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from solver.workflow.choose_code_files import choose_code_files
from solver.workflow.work_dir import WorkDir


class TestChooseCodeFiles(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.work_dir = WorkDir("./work/directory", write_sequence=False)
        self.trajectory_file = os.path.join(self.work_dir.path_name, "trajectory.jsonl")
        self.issue_content = "Sample issue content"
        self.validate_true = lambda x, y: True
        self.validate_false = lambda x, y: False

    @patch("solver.workflow.choose_code_files.Editor")
    @patch("solver.workflow.choose_code_files.os.path.exists")
    def test_choose_code_files_from_mixed_content(self, exists_mock, Editor_mock):
        mixed_content_response = """2024-10-28 00:26:50,931 - INFO - [choose-code-file] (django__django-11848) Found no existing code files in Based on the problem statement and code context, I'll identify the 3 most relevant files for fixing the incorrect two-digit year handling in parse_http_date:

django/utils/http.py
django/views/decorators/http.py
django/utils/http.py

The primary file is django/utils/http.py since it contains the parse_http_date function with the problematic year handling logic. The issue is specifically in the code block that handles two-digit years:

if year < 100:
    if year < 70:
        year += 2000
    else:
        year += 1900

The other files are relevant because:

1. django/views/decorators/http.py uses the parse_http_date functionality for HTTP request handling and conditional responses

2. django/db/models/functions/datetime.py contains related date/time handling functionality that may need to be considered when fixing the year handling logic

The fix would need to be implemented in django/utils/http.py to compare against the current year rather than using hardcoded values of 70, as specified in RFC 7231.
"""

        exists_mock.side_effect = lambda x: x.endswith(".py")
        editor_instance_mock = Editor_mock.return_value
        editor_instance_mock.search.return_value = mixed_content_response

        results = choose_code_files(
            self.log_mock,
            self.work_dir,
            self.trajectory_file,
            self.issue_content,
            3,
        )
        self.assertEqual(
            results,
            [
                Path("django/utils/http.py"),
                Path("django/views/decorators/http.py"),
                Path("django/db/models/functions/datetime.py"),
            ],
        )
