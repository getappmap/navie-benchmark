from argparse import ArgumentParser
from os import environ
from pathlib import Path
from subprocess import run
import sys

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.docker_build import build_base_images, build_env_images

from solver.cli import configure_clean_option, configure_limits, load_dataset
from solver.harness.pull_images import pull_instance_images

DATASET_NAME = "princeton-nlp/SWE-bench_Verified"
DATASET_SPLIT = "test"


def main(instance_ids: list, clean_work_dir: bool, limit: list):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    dataset = load_dataset(DATASET_NAME, instance_ids)

    if not dataset:
        print("[solve] No instances to run.")
        return

    print(f"[solve] Running {len(dataset)} unevaluated instances...")

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
            "--instance_id",
            instance["instance_id"],
        ]
        if clean_work_dir:
            solve_args.append("--clean_work_dir")
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
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )

    configure_clean_option(parser)
    configure_limits(parser)

    args = parser.parse_args()

    appmap_command = environ.get("APPMAP_COMMAND")
    if appmap_command:
        print(f"[solve] Running with appmap command: {appmap_command}")

    if environ.get("OPENAI_API_KEY"):
        print("[solve] Running with OpenAI API key")
    else:
        print("[solve] WARNING: OpenAI API key not found in environment")

    main(**vars(args))
