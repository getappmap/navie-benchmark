from argparse import ArgumentParser
from pathlib import Path
import sys
from typing import List, Optional
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.workflow.observe_test import ObserveTest
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


def main(
    instance_id: str,
    test_patch: str,
    code_patch: Optional[str],
    observe: Optional[bool],
):
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
        raise ValueError(f"Patch file {test_patch} not found.")

    test_patch_p = Patch.load_file(test_patch_path)

    def observe_test():
        run_test = ObserveTest(logger_fn, navie_work_dir, test_spec)
        if code_patch:
            raise ValueError("Cannot observe with code patch")

        return run_test.run(docker_client, test_patch_p)

    def run_test():
        run_test = RunTest(logger_fn, navie_work_dir, test_spec)

        if code_patch:
            code_patch_file = Path(code_patch)
            if not code_patch_file.exists():
                raise ValueError(f"Patch file {code_patch} not found.")

            code_patch_p = Patch.load_file(code_patch_file)
            run_test.code_patches = [code_patch_p]

        return run_test.run(docker_client, test_patch_p)

    if observe:
        runner = observe_test
    else:
        runner = run_test

    result = runner()
    print(result)


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
    parser.add_argument(
        "--observe",
        action="store_true",
        help="Observe the test execution",
        required=False,
    )

    args = parser.parse_args()

    main(**vars(args))
