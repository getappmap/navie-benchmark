from argparse import ArgumentParser
from pathlib import Path
import shutil
import sys
from typing import Callable, Optional

import docker

from solver.workflow.solve_test import SolveTest
from solver.workflow.patch import Patch
from swebench.harness.constants import (
    KEY_INSTANCE_ID,
    SWEbenchInstance,
)
from swebench.harness.docker_build import (
    setup_logger,
)
from swebench.harness.test_spec import make_test_spec
from swebench.harness.utils import load_swebench_dataset

from solver.workflow.workflow_limits import WorkflowLimits
from solver.workflow.solve_code import SolveCode


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


def build_limits(instance_id: str, limits: dict) -> WorkflowLimits:
    limits_obj = WorkflowLimits.from_dict(limits)
    print(f"[solve] ({instance_id}) Using limits: {limits_obj}")
    return limits_obj


def configure_clean_option(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--clean_work_dir",
        action="store_true",
        help="Remove the work directory, if it exists, before running",
        default=False,
    )
    parser.add_argument(
        "--clean_navie",
        action="store_true",
        help="Remove the navie work directory, if it exists, before running",
        default=False,
    )


def apply_clean_option(args) -> None:
    work_dir = build_work_dir(args.instance_id)

    clean_work_dir = args.clean_work_dir
    del args.clean_work_dir

    clean_navie = args.clean_navie
    del args.clean_navie

    if clean_work_dir and work_dir.exists():
        print(f"Deleting work directory {work_dir}")
        shutil.rmtree(work_dir)

    navie_work_dir = work_dir / "navie"
    if clean_navie and navie_work_dir.exists():
        print(f"Deleting navie work directory {navie_work_dir}")
        shutil.rmtree(navie_work_dir)


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

    return sort_dataset(dataset)


def build_work_dir(instance_id) -> Path:
    work_dir = Path(__file__).parent.parent / "solve" / instance_id
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


LEVELS = ["debug", "info"]


def build_logger(work_dir: Path, instance_id: str) -> Callable[..., None]:
    log_file = work_dir / "logs" / "solve.log"
    logger = setup_logger(instance_id, log_file)

    def logger_fn(level_or_facility: str, facility_or_message: str, *args: str):
        if level_or_facility in LEVELS:
            level = level_or_facility
            facility = facility_or_message
            messages = args
        else:
            level = "debug"
            facility = level_or_facility
            messages = [facility_or_message] + list(args)

        message = f"[{facility}] ({instance_id}) " + " ".join(messages)
        if level == "info":
            print(message)
            sys.stdout.flush()
            logger.info(message)
        else:
            logger.info(message)

    return logger_fn


def build_solve_test(
    log: Callable[[str, str], None],
    navie_work_dir: Path,
    docker_client: docker.DockerClient,
    instance: SWEbenchInstance,
    limits: WorkflowLimits,
):
    problem_statement = instance["problem_statement"]
    test_spec = make_test_spec(instance)

    return SolveTest(
        log,
        navie_work_dir,
        docker_client,
        test_spec,
        problem_statement,
        limits,
    )


def build_solve_code(
    log: Callable[[str, str], None],
    navie_work_dir: Path,
    docker_client: docker.DockerClient,
    instance: SWEbenchInstance,
    limits: WorkflowLimits,
    observe_enabled: bool,
    edit_test_file: Optional[Path],
    test_patch: Optional[Patch],
    inverted_patch: Optional[Patch],
):
    problem_statement = instance["problem_statement"]
    test_spec = make_test_spec(instance)

    return SolveCode(
        log,
        navie_work_dir,
        docker_client,
        test_spec,
        problem_statement,
        limits,
        edit_test_file,
        test_patch,
        inverted_patch,
        observe_enabled=observe_enabled,
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
        help=r"Select instances based on the runner index (instance index %% num_runners == runner_index)",
    )


def sort_dataset(dataset: list[SWEbenchInstance]) -> list[SWEbenchInstance]:
    dataset_sorted = dataset.copy()
    dataset_sorted.sort(
        key=lambda instance: instance[KEY_INSTANCE_ID],
    )
    return dataset_sorted


def select_instances_for_runner(
    dataset: list[SWEbenchInstance],
    num_runners: Optional[int],
    runner_index: Optional[int],
) -> list[SWEbenchInstance]:
    if num_runners is None or runner_index is None:
        return dataset

    return [
        instance
        for i, instance in enumerate(sort_dataset(dataset))
        if i % num_runners == runner_index
    ]
