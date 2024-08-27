from argparse import ArgumentParser
from os import environ
from pathlib import Path
from subprocess import run
import sys

import docker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.docker_build import build_base_images, build_env_images
from swebench.harness.utils import load_swebench_dataset

from solver.harness.pull_images import pull_instance_images


def main(
    dataset_name: str, split: str, instance_ids: list, reuse_work_dir: bool, limit: list
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    # Collect all instance ids by splitting each instance id by space
    if instance_ids:
        instance_ids = [
            id for instance_id in instance_ids for id in instance_id.split()
        ]
        print(f"[solve] Running instances: {instance_ids}")

    full_dataset = load_swebench_dataset(dataset_name, split, instance_ids)
    dataset = full_dataset
    print(f"[solve] Running {len(dataset)} unevaluated instances...")
    if not dataset:
        print("[solve] No instances to run.")
        return

    docker_client = docker.from_env()

    pull_instance_images(docker_client, dataset)
    build_base_images(docker_client, dataset)
    build_env_images(docker_client, dataset)

    # TODO: Parallelize this
    # Make inferences
    solver_path = Path(__file__).parent / "solve_instance.py"

    for instance in dataset:
        print(f"[solve] Running instance {instance['instance_id']}...")
        solve_args = [
            "python",
            str(solver_path),
            "--dataset_name",
            dataset_name,
            "--instance_id",
            instance["instance_id"],
        ]
        if reuse_work_dir:
            solve_args.append("--reuse_work_dir")
        if limit:
            solve_args.append("--limit")
            solve_args.extend(limit)

        print(f"[solve] Running: {' '.join(solve_args)}")

        # Run this as a separate process so that it can change the working directory.
        solve_result = run(solve_args)

        if solve_result.returncode != 0:
            print(f"[solve] Failed to run instance {instance['instance_id']}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--dataset_name",
        default="princeton-nlp/SWE-bench_Lite",
        type=str,
        help="Name of dataset or path to JSON file.",
    )
    parser.add_argument(
        "--split", type=str, default="test", help="Split of the dataset"
    )
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "--reuse_work_dir",
        action="store_true",
        help="Reuse the work directory if it exists",
        default=False,
    )
    parser.add_argument(
        "--limit",
        type=str,
        help="Set a configurable limit as key=value. Valid keys are: ['time', 'memory']",
        nargs="+",
    )

    args = parser.parse_args()

    appmap_command = environ.get("APPMAP_COMMAND")
    if appmap_command:
        print(f"[solve] Running with appmap command: {appmap_command}")

    if environ.get("OPENAI_API_KEY"):
        print("[solve] Running with OpenAI API key")
    else:
        print("[solve] WARNING: OpenAI API key not found in environment")

    main(**vars(args))
