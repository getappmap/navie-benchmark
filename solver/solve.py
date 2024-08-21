from argparse import ArgumentParser
import resource
from time import time

import docker

from swebench.harness.docker_build import build_env_images
from swebench.harness.docker_utils import clean_images, list_images
from swebench.harness.utils import load_swebench_dataset, str2bool


def main(
    dataset_name: str,
    split: str,
    instance_ids: list,
    max_workers: int,
    force_rebuild: bool,
    cache_level: str,
    clean: bool,
    open_file_limit: int,
    run_id: str,
    timeout: int,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    resource.setrlimit(resource.RLIMIT_NOFILE, (open_file_limit, open_file_limit))
    client = docker.from_env()

    full_dataset = load_swebench_dataset(dataset_name, split, instance_ids)
    dataset = full_dataset
    existing_images = list_images(client)
    print(f"Running {len(dataset)} unevaluated instances...")
    if not dataset:
        print("No instances to run.")
        return

    # build environment images
    build_env_images(client, dataset, force_rebuild, max_workers)

    # make inferences


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
        "--max_workers",
        type=int,
        default=4,
        help="Maximum number of workers (should be <= 75%% of CPU cores)",
    )
    parser.add_argument(
        "--open_file_limit", type=int, default=4096, help="Open file limit"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1_800,
        help="Timeout (in seconds) for running tests for each instance",
    )
    parser.add_argument(
        "--force_rebuild",
        type=str2bool,
        default=False,
        help="Force rebuild of all images",
    )
    parser.add_argument(
        "--cache_level",
        type=str,
        choices=["none", "base", "env", "instance"],
        help="Cache level - remove images above this level",
        default="env",
    )
    # if clean is true then we remove all images that are above the cache level
    # if clean is false, we only remove images above the cache level if they don't already exist
    parser.add_argument(
        "--clean", type=str2bool, default=False, help="Clean images above cache level"
    )
    parser.add_argument(
        "--run_id", type=str, required=False, help="Run ID - identifies the run"
    )

    args = parser.parse_args()
    if not args.run_id:
        time_millis = int(time() * 1000)
        args.run_id = f"solve_{time_millis}"
        print(f"Generated run ID: {args.run_id}")

    main(**vars(args))
