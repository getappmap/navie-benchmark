from argparse import ArgumentParser
from pathlib import Path
from time import time

from solver.workflow.workflow import WorkflowLimits
from swebench.harness.constants import KEY_INSTANCE_ID
from swebench.harness.docker_build import setup_logger
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
