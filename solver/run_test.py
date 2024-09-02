from argparse import ArgumentParser
from pathlib import Path
import sys
from typing import List
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.harness.image_store import ImageStore
from solver.solve import DATASET_NAME
from solver.cli import (
    build_logger,
    build_work_dir,
    load_dataset,
)
from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTest


def main(instance_id: str, test_patch: str, code_patch: str):
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

    image_store = ImageStore(docker_client)
    image_store.ensure([test_spec])

    test_patch_path = Path(test_patch)
    if not test_patch_path.exists():
        print(f"Patch file {test_patch} not found.")
        sys.exit(1)

    test_patch_p = Patch.load_file(test_patch_path)

    code_patches: List[Patch] = []
    if code_patch:
        code_patch_file = Path(code_patch)
        if not code_patch_file.exists():
            print(f"Patch file {code_patch} not found.")
            sys.exit(1)

        code_patch_p = Patch.load_file(code_patch_file)
        code_patches.append(code_patch_p)

    run_test = RunTest(
        logger_fn, navie_work_dir, instance["repo"], instance["version"], test_spec
    )
    if code_patches:
        run_test.code_patches = code_patches

    run_test_result = run_test.run(docker_client, test_patch_p)

    print(run_test_result)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    parser.add_argument(
        "--test_patch", type=str, help="File containing the test patch", required=True
    )
    parser.add_argument(
        "--code_patch", type=str, help="File containing the code patch", required=False
    )

    args = parser.parse_args()

    main(**vars(args))
