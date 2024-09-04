import json
import os
import csv
from pathlib import Path
import sys
from typing import List, TypedDict

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.workflow.patch import Patch
from solver.workflow.solution_listener import Solution


class Prediction(TypedDict):
    instance_id: str
    repo: str
    base_commit: str
    patch: str
    test_patch: str
    created_at: str
    version: str
    model_name_or_path: str
    model_edit_test_file: str
    # These are available in the solution.json
    # model_patch: str
    # model_test_patch: str
    # model_inverted_patch: str
    # These don't report very well, or we don't care
    # hints_text: str
    # FAIL_TO_PASS: List[str]
    # PASS_TO_PASS: List[str]
    # environment_setup_commit: str
    # problem_statement: str


class EvaluationReport(TypedDict):
    instance_id: str
    patch_is_None: bool
    patch_exists: bool
    patch_successfully_applied: bool
    resolved: bool


class Report:
    """
    Build a CSV report that combines evaluations results with the solution.json files
    generated by the solver.
    """

    def __init__(self, solve_data_dir, predictions_file, evaluation_logs_dir):
        self.solve_data_dir = solve_data_dir
        self.predictions_file = predictions_file
        self.evaluation_logs_dir = evaluation_logs_dir

    def generate(self):
        def list_patch_files(patch: str) -> str:
            return " ".join(Patch(patch).list_files())

        solutions: dict[str, Solution] = {}
        for root, dirs, files in os.walk(self.solve_data_dir):
            for file in files:
                if file == "solution.json":
                    solution_data = json.load(open(Path(root) / file))
                    for patch_field in [
                        "code_patch",
                        "test_patch",
                        "test_inverted_patch",
                    ]:
                        if patch_field in solution_data:
                            solution_data[patch_field] = list_patch_files(
                                solution_data[patch_field]
                            )
                    if not solution_data.get("instance_id"):
                        root_tokens = root.split("/")
                        instance_id = root_tokens[1]
                        solution_data["instance_id"] = instance_id
                    assert "instance_id" in solution_data
                    solution = Solution(**solution_data)
                    solutions[solution["instance_id"]] = solution

        print(f"Loaded {len(solutions)} solutions")

        # Load predictions.jsonl
        predictions: dict[str, Prediction] = {}
        with open(self.predictions_file) as f:
            for line in f:
                data = json.loads(line)
                data = {
                    k: v for k, v in data.items() if k in Prediction.__annotations__
                }
                assert "instance_id" in data

                data["gold_patch"] = list_patch_files(data["patch"])
                data["gold_test_patch"] = list_patch_files(data["test_patch"])
                del data["patch"]
                del data["test_patch"]

                prediction = Prediction(**data)
                predictions[prediction["instance_id"]] = prediction
        print(f"Loaded {len(predictions)} predictions")

        # Load EvaluationReport
        evaluation_reports: dict[str, EvaluationReport] = {}
        for root, dirs, files in os.walk(self.evaluation_logs_dir):
            for file in files:
                if file == "report.json":
                    data = json.load(open(Path(root) / file))
                    for key in data:
                        data_item = data[key]
                        data_item = {
                            k: v
                            for k, v in data_item.items()
                            if k in EvaluationReport.__annotations__
                        }
                        data_item["instance_id"] = key
                        assert "instance_id" in data_item
                        report = EvaluationReport(**data_item)
                        evaluation_reports[report["instance_id"]] = report
        print(f"Loaded {len(evaluation_reports)} evaluations")

        instance_ids = list(
            set(solutions.keys())
            | set(predictions.keys())
            | set(evaluation_reports.keys())
        )
        intersection_ids = (
            set(solutions.keys())
            & set(predictions.keys())
            & set(evaluation_reports.keys())
        )
        difference_ids = set(instance_ids) - intersection_ids
        if difference_ids:
            print(f"Instance IDs in one file but not the others: {" ".join(difference_ids)}")
        print(f"Reporting on {len(intersection_ids)} instances")

        instance_ids.sort()
        combined_data: list[dict] = []
        for instance_id in intersection_ids:
            solution = solutions.get(instance_id)
            prediction = predictions.get(instance_id)
            evaluation_report = evaluation_reports.get(instance_id)

            assert solution
            assert prediction
            assert evaluation_report

            # Collect all data into one record
            row = {}
            row.update(solution)
            row.update(prediction)
            row.update(evaluation_report)
            combined_data.append(row)

        report_file = Path("report.csv")
        with report_file.open("w") as f:
            writer = csv.DictWriter(f, fieldnames=combined_data[0].keys())
            writer.writeheader()
            writer.writerows(combined_data)


if __name__ == "__main__":
    """
    Build a CSV report that combines evaluations results with the solution.json files
    generated by the solver.
    """
    solve_data_dir = Path("solve")
    predictions_file = Path("predictions.jsonl")
    evaluation_logs_dir = Path("logs") / "run_evaluation"
    report = Report(solve_data_dir, predictions_file, evaluation_logs_dir)
    report = report.generate()
