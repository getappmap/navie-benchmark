from pathlib import Path
from typing import IO, Any, Union


def make_path(path: Union[str | Path]) -> Path:
    if isinstance(path, str):
        path = Path(path)
    return path
