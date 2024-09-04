from json import dumps
from pathlib import Path
from typing import Callable, Optional


class PredictionsManager:
    def __init__(
        self,
        log: Callable[[str, str], None],
        instance_set=None,
        num_runners=None,
        runner_index=None,
        directory: Path = Path(__file__).resolve().parents[1] / "predictions",
    ):
        self.log = log
        self.predictions_name = PredictionsManager._generate_predictions_name(
            instance_set, num_runners, runner_index
        )
        self.predictions_dir = directory
        self.predictions_dir.mkdir(parents=True, exist_ok=True)
        self.predictions_path = self.predictions_dir / f"{self.predictions_name}.jsonl"

        self._handle_existing_predictions_file()

    def _handle_existing_predictions_file(self) -> None:
        if self.predictions_path.exists():
            new_predictions_path = (
                self.predictions_dir
                / f"{self.predictions_name}.{int(self.predictions_path.stat().st_mtime)}.jsonl"
            )
            self.predictions_path.rename(new_predictions_path)
            self.log(
                "predictions-manager",
                f"Renamed existing predictions file from {self.predictions_path} to {new_predictions_path}",
            )

    def write_predictions(self, predictions) -> None:
        with self.predictions_path.open("a") as f:
            f.write(predictions)

    def read_predictions(self) -> Optional[str]:
        if not self.predictions_path.exists():
            return None

        with self.predictions_path.open("r") as f:
            return f.read()

    def collect_predictions(self, path: Path) -> Optional[str]:
        predictions = self.read_predictions()
        if predictions:
            with path.open("a") as f:
                f.write(predictions)

    @staticmethod
    def add_prediction(predictions_file: str, prediction: dict) -> None:
        with open(predictions_file, "a") as f:
            f.write(dumps(prediction) + "\n")

    @staticmethod
    def _generate_predictions_name(instance_set, num_runners, runner_index) -> str:
        if instance_set:
            predictions_name = instance_set
            if num_runners is not None and runner_index is not None:
                predictions_name += f"-{runner_index}_{num_runners}"
        else:
            predictions_name = "predictions"
        return predictions_name
