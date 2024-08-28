from concurrent.futures import ThreadPoolExecutor, as_completed as futures_as_completed

import docker

from swebench.harness.test_spec import get_test_specs_from_dataset


def _pull_images(
    docker_client: docker.APIClient, image_type: str, image_names: set, max_workers=4
) -> list:
    """
    Pull images for the given dataset. Report the images that are not available.
    """

    def tag_image(image_name):
        if ":" not in image_name:
            print(
                f"WARNING: Image name {image_name} does not have a tag. Tagging :latest"
            )
            return f"{image_name}:latest"

        return image_name

    image_names = [tag_image(x) for x in image_names]

    unavailable_images = []
    for image_name in image_names:
        if not docker_client.images.list(name=image_name):
            unavailable_images.append(image_name)

    if not unavailable_images:
        print(f"All {image_type} images are already present locally.")
        return []

    not_found_images = []
    print(f"Pulling {len(unavailable_images)} images that are not present locally")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_image_name = {}
        for image_name in unavailable_images:
            full_image_name = f"ghcr.io/getappmap/{image_name}"
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
            except docker.errors.APIError as e:
                print(f"Error pulling image: {full_image_name}. Error: {e}")
                not_found_images.append(full_image_name)

    return not_found_images


def pull_base_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull base images for the given dataset.
    """
    test_specs = get_test_specs_from_dataset(dataset)
    base_image_names = {x.base_image_key for x in test_specs}
    _pull_images(docker_client, "base", base_image_names, max_workers)


def pull_env_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull environment images for the given dataset.
    """
    pull_base_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    env_image_names = {x.env_image_key for x in test_specs}
    _pull_images(docker_client, "env", env_image_names, max_workers)


def pull_instance_images(docker_client: docker.APIClient, dataset: list, max_workers=4):
    """
    Pull instance images for the given dataset.
    """
    pull_env_images(docker_client, dataset, max_workers)

    test_specs = get_test_specs_from_dataset(dataset)
    instance_image_names = {x.instance_image_key for x in test_specs}
    _pull_images(docker_client, "instance", instance_image_names, max_workers)
