from argparse import ArgumentParser

import docker

from solver.cli import (
    apply_limits,
    apply_run_id,
    build_limits,
    build_work_dir,
    build_workflow,
    configure_limits,
    configure_run_id,
    load_dataset,
    pull_or_build_instance_images,
)
from solver.workflow.workflow import Workflow, WorkflowLimits
from swebench.harness.constants import KEY_INSTANCE_ID
from swebench.harness.docker_build import setup_logger
from swebench.harness.test_spec import make_test_spec


def main(
    dataset_name: str,
    instance_id: list,
    run_id: str,
    limits: dict,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(run_id)
    logger = setup_logger(work_dir, instance_id)
    limits = build_limits(limits)
    dataset = load_dataset(dataset_name, [instance_id])

    pull_or_build_instance_images(docker_client, dataset)

    instance = dataset[0]
    navie_work_dir = work_dir / "navie"

    workflow = build_workflow(logger, navie_work_dir, docker_client, instance, limits)


if __name__ == "__main__":
    limit_names = WorkflowLimits.limit_names()

    parser = ArgumentParser()
    parser.add_argument(
        "--dataset_name",
        type=str,
        help="Name of dataset or path to JSON file.",
        required=True,
    )
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    configure_run_id(parser)
    configure_limits(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_run_id(args)

    main(**vars(args))
