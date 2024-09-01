from argparse import ArgumentParser
from pathlib import Path
import shutil
from typing import Callable, Optional

import docker

from swebench.harness.constants import (
    KEY_INSTANCE_ID,
    SWEbenchInstance,
)
from swebench.harness.docker_build import (
    build_env_images,
    build_instance_images,
    setup_logger,
)
from swebench.harness.test_spec import make_test_spec
from swebench.harness.utils import load_swebench_dataset

from solver.harness.pull_images import pull_instance_images
from solver.workflow.code_environment import DetectEnvironment
from solver.workflow.workflow import Workflow, WorkflowLimits


def configure_limits(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--limit",
        type=str,
        help="Set a configurable limit as key=value",
        nargs="+",
    )


def apply_limits(args) -> None:
    args.limits = {}
    if args.limit:
        limits = args.limit
        for limit in limits:
            key, value_str = limit.split("=")
            value_int = int(value_str)
            args.limits[key] = value_int

    if hasattr(args, "limit"):
        del args.limit


def build_limits(limits: dict) -> WorkflowLimits:
    limits_obj = WorkflowLimits.from_dict(limits)
    print(f"Using limits: {limits_obj}")
    return limits_obj


def configure_clean_option(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--clean_work_dir",
        action="store_true",
        help="Remove the work directory, if it exists, before running",
        default=False,
    )


def apply_clean_option(args) -> None:
    work_dir = build_work_dir(args.instance_id)

    clean_work_dir = args.clean_work_dir
    del args.clean_work_dir

    if clean_work_dir and work_dir.exists():
        print(f"Deleting work directory {work_dir}")
        shutil.rmtree(work_dir)


def load_dataset(dataset_name: str, instance_ids: list) -> list:
    test_dataset = load_swebench_dataset(dataset_name, "test")

    dataset = []
    not_found_instance_ids = []
    for instance_id in instance_ids:
        instance = [
            instance
            for instance in test_dataset
            if instance[KEY_INSTANCE_ID] == instance_id
        ]
        if not instance:
            not_found_instance_ids.append(instance_id)
        else:
            dataset.append(instance[0])

    if not_found_instance_ids:
        instance_id_str = ", ".join(not_found_instance_ids)
        raise Exception(f"Instance ids not found in dataset: {instance_id_str}")

    return dataset


def build_work_dir(instance_id) -> Path:
    work_dir = Path(__file__).parent.parent / "solve" / instance_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def build_logger(work_dir: Path, instance_id: str) -> Callable[[str, str], None]:
    log_dir = work_dir / "logs" / "plan" / instance_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = work_dir / "logs" / "solve.log"
    logger = setup_logger(instance_id, log_file)

    def logger_fn(facility, msg):
        message = f"[{facility}] ({instance_id}) {msg}"
        print(message)
        logger.info(message)

    return logger_fn


def build_images(
    docker_client: docker.DockerClient,
    dataset: list,
    force_rebuild=False,
    max_workers=4,
):
    build_env_images(docker_client, dataset, force_rebuild, max_workers)
    build_instance_images(docker_client, dataset, force_rebuild, max_workers)


def build_workflow(
    log: Callable[[str, str], None],
    navie_work_dir: Path,
    docker_client: docker.DockerClient,
    instance: SWEbenchInstance,
    limits: WorkflowLimits,
):
    repo = instance["repo"]
    version = instance["version"]
    problem_statement = instance["problem_statement"]
    test_spec = make_test_spec(instance)

    environment = DetectEnvironment(
        log, navie_work_dir, repo, version, test_spec
    ).detect(docker_client)

    return Workflow(
        log,
        navie_work_dir,
        environment,
        docker_client,
        repo,
        version,
        test_spec,
        problem_statement,
        limits,
    )


def pull_or_build_instance_images(
    docker_client: docker.DockerClient,
    dataset: list,
    max_workers=4,
):
    # Base and env images will be pulled, but will not be built.
    # That's beacuse there may be multiple processes running at the same time
    # that want to do this, and we don't want to build the same image multiple times.
    # Base and env images should be pre-allocated before running any command that needs this function.

    pull_instance_images(docker_client, dataset, max_workers)

    build_instance_images(
        docker_client, dataset, force_rebuild=False, max_workers=max_workers
    )


def configure_runner_index(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--num_runners",
        type=int,
        help="Number of runners",
    )
    parser.add_argument(
        "--runner_index",
        type=int,
        help="Select instances based on the runner index (instance index % num_runners == runner_index)",
    )


def select_instances_for_runner(
    dataset: list, num_runners: Optional[int], runner_index: Optional[int]
) -> list:
    if num_runners is None or runner_index is None:
        return dataset

    return [
        instance
        for i, instance in enumerate(dataset)
        if i % num_runners == runner_index
    ]
