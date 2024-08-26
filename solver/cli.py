from argparse import ArgumentParser
from pathlib import Path
from time import time

import docker

from solver.harness.pull_images import pull_instance_images
from solver.workflow.workflow import Workflow, WorkflowLimits
from swebench.harness.constants import KEY_INSTANCE_ID, SWEbenchInstance
from swebench.harness.docker_build import (
    build_base_images,
    build_env_images,
    build_instance_images,
    setup_logger,
)
from swebench.harness.test_spec import TestSpec, make_test_spec
from swebench.harness.utils import load_swebench_dataset


def configure_limits(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--limit",
        type=str,
        help="Set a configurable limit as key=value",
        nargs="+",
    )


def apply_limits(args) -> None:
    if args.limit:
        limits = args.limit
        args.limits = {}
        del args.limit
        for limit in limits:
            key, value_str = limit.split("=")
            value_int = int(value_str)
            args.limits[key] = value_int


def build_limits(limits: dict) -> WorkflowLimits:
    limits = WorkflowLimits.from_dict(limits)
    print(f"Using limits: {limits}")
    return limits


def configure_run_id(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--reuse_work_dir",
        action="store_true",
        help="Reuse the work directory if it exists",
        default=False,
    )


def apply_run_id(args) -> None:
    reuse_work_dir = args.reuse_work_dir
    del args.reuse_work_dir

    if reuse_work_dir:
        args.run_id = f"solve_{args.instance_id}"
    else:
        time_millis = int(time() * 1000)
        args.run_id = f"solve_{args.instance_id}_{time_millis}"
        print(f"Generated run ID: {args.run_id}")


def load_dataset(dataset_name: str, instance_ids: list) -> list:
    test_dataset = load_swebench_dataset(dataset_name, "test")
    dev_dataset = load_swebench_dataset(dataset_name, "dev")

    dataset = []
    not_found_instance_ids = []
    for instance_id in instance_ids:
        instance = [
            instance
            for instance in test_dataset + dev_dataset
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


def build_work_dir(run_id) -> Path:
    work_dir = Path(__file__).parent.parent / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def build_logger(work_dir: str, instance_id: str) -> callable:
    log_dir = work_dir / "logs" / "plan" / instance_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run_instance.log"
    logger = setup_logger(instance_id, log_file)

    def logger_fn(facility, msg):
        message = f"[{facility}] ({instance_id}) {msg}"
        print(message)
        logger.info(message)

    return logger_fn


def build_images(
    docker_client: docker.APIClient, dataset: list, force_rebuild=False, max_workers=4
):
    build_env_images(docker_client, dataset, force_rebuild, max_workers)
    build_instance_images(docker_client, dataset, force_rebuild, max_workers)


def build_workflow(
    log: callable,
    navie_work_dir: Path,
    docker_client: docker.APIClient,
    instance: SWEbenchInstance,
    limits: WorkflowLimits,
):
    repo = instance["repo"]
    version = instance["version"]
    problem_statement = instance["problem_statement"]
    test_spec = make_test_spec(instance)

    return Workflow(
        log,
        navie_work_dir,
        docker_client,
        repo,
        version,
        test_spec,
        problem_statement,
        limits,
    )


def pull_or_build_instance_images(
    docker_client: docker.APIClient, dataset: list, force_rebuild=False, max_workers=4
):
    pull_instance_images(docker_client, dataset, max_workers)

    build_base_images(docker_client, dataset, force_rebuild)
    build_env_images(docker_client, dataset, force_rebuild)
    build_instance_images(docker_client, dataset, force_rebuild)
