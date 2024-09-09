from typing import Union
from solver.workflow.patch import Patch
from swebench.harness.constants import SWEbenchInstance


from pathlib import Path


class Prediction:
    def __init__(self, instance: SWEbenchInstance, llm: str):
        self.prediction_data: dict = instance.copy()  # type: ignore
        self.model_name_or_path = f"navie_082024+{llm}"

        self.add_prediction("model_patch", None)
        self.add_prediction("model_name_or_path", self.model_name_or_path)
        self.add_prediction("model_test_patch", None)
        self.add_prediction("model_inverted_patch", None)
        self.add_prediction("model_edit_test_file", None)

    def as_dict(self):
        return self.prediction_data

    def add_prediction(self, key: str, value: Union[str, Patch, Path, None]):
        self.prediction_data[key] = str(value) if value else None

    @staticmethod
    def build_predictions(instance: SWEbenchInstance, llm: str):
        return Prediction(instance, llm)
