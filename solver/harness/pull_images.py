from asyncio import as_completed
from concurrent.futures import ThreadPoolExecutor, as_completed as futures_as_completed

import docker

from swebench.harness.test_spec import get_test_specs_from_dataset


def _pull_images(
    docker_client: docker.APIClient, image_names: set, max_workers=4
) -> list:
    """
    Pull images for the given dataset. Report the images that are not available.
    """

    unavailable_images = []
    for image_name in image_names:
        if not docker_client.images.list(name=image_name):
            unavailable_images.append(image_name)

    if not unavailable_images:
        print("All images are already present locally.")
        return []

    not_found_images = []
    print(f"Pulling {len(unavailable_images)} images that are not present locally")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_image_name = {}
        for image_name in unavailable_images:
            full_image_name = "/".join(["ghcr.io", "getappmap", image_name])
            future = executor.submit(docker_client.images.pull, full_image_name)
            future_to_image_name[future] = full_image_name

        for future in futures_as_completed(future_to_image_name):
            full_image_name = future_to_image_name[future]
            try:
                future.result()
            except docker.errors.ImageNotFound as e:
                print(
                    f"Image not found: {full_image_name}. It should be built in a subsequent step."
                )
                not_found_images.append(full_image_name)

    return not_found_images


def pull_base_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull base images for the given dataset.
    """
    test_specs = get_test_specs_from_dataset(dataset)
    base_image_names = {x.base_image_key for x in test_specs}
    _pull_images(docker_client, base_image_names, max_workers)


def pull_env_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull environment images for the given dataset.
    """
    pull_base_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    env_image_names = {x.env_image_key for x in test_specs}
    _pull_images(docker_client, env_image_names, max_workers)


def pull_instance_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull instance images for the given dataset.
    """
    pull_env_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    instance_image_names = {x.instance_image_key for x in test_specs}
    _pull_images(docker_client, instance_image_names, max_workers)
