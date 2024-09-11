from argparse import ArgumentParser
from os import environ
from pathlib import Path
from subprocess import run
import sys
from typing import Optional

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.harness.image_store import ImageStore
from solver.predictions_file import PredictionsFile
from solver.cli import (
    configure_clean_option,
    configure_limits,
    configure_runner_index,
    load_dataset,
    select_instances_for_runner,
)

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
DATASET_SPLIT = "test"


def main(
    instance_set: str,
    instance_ids: list,
    clean_work_dir: bool,
    clean_navie: bool,
    limit: list,
    num_runners: Optional[int] = None,
    runner_index: Optional[int] = None,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    if not instance_ids:
        instance_ids = []

    if instance_set:
        instance_set_file = (
            Path(__file__).resolve().parents[1]
            / "instance_sets"
            / f"{instance_set}.txt"
        )
        with instance_set_file.open() as f:
            instance_ids.extend([id for id in f.read().splitlines() if id])

    dataset = load_dataset(DATASET_NAME, instance_ids)
    dataset = select_instances_for_runner(dataset, num_runners, runner_index)

    if not dataset:
        print("[solve] No instances to run.")
        return

    print(f"[solve] Running {len(dataset)} unevaluated instances...")

    docker_client = docker.from_env()

    test_specs = [make_test_spec(instance) for instance in dataset]
    image_store = ImageStore(
        docker_client,
    )
    image_store.set_image_types(["base", "env"])
    image_store.ensure(test_specs)

    def log_fn(context, msg):
        print(f"[{context}] {msg}")

    predictions_manager = PredictionsFile(
        log_fn,
        instance_set,
        num_runners,
        runner_index,
    )

    # TODO: Parallelize this
    # Make inferences
    solver_path = Path(__file__).parent / "solve_instance.py"

    for instance in dataset:
        print(f"[solve] Running instance {instance['instance_id']}...")
        solve_args = [
            "python",
            str(solver_path),
            "--instance_id",
            instance["instance_id"],
            "--predictions",
            str(predictions_manager.predictions_path),
        ]
        if clean_work_dir:
            solve_args.append("--clean_work_dir")
        if clean_navie:
            solve_args.append("--clean_navie")
        if limit:
            solve_args.append("--limit")
            solve_args.extend(limit)

        print(f"[solve] Running: {' '.join(solve_args)}")

        # Run this as a separate process so that it can change the working directory.
        solve_result = run(solve_args)

        if solve_result.returncode != 0:
            print(f"[solve] Failed to run instance {instance['instance_id']}")

    print("[solve] Writing predictions to predictions.jsonl")
    predictions_manager.collect_predictions(Path("predictions.jsonl"))

    print("[solve] Done!")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "--instance_set",
        type=str,
        help="Instance set to run",
    )
    configure_runner_index(parser)
    configure_clean_option(parser)
    configure_limits(parser)

    args = parser.parse_args()

    appmap_command = environ.get("APPMAP_COMMAND")
    if appmap_command:
        print(f"[solve] Running with appmap command: {appmap_command}")

    if environ.get("OPENAI_API_KEY"):
        print("[solve] Running with OpenAI API key")
    elif environ.get("ANTHROPIC_API_KEY"):
        print("[solve] Running with Anthropic API key")
    else:
        print("[solve] WARNING: OpenAI API key not found in environment")

    main(**vars(args))
