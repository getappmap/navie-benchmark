from argparse import ArgumentParser
from os import chdir
from pathlib import Path
import sys

import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.harness.image_store import ImageStore
from solver.solve import DATASET_NAME
from solver.cli import (
    apply_limits,
    apply_clean_option,
    build_limits,
    build_logger,
    build_work_dir,
    build_workflow,
    configure_limits,
    configure_clean_option,
    load_dataset,
)


def main(
    instance_id: str,
    run_id: str,
    limits: dict,
):
    """
    Generate a test that reproduces the problem_statement in a given instance.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(run_id)
    logger_fn = build_logger(work_dir, instance_id)
    limits_obj = build_limits(limits)
    dataset = load_dataset(DATASET_NAME, [instance_id])

    instance = dataset[0]
    navie_work_dir = work_dir / "navie"
    source_dir = work_dir / "source"

    navie_work_dir.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        raise Exception(
            f"Source directory {source_dir} does not exist. It should already be checked out to run this script. Try running solve.py first, then using this script for re-runs."
        )

    test_spec = make_test_spec(instance)
    image_store = ImageStore(docker_client)
    image_store.ensure([test_spec])

    print(f"[solve_test]Changing directory to {source_dir}")
    chdir(source_dir)

    workflow = build_workflow(
        logger_fn, navie_work_dir, docker_client, instance, limits_obj
    )

    test_patch = workflow.generate_and_validate_test()

    if test_patch is None:
        print("[solve_test] No test patch generated.")
        return

    print(f"[solve_test]Generated test patch:\n{test_patch}")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    configure_clean_option(parser)
    configure_limits(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_clean_option(args)

    main(**vars(args))
