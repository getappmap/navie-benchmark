from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed as futures_as_completed,
)
from typing import Callable, Dict, Tuple

import docker

from swebench.harness.constants import SWEbenchInstance
from swebench.harness.test_spec import TestSpec, get_test_specs_from_dataset


def tag_image(image_name: str) -> str:
    if ":" not in image_name:
        print(f"WARNING: Image name {image_name} does not have a tag. Tagging :latest")
        return f"{image_name}:latest"

    return image_name


def _pull_images(
    docker_client: docker.DockerClient,
    image_type: str,
    image_names: list[str],
    max_workers=4,
) -> list:
    """
    Pull images for the given dataset. Report the images that are not available.
    """

    image_names = [tag_image(x) for x in image_names]

    unavailable_images = []
    for image_name in image_names:
        if not docker_client.images.list(name=image_name):
            unavailable_images.append(image_name)

    if not unavailable_images:
        print(f"All {image_type} images are already present locally.")
        return []

    not_found_images = []
    print(
        f"Pulling images that are not present locally: {', '.join(unavailable_images)}"
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_image_name: Dict[Future, Tuple[str, str]] = {}
        for image_name in unavailable_images:
            full_image_name = f"ghcr.io/getappmap/{image_name}"
            future = executor.submit(docker_client.images.pull, full_image_name)
            future_to_image_name[future] = (image_name, full_image_name)

        for future in futures_as_completed(future_to_image_name):
            (image_name, full_image_name) = future_to_image_name[future]
            try:
                future.result()
            except Exception as e:
                print(f"Error pulling image: {full_image_name}. Error: {e}")
                not_found_images.append(full_image_name)
                full_image_name = None

            if full_image_name:
                # Tag each image by removing the prefix ghcr.io/getappmap/
                docker_client.images.get(full_image_name).tag(image_name)

    return not_found_images


def _not_found_dataset(
    not_found_images: list,
    dataset: list[SWEbenchInstance],
    test_specs: list[TestSpec],
    image_key_function: Callable[[TestSpec], str],
):
    # Prune the prefix ghcr.io/getappmap/ from the image names
    image_base_names = [x.split("ghcr.io/getappmap/")[1] for x in not_found_images]
    not_found_test_specs = [
        x for x in test_specs if image_key_function(x) in image_base_names
    ]
    # Return a dataset of not-found images by looking up the test specs in the full dataset list.
    # For each test spec, find the corresponding instance in the dataset.
    instances_by_instance_id = {x["instance_id"]: x for x in dataset}
    not_found_dataset = [
        instances_by_instance_id[x.instance_id] for x in not_found_test_specs
    ]

    if len(not_found_images) != len(not_found_dataset):
        print(
            f"ERROR: Inconsistent number of not found images: {len(not_found_images)} != {len(not_found_dataset)}!"
        )

    return not_found_dataset


def pull_base_images(
    docker_client: docker.DockerClient, dataset: list[SWEbenchInstance], max_workers=4
):
    """
    Pull base images for the given dataset.
    """
    test_specs = get_test_specs_from_dataset(dataset)
    base_image_names = {x.base_image_key for x in test_specs}
    print(f"Base image names: {', '.join(base_image_names)}")
    not_found_images = _pull_images(
        docker_client, "base", list(base_image_names), max_workers
    )
    return _not_found_dataset(
        not_found_images, dataset, test_specs, lambda x: x.base_image_key
    )


def pull_env_images(docker_client: docker.DockerClient, dataset: list, max_workers=4):
    """
    Pull environment images for the given dataset.
    """
    pull_base_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    env_image_names = {x.env_image_key for x in test_specs}
    print(f"Env image names: {", ".join(env_image_names)}")
    not_found_images = _pull_images(
        docker_client, "env", list(env_image_names), max_workers
    )
    return _not_found_dataset(
        not_found_images, dataset, test_specs, lambda x: x.env_image_key
    )


def pull_instance_images(
    docker_client: docker.DockerClient, dataset: list, max_workers=4
):
    """
    Pull instance images for the given dataset.
    """
    pull_env_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    instance_image_names = {x.instance_image_key for x in test_specs}
    print(f"Instance image names: {', '.join(instance_image_names)}")
    not_found_images = _pull_images(
        docker_client, "instance", list(instance_image_names), max_workers
    )
    return _not_found_dataset(
        not_found_images, dataset, test_specs, lambda x: x.instance_image_key
    )
