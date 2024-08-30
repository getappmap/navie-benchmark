from argparse import ArgumentParser
from pathlib import Path
import sys
from typing import Callable, Dict, List, Optional

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.docker_build import (
    build_base_images,
    build_env_images,
    build_instance_images,
    DockerBuildResult,
)

from solver.harness.pull_images import pull_instance_images, tag_image
from solver.cli import load_dataset
from solver.solve import DATASET_NAME


def build_and_push_images(
    docker_client: docker.DockerClient,
    build_images_func: Callable[
        [docker.DockerClient, Optional[int]],
        DockerBuildResult,
    ],
    max_workers: int,
):
    build_result = build_images_func(docker_client, max_workers)

    if build_result.failed:
        print(f"WARNING: Failed to build some images: {", ".join(build_result.failed)}")

    print(f"Built images: {", ".join(build_result.successful)}")

    remote_image_keys = [
        f"ghcr.io/getappmap/{tag_image(image_name)}"
        for image_name in build_result.images
    ]
    # Tag each image, then push
    for image_name, remote_image_key in zip(build_result.images, remote_image_keys):
        if image_name in build_result.failed:
            print(f"Skipping {image_name} because it failed to build")
            continue
        else:
            print(f"Pushing {remote_image_key}")
            docker_client.images.get(image_name).tag(remote_image_key)
            try:
                docker_client.images.push(remote_image_key)
            except docker.errors.APIError as e: # type: ignore
                print(f"Error pushing image: {remote_image_key}. Error: {e}")


def main(instance_ids: list, instance_set: str, max_workers: int = 4):
    docker_client = docker.from_env()

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

    pull_instance_images(docker_client, dataset, max_workers=max_workers)

    def wrap_build_base_images(docker_client, max_workers):
        # max_workers is not used here
        return build_base_images(docker_client, dataset)

    build_and_push_images(docker_client, wrap_build_base_images, max_workers)

    def wrap_build_env_images(docker_client, max_workers):
        return build_env_images(docker_client, dataset, max_workers=max_workers)

    build_and_push_images(docker_client, wrap_build_env_images, max_workers)

    def wrap_build_instance_images(docker_client, max_workers):
        return build_instance_images(docker_client, dataset, max_workers)

    build_and_push_images(docker_client, wrap_build_instance_images, max_workers)


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

    args = parser.parse_args()

    main(**vars(args))
