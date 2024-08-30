from argparse import ArgumentParser
from os import chdir
from pathlib import Path
import sys
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))


from solver.solve import DATASET_NAME
from solver.cli import (
    apply_limits,
    apply_clean_option,
    build_limits,
    build_logger,
    build_work_dir,
    build_workflow,
    configure_clean_option,
    configure_limits,
    load_dataset,
    pull_or_build_instance_images,
)
from solver.checkout_code import checkout_code
from solver.workflow import WorkflowLimits

from swebench.harness.docker_build import (
    build_container,
    setup_logger,
)
from swebench.harness.docker_utils import (
    cleanup_container,
)
from swebench.harness.test_spec import make_test_spec


def main(
    instance_id: str,
    limits: dict,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(instance_id)
    docker_log_file = work_dir / "docker.log"
    docker_logger = setup_logger(instance_id, docker_log_file)
    logger_fn = build_logger(work_dir, instance_id)
    limits_obj = build_limits(limits)
    dataset = load_dataset(DATASET_NAME, [instance_id])
    instance = dataset[0]

    pull_or_build_instance_images(docker_client, dataset)

    instance_id = instance["instance_id"]

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
            test_spec, docker_client, instance_id, docker_logger, False
        )
        container.start()
        logger_fn("solve", f"Container started: {container.id}")

        # If source_dir doesn't exist, create it and clone the repo
        if not source_dir.exists():
            checkout_code(logger_fn, container, source_dir, tmp_dir)

        # os chdir to source_dir
        pwd = Path.cwd()
        logger_fn("solve", f"Changing directory to {source_dir}")
        chdir(source_dir)
        try:
            workflow = build_workflow(
                logger_fn,
                navie_work_dir,
                docker_client,
                instance,
                limits_obj,
            )
            workflow.run()
        finally:
            chdir(pwd)

    except Exception as e:
        print(f"[solve_instance] Error solving {instance_id}: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Remove instance container + image, close logger
        if container:
            print(f"[solve_instance] Cleaning up container {container.id}")
            cleanup_container(docker_client, container, docker_logger)

    return


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    configure_limits(parser)
    configure_clean_option(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_clean_option(args)

    main(**vars(args))
