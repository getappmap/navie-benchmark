from argparse import ArgumentParser
from os import getenv
from pathlib import Path
import sys
from typing import Optional

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.load_instance_set import load_instance_set
from swebench.harness.test_spec import make_test_spec

from solver.harness.image_store import ImageStore

from solver.cli import configure_runner_index, load_dataset, select_instances_for_runner
from solver.solve import DATASET_NAME


def main(
    instance_ids: list,
    instance_set: str,
    max_workers: int = 4,
    no_push: bool = False,
    num_runners: Optional[int] = None,
    runner_index: Optional[int] = None,
):
    docker_timeout = int(getenv("DOCKER_TIMEOUT", 600))
    docker_client = docker.from_env(timeout=docker_timeout)

    if not instance_ids:
        instance_ids = []

    if instance_set:
        instance_ids.extend(load_instance_set(instance_set))

    dataset = load_dataset(DATASET_NAME, instance_ids)
    dataset = select_instances_for_runner(dataset, num_runners, runner_index)
    test_specs = [make_test_spec(instance) for instance in dataset]

    push = not no_push

    image_store = ImageStore(docker_client, build_if_not_found=True, push_images=push)
    image_store.max_workers = max_workers
    image_store.ensure(test_specs)


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
    parser.add_argument(
        "--max_workers",
        type=int,
        default=4,
        help="Maximum number of workers to use for building images",
    )
    parser.add_argument(
        "--no_push",
        action="store_true",
        help="Don't push images after building",
    )

    configure_runner_index(parser)

    args = parser.parse_args()

    main(**vars(args))
