from argparse import ArgumentParser
from os import chdir
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
    load_dataset,
)
from swebench.harness.constants import KEY_INSTANCE_ID
from solver.checkout_code import checkout_code
from solver.workflow import Workflow, WorkflowLimits

from swebench.harness.docker_build import (
    build_container,
    build_env_images,
    setup_logger,
)
from swebench.harness.docker_utils import (
    cleanup_container,
)
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
    docker_logger = setup_logger(work_dir, instance_id)
    logger_fn = build_logger(work_dir, instance_id)
    limits = build_limits(limits)
    dataset = load_dataset(dataset_name, [instance_id])
    instance = dataset[0]

    # build environment images
    build_env_images(docker_client, dataset)

    instance_id = instance["instance_id"]
    issue_text = instance["problem_statement"]

    test_spec = make_test_spec(instance)

    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    source_dir = work_dir / "source"
    navie_work_dir = work_dir / "navie"

    # plan the issue
    container = None
    try:
        # Build + start instance container (instance image should already be built)
        container = build_container(
            test_spec, docker_client, run_id, docker_logger, False
        )
        container.start()
        logger_fn("solve", f"Container started: {container.id}")

        # If source_dir doesn't exist, create it and clone the repo
        if not source_dir.exists():
            checkout_code(logger_fn, container, source_dir, tmp_dir)

        # Run the plan script
        logger_fn("solve", "Running plan script")

        # os chdir to source_dir
        pwd = Path.cwd()
        logger_fn("solve", f"Changing directory to {source_dir}")
        chdir(source_dir)
        try:
            workflow = Workflow(
                logger_fn,
                navie_work_dir,
                docker_client,
                instance["repo"],
                instance["version"],
                test_spec,
                issue_text,
                limits,
            )
            workflow.run()
        finally:
            chdir(pwd)

    except Exception as e:
        print(f"[plan] Error running plan for {instance_id}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Remove instance container + image, close logger
        if container:
            print(f"[plan] Cleaning up container {container.id}")
            cleanup_container(docker_client, container, docker_logger)

    return


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
    parser.add_argument(
        "--reuse_work_dir",
        action="store_true",
        help="Reuse the work directory if it exists",
        default=False,
    )
    parser.add_argument(
        "--limit",
        type=str,
        help=f"Set a configurable limit as key=value. Valid keys are: {limit_names}",
        nargs="+",
    )

    args = parser.parse_args()

    apply_limits(args)
    apply_run_id(args)

    main(**vars(args))
