from typing import Callable, Dict, Tuple
import docker
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed as futures_as_completed,
)

from tqdm import tqdm

from swebench.harness.constants import ENV_IMAGE_BUILD_DIR, INSTANCE_IMAGE_BUILD_DIR
from swebench.harness.docker_build import (
    build_base_images,
    build_image,
    get_env_configs_to_build,
)
from swebench.harness.test_spec import TestSpec

ImageKeyFunction = Callable[[TestSpec], str]

ImageBuildFunction = Callable[[TestSpec], None]

DEFAULT_MAX_WORKERS = 4

IMAGE_TYPES = [
    "base",
    "env",
    "instance",
]


class ImageStore:
    def __init__(
        self,
        docker_client: docker.DockerClient,
        build_if_not_found: bool = True,
        push_images: bool = False,
    ):
        self.docker_client = docker_client
        self.build_if_not_found = build_if_not_found
        self.push_images = push_images

        self.max_workers = DEFAULT_MAX_WORKERS
        self.image_types = IMAGE_TYPES

    def set_max_workers(self, max_workers: int):
        self.max_workers = max_workers

    def set_image_types(self, image_types: list[str]):
        self.image_types = image_types

    def ensure(self, dataset: list[TestSpec]):
        if "base" in self.image_types:
            self._ensure_images(
                "base",
                ImageStore.base_image_key_function(),
                self.build_base_image,
                dataset,
            )

        if "env" in self.image_types:
            self._ensure_images(
                "env",
                ImageStore.env_image_key_function(),
                self.build_env_image,
                dataset,
            )

        if "instance" in self.image_types:
            self._ensure_images(
                "instance",
                ImageStore.instance_image_key_function(),
                self.build_instance_image,
                dataset,
            )

    def _ensure_images(
        self,
        image_type: str,
        image_key_function: ImageKeyFunction,
        build_image_function: ImageBuildFunction,
        dataset: list[TestSpec],
    ):
        image_names = [image_key_function(x) for x in dataset]

        not_local_images = []
        for image_name in image_names:
            try:
                self.docker_client.images.get(image_name)
            except docker.errors.ImageNotFound:  # type: ignore
                not_local_images.append(image_name)

        build_images = self._pull_images(image_type, not_local_images)

        if build_images:
            if not self.build_if_not_found:
                raise Exception(
                    f"The following images could not be pulled, and building is disabled: {', '.join(build_images)}"
                )

            dataset_to_build = self.image_list_to_dataset(
                image_key_function, build_images, dataset
            )
            image_names = [image_key_function(x) for x in dataset_to_build]
            message = [f"Building"]
            if self.push_images:
                message.append("and pushing")
            message.append(
                f"{len(image_names)} {image_type} images: {', '.join(image_names)}"
            )
            print(" ".join(message))
            self.build_images(
                image_key_function, build_image_function, image_type, dataset_to_build
            )

    def build_images(
        self,
        image_key_function: ImageKeyFunction,
        build_image_function: ImageBuildFunction,
        image_type: str,
        dataset: list[TestSpec],
    ):
        image_names = {image_key_function(x) for x in dataset}
        print(f"Building {image_type} images: {', '.join(image_names)}")

        def build_and_push_image(test_spec: TestSpec):
            build_image_function(test_spec)
            if self.push_images:
                self.push_image(image_key_function(test_spec))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(build_and_push_image, x) for x in dataset]
            with tqdm(
                futures, desc=f"Building {image_type} images", unit="img"
            ) as pbar:
                for future in futures_as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        print(f"Error building image: {e}")
                    pbar.update(1)

    def push_image(self, image_name: str):
        print(f"Pushing image: {image_name}")

        remote_image_key = f"ghcr.io/getappmap/{image_name}"
        try:
            self.docker_client.images.push(remote_image_key)
        except docker.errors.APIError as e:  # type: ignore
            print(f"Error pushing image: {remote_image_key}. Error: {e}")

    def build_base_image(self, test_spec: TestSpec) -> None:
        image_name = test_spec.base_image_key
        print(f"Building base image ({image_name})")
        build_base_images(self.docker_client, [test_spec])

    def build_env_image(self, test_spec: TestSpec) -> None:
        image_name = test_spec.env_image_key
        print(f"Building env image ({image_name})")

        configs_to_build = get_env_configs_to_build(self.docker_client, [test_spec])
        assert image_name in configs_to_build
        config = configs_to_build[image_name]
        assert config

        build_image(
            image_name,
            {"setup_env.sh": config["setup_script"]},
            config["dockerfile"],
            config["platform"],
            self.docker_client,
            ENV_IMAGE_BUILD_DIR / image_name.replace(":", "__"),
        )

    def build_instance_image(self, test_spec: TestSpec) -> None:
        image_name = test_spec.instance_image_key
        print(f"Building instance image ({image_name})")

        build_image(
            image_name=image_name,
            setup_scripts={
                "setup_repo.sh": test_spec.install_repo_script,
            },
            dockerfile=test_spec.instance_dockerfile,
            platform=test_spec.platform,
            client=self.docker_client,
            build_dir=INSTANCE_IMAGE_BUILD_DIR / image_name.replace(":", "__"),
            nocache=False,
        )

    def _pull_images(
        self, image_type: str, image_names: list[str], max_workers=4
    ) -> list[str]:
        """
        Pull images for the given dataset. Report the images that are not available.

        Pulled images are tagged with the image name.
        """

        image_names = [ImageStore.ensure_image_tag(x) for x in image_names]
        not_found_images = []

        unavailable_images = [
            name
            for name in image_names
            if not self.docker_client.images.list(name=name)
        ]
        if not unavailable_images:
            print(f"All {image_type} images are already present locally.")
            return []

        print(
            f"Pulling images that are not present locally: {', '.join(unavailable_images)}"
        )
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_image_name: Dict[Future, Tuple[str, str]] = {}
            futures = [
                executor.submit(
                    self.docker_client.images.pull, f"ghcr.io/getappmap/{name}"
                )
                for name in unavailable_images
            ]

            with tqdm(total=len(futures), desc="Pulling images", unit="img") as pbar:
                for future, name in zip(futures, unavailable_images):
                    future_to_image_name[future] = (name, f"ghcr.io/getappmap/{name}")

                for future in futures_as_completed(futures):
                    (image_name, full_image_name) = future_to_image_name[future]
                    pulled = False
                    try:
                        future.result()
                        pulled = True
                    except Exception as e:
                        if not "manifest unknown" in str(e):
                            print(f"Error pulling image: {full_image_name}. Error: {e}")

                    pbar.update(1)
                    if pulled:
                        self.docker_client.images.get(full_image_name).tag(image_name)
                    else:
                        not_found_images.append(image_name)

        not_found_images.sort()
        return not_found_images

    @staticmethod
    def image_list_to_dataset(
        image_key_function: Callable, image_names: list[str], dataset: list[TestSpec]
    ) -> list[TestSpec]:
        """
        Convert a list of image names to a list of TestSpecs.
        """
        image_name_set = set(image_names)
        return [x for x in dataset if image_key_function(x) in image_name_set]

    @staticmethod
    def ensure_image_tag(image_name: str) -> str:
        """
        Enure that the image name has a tag. If not, tag it with :latest.
        """
        if ":" not in image_name:
            print(
                f"WARNING: Image name {image_name} does not have a tag. Tagging :latest"
            )
            return f"{image_name}:latest"
        return image_name

    @staticmethod
    def base_image_key_function() -> ImageKeyFunction:
        return lambda x: x.base_image_key

    @staticmethod
    def env_image_key_function() -> ImageKeyFunction:
        return lambda x: x.env_image_key

    @staticmethod
    def instance_image_key_function() -> ImageKeyFunction:
        return lambda x: x.instance_image_key
