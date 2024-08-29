from argparse import ArgumentParser
from pathlib import Path
import sys
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.solve import DATASET_NAME
from swebench.harness.test_spec import make_test_spec

from solver.cli import (
    build_logger,
    build_work_dir,
    load_dataset,
    pull_or_build_instance_images,
)
from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTest


def main(instance_id: list, patch_file: str):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(instance_id)
    logger_fn = build_logger(work_dir, instance_id)
    dataset = load_dataset(DATASET_NAME, [instance_id])
    instance = dataset[0]

    test_spec = make_test_spec(instance)
    navie_work_dir = work_dir / "navie"
    run_test_dir = navie_work_dir / "run_test"
    run_test_dir.mkdir(parents=True, exist_ok=True)

    patch_file = Path(patch_file)
    if not patch_file.exists():
        print(f"Patch file {patch_file} not found.")
        sys.exit(1)

    test_patch = Patch.load_file(patch_file)

    pull_or_build_instance_images(docker_client, dataset)

    run_test = RunTest(
        logger_fn, navie_work_dir, instance["repo"], instance["version"], test_spec
    )

    run_test_result = run_test.run(docker_client, test_patch)

    print(run_test_result)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    parser.add_argument(
        "--patch_file", type=str, help="File containing the test patch", required=True
    )

    args = parser.parse_args()

    main(**vars(args))
