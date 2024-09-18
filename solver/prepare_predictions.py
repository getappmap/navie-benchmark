from argparse import ArgumentParser
import json
from os import readlink
from pathlib import Path
import sys
from typing import Optional
import zipfile
import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.cli import load_dataset
from solver.solve import DATASET_NAME
from solver.harness.image_store import ImageStore
from solver.load_instance_set import load_instance_set


def find_prediction_in_zip_archive(zip_file: Path, instance_id: str) -> Optional[dict]:
    if zip_file.is_symlink():
        zip_file = Path(readlink(zip_file))
    with zipfile.ZipFile(zip_file, "r") as z:
        for name in z.namelist():
            with z.open(name) as zf:
                data = zf.readlines()
                prediction_lines = [json.loads(line) for line in data if line.strip()]
                prediction = [
                    p for p in prediction_lines if p["instance_id"] == instance_id
                ]
                if prediction:
                    return prediction[0]

    return None


def main(instance_set: str, predictions_path: str, no_pull: bool):
    print(f"Preparing predictions for instance set '{instance_set}'")

    instance_ids = load_instance_set(instance_set)
    dataset = load_dataset(DATASET_NAME, list(instance_ids))

    if not no_pull:
        print("Loading Docker images...")
        docker_client = docker.from_env()
        test_specs = [make_test_spec(instance) for instance in dataset]
        image_store = ImageStore(
            docker_client,
        )
        image_store.set_image_types(["base", "env"])
        image_store.ensure(test_specs)

    # Collect every instance in data/code_patches/*.json
    code_patches_dir = Path("data") / "code_patches"
    solution_files = [
        p for p in list(code_patches_dir.rglob("*.json")) if p.stem in instance_ids
    ]

    predictions: list = []
    for solution_file in solution_files:
        if solution_file.is_symlink():
            solution_file_link_source = (
                Path("data") / "solve_code_runs" / readlink(solution_file)
            )
            with solution_file_link_source.open() as f:
                solution = json.load(f)
            run_dir = solution_file_link_source.parent.parent
            predictions_files = run_dir.glob("predictions-*.zip")
            for predictions_file in predictions_files:
                prediction = find_prediction_in_zip_archive(
                    predictions_file, solution["instance_id"]
                )
                if prediction:
                    predictions.append(prediction)
                    break
        else:
            instance_id = solution_file.stem

            def prediction_for_solution_file():
                predictions_dir = Path("data") / "predictions_issue-46"
                prediction_file = predictions_dir / f"{instance_id}.json"
                with prediction_file.open() as f:
                    return json.load(f)

            print(
                f"Loading prediction for {instance_id} from data/predictions_issue-46",
                file=sys.stderr,
            )
            predictions.append(prediction_for_solution_file())

    print(f"Collected {len(predictions)} predictions (out of {len(instance_ids)}).")
    for instance_id in instance_ids:
        if not any(p["instance_id"] == instance_id for p in predictions):
            print(f"No optimal prediction found for: {instance_id}")

    predictions = sorted(predictions, key=lambda p: p["instance_id"])
    with open(predictions_path, "w") as f:
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
        "--predictions_path",
        type=str,
        help="File to write predictions to",
        default="predictions.jsonl",
    )
    parser.add_argument(
        "--no_pull",
        action="store_true",
        help="Do not pull Docker images",
    )

    args = parser.parse_args()
    main(**vars(args))
