from argparse import ArgumentParser
from pathlib import Path
import sys

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.docker_build import build_base_images, build_env_images

from solver.harness.pull_images import pull_base_images, pull_env_images, tag_image
from solver.cli import load_dataset
from solver.solve import DATASET_NAME


def build_and_push_images(
    docker_client: docker.APIClient,
    images_to_build_dataset: list,
    build_images_func: callable,
    max_workers: int,
):
    if images_to_build_dataset:
        (successful_images, failed_images) = build_images_func(
            docker_client, images_to_build_dataset, max_workers=max_workers
        )

        if failed_images:
            print(f"Failed to build: {failed_images}")
            sys.exit(1)

        built_image_names = successful_images
        print(f"Built images: {built_image_names}")
        remote_image_keys = [
            f"ghcr.io/getappmap/{tag_image(image_name)}"
            for image_name in built_image_names
        ]
        # Tag each image, then push
        for image_name, remote_image_key in zip(built_image_names, remote_image_keys):
            print(f"Tagging {image_name} as {remote_image_key}")
            docker_client.images.get(image_name).tag(remote_image_key)
            print(f"Pushing {remote_image_key}")
            docker_client.images.push(remote_image_key)


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

    # Build one image at a time
    base_images_to_build_dataset = pull_base_images(
        docker_client, dataset, max_workers=1
    )

    # max_workers is not used here
    def wrap_build_base_images(docker_client, dataset, max_workers):
        return build_base_images(docker_client, dataset)

    build_and_push_images(
        docker_client, base_images_to_build_dataset, wrap_build_base_images, max_workers
    )

    env_images_to_build_dataset = pull_env_images(
        docker_client, dataset, max_workers=max_workers
    )
    build_and_push_images(
        docker_client, env_images_to_build_dataset, build_env_images, max_workers
    )


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
