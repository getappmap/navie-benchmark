from argparse import ArgumentParser
from pathlib import Path
import sys

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.cli import (
    apply_limits,
    apply_run_id,
    build_limits,
    build_logger,
    build_work_dir,
    build_workflow,
    configure_limits,
    configure_run_id,
    load_dataset,
    pull_or_build_instance_images,
)
from solver.workflow.workflow import WorkflowLimits
from swebench.harness.docker_build import setup_logger


def main(
    dataset_name: str,
    instance_id: list,
    run_id: str,
    limits: dict,
):
    """
    Generate a test that reproduces the problem_statement in a given instance.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(run_id)
    logger_fn = build_logger(work_dir, instance_id)
    limits = build_limits(limits)
    dataset = load_dataset(dataset_name, [instance_id])

    pull_or_build_instance_images(docker_client, dataset)

    instance = dataset[0]
    navie_work_dir = work_dir / "navie"

    workflow = build_workflow(
        logger_fn, navie_work_dir, docker_client, instance, limits
    )

    plan = workflow.generate_plan()
    test_patch = workflow.generate_and_validate_test(plan)

    if test_patch is None:
        print("No test patch generated.")
        return

    print(f"Generated test patch:\n{test_patch}")


if __name__ == "__main__":
    limit_names = WorkflowLimits.limit_names()

    parser = ArgumentParser()
    parser.add_argument(
        "--dataset_name",
        default="princeton-nlp/SWE-bench_Lite",
        type=str,
        help="Name of dataset or path to JSON file.",
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
