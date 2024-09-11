from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Union


class WorkDir:
    def __init__(
        self,
        dir: Union[Path, str],
        parent: Optional[WorkDir] = None,
        write_sequence: bool = True,
    ):
        if isinstance(dir, str):
            dir = Path(dir)
        self._dir = dir

        self._parent = parent
        self._write_sequence = write_sequence

        if self._parent is None:
            if write_sequence:
                self._dir.mkdir(parents=True, exist_ok=True)
                sequence_file = self._dir / "sequence.txt"
                with sequence_file.open("w") as f:
                    f.write("")
        else:
            root = self.root
            if root._write_sequence:
                sequence_file = root.path / "sequence.txt"
                dir_relative_to_root = self._dir.relative_to(root.path)
                with sequence_file.open("a") as f:
                    f.write(f"{dir_relative_to_root}\n")

    def __repr__(self) -> str:
        return f"WorkDir({self._dir})"

    def __str__(self) -> str:
        return str(self._dir)

    @property
    def path(self) -> Path:
        return self._dir

    @property
    def path_name(self) -> str:
        return str(self._dir)

    @property
    def root(self) -> WorkDir:
        work_dir = self
        while work_dir._parent is not None:
            work_dir = work_dir._parent

        return work_dir

    def choose_test_files(self) -> WorkDir:
        return WorkDir(self._dir / "choose-test-files", self)

    def choose_code_files(self) -> WorkDir:
        return WorkDir(self._dir / "choose-code-files", self)

    def plan(self) -> WorkDir:
        return WorkDir(self._dir / "plan", self)

    def observe_test_patch(self) -> WorkDir:
        return WorkDir(self._dir / "observe-test-patch", self)

    def generate_test(self, edit_test_file: Path, attempt: int) -> WorkDir:
        return WorkDir(
            self._dir
            / "generate-test"
            / f"attempt-{str(attempt)}_from-{edit_test_file.name}",
            self,
        )

    def test(self, attempt: int) -> WorkDir:
        return WorkDir(self._dir / f"test-{str(attempt)}", self)

    def invert(self) -> WorkDir:
        return WorkDir(self._dir / "invert", self)

    def summarize_test_errors(self) -> WorkDir:
        return WorkDir(self._dir / "summarize-test-errors", self)

    def generate_code(self, attempt: int) -> WorkDir:
        return WorkDir(self._dir / "generate-code" / f"attempt-{str(attempt)}", self)

    def code(self, attempt: int) -> WorkDir:
        return WorkDir(self._dir / f"code-{str(attempt)}", self)

    def run_pass_to_pass(self) -> WorkDir:
        return WorkDir(self._dir / "run-test" / "pass-to-pass", self)

    def run_test_patch(self) -> WorkDir:
        return WorkDir(self._dir / "run-test" / "test-patch", self)

    def run_test_inverted_patch(self) -> WorkDir:
        return WorkDir(self._dir / "run-test" / "test-inverted-patch", self)

    def apply(self) -> WorkDir:
        return WorkDir(self._dir / "apply", self)
