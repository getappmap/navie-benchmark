import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from inline_snapshot import snapshot

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

    def test_choose_code_files_from_mixed_content(self):
        assert (
            self.check(
                """2024-10-28 00:26:50,931 - INFO - [choose-code-file] (django__django-11848) Found no existing code files in Based on the problem statement and code context, I'll identify the 3 most relevant files for fixing the incorrect two-digit year handling in parse_http_date:

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
            )
            == snapshot(
                [
                    Path("django/utils/http.py"),
                    Path("django/views/decorators/http.py"),
                    Path("django/db/models/functions/datetime.py"),
                ]
            )
        )

    def test_relative_absolute_paths(self):
        # Sometimes LLM emits paths that look absolute but are relative to the work directory
        assert (
            self.check(
                """Found no existing code files in Based on the code snippets provided, I can identify the issue in the Quaternion rotation matrix implementation. Let me analyze the most relevant files:

1. /sympy/algebras/quaternion.py
This contains the core implementation of the quaternion class and the problematic to_rotation_matrix() method.

2. /sympy/vector/orienters.py
This shows how quaternion rotations are used in the vector orientation system.

3. /sympy/physics/vector/frame.py
This demonstrates how quaternion rotations are used in reference frames.
"""
            )
            == snapshot(
                [
                    Path("sympy/algebras/quaternion.py"),
                    Path("sympy/vector/orienters.py"),
                    Path("sympy/physics/vector/frame.py"),
                ]
            )
        )

    def test_is_not_confused_by_fences(self):
        # Sometimes LLM adds extra content, such as fenced code blocks which can be confusing
        assert (
            self.check(
                """Based on the code snippets provided, I can identify the issue in the Quaternion rotation matrix implementation. Let me analyze the most relevant files:

1. /sympy/algebras/quaternion.py
This contains the core implementation of the quaternion class and the problematic to_rotation_matrix() method.

2. /sympy/vector/orienters.py
This shows how quaternion rotations are used in the vector orientation system.

3. /sympy/physics/vector/frame.py
This demonstrates how quaternion rotations are used in reference frames.

The issue is in the to_rotation_matrix() implementation. For a rotation about the x-axis by angle x, the correct rotation matrix should be:

```
[1,      0,       0]
[0,  cos(x), -sin(x)]
[0,  sin(x),  cos(x)]
```

The current implementation produces:

```
[1,      0,     0]
[0,  cos(x), sin(x)]
[0,  sin(x), cos(x)]
```

The error appears to be in the sign of the m12 term (the sin(x) in the middle row). This is a well-known rotation matrix form that can be found in standard robotics and computer graphics texts.

The quaternion-to-rotation-matrix conversion is documented in the code comments referencing:
- http://www.euclideanspace.com/maths/algebra/realNormedAlgebra/quaternions/
- https://en.wikipedia.org/wiki/Quaternion

The error likely stems from a sign error in the conversion formula implementation, not accounting for the proper relationship between quaternion components and rotation matrix elements.

This issue affects the correctness of rotations when using quaternions in SymPy's vector and physics modules.
"""
            )
            == snapshot(
                [
                    Path("sympy/algebras/quaternion.py"),
                    Path("sympy/vector/orienters.py"),
                    Path("sympy/physics/vector/frame.py"),
                ]
            )
        )

    def check(self, response: str):
        with patch("solver.workflow.choose_code_files.Editor") as Editor_mock, patch(
            "solver.workflow.choose_code_files.os.path.exists"
        ) as exists_mock:
            exists_mock.side_effect = lambda x: (
                x.startswith("django") or x.startswith("sympy")
            ) and x.endswith(".py")
            editor_instance_mock = Editor_mock.return_value
            editor_instance_mock.search.return_value = response
            results = choose_code_files(
                self.log_mock,
                self.work_dir,
                self.trajectory_file,
                self.issue_content,
                3,
            )
            return results
