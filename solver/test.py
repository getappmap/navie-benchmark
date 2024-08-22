import sys
import pathlib

# This is a utility script to run all tests in the solver module.
# Invoke from the project directory: python -m solver.test


sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.append(
    str(pathlib.Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)

if __name__ == "__main__":
    import pytest

    pytest.main(["solver/tests"])
