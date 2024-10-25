# Set up the path to the navie-editor submodule

import sys
from pathlib import Path

sys.path.append(
    str(Path(__file__).resolve().parents[0] / "submodules" / "navie-editor")
)
