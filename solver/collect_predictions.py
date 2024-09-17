from argparse import ArgumentParser
import json
from os import readlink
from pathlib import Path
import sys
from typing import Optional
import zipfile

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.load_instance_set import load_instance_set

def find_prediction_in_zip_archive(zip_file: Path, instance_id: str) -> Optional[dict]:
    with zipfile.ZipFile(zip_file, "r") as z:
        for name in z.namelist():
            with z.open(name) as zf:
                data = zf.readlines()
                prediction_lines = [
                    json.loads(line) for line in data if line.strip()
                ]
                prediction = [
                    p
                    for p in prediction_lines
                    if p["instance_id"] == instance_id
                ]
                if prediction:
                    return prediction[0]
                
    return None


def main(instance_set: str, prediction_path: str):
    print(f"Collecting predictions for {instance_set}")

    instance_ids = load_instance_set(instance_set)

    # Collect every instance in data/code_patches/*.json
    code_patches_dir = Path("data") / "code_patches"
    solution_files = [
        p for p in list(code_patches_dir.rglob("*.json")) if p.stem in instance_ids
    ]

    predictions: list = []
    for solution_file in solution_files:
        solution_file_link_source = (
            Path("data") / "solve_code_runs" / readlink(solution_file)
        )
        with solution_file_link_source.open() as f:
            solution = json.load(f)
        print(f"Locating prediction for {solution["instance_id"]}")
        run_dir = solution_file_link_source.parent.parent
        predictions_files = run_dir.glob("predictions-*.zip")
        for predictions_file in predictions_files:
            prediction = find_prediction_in_zip_archive(predictions_file, solution["instance_id"])
            if prediction:
                predictions.append(prediction)
                break

    print(f"Collected {len(predictions)} predictions")
    for instance_id in instance_ids:
        if not any(p["instance_id"] == instance_id for p in predictions):
            print(f"No optimal prediction for {instance_id}. Search available solution files...")

    predictions = sorted(predictions, key=lambda p: p["instance_id"])
    with open(prediction_path, "w") as f:
        for prediction in predictions:
            f.write(json.dumps(prediction) + "\n")


if __name__ == "__main__":
    """
    Collects optimal predictions for a given instance set. The code solutions are read from the
    data/code_patches directory and the predictions are read from the predictions-*.zip files
    that are stored in the data/solve_code_runs directory. The predictions are matched to the
    code solutions by instance ID. The predictions are written to a file in JSONL format.

    Currently, only optimal solutions are collected for evaluation.
    """
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_set",
        type=str,
        help="Instance set to run",
    )
    parser.add_argument(
        "--prediction_path",
        type=str,
        help="File to write predictions to",
        default="predictions.jsonl",
    )

    args = parser.parse_args()
    main(**vars(args))
