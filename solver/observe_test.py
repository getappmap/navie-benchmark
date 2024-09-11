from argparse import ArgumentParser
from pathlib import Path
import re
import sys
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.appmap import AppMap
from solver.workflow.observe_test import ObserveTest
from solver.harness.image_store import ImageStore
from solver.solve import DATASET_NAME
from solver.cli import (
    build_logger,
    load_dataset,
)
from solver.workflow.patch import Patch


def main(patch: str):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    # Find instance id in the patch path, it will look like "<org>_<repo>-<instance-id>"
    # org and repo are strings, instance-id is a number.
    instance_id_regexp = r"^(\w+_\w+)-(\d+)$"
    instance_id = next(
        (part for part in patch.split("/") if re.match(instance_id_regexp, part)), None
    )
    if not instance_id:
        print(f"Instance id not found in patch path {patch}")
        sys.exit(1)

    print(f"Running test patch for instance: {instance_id}")

    docker_client = docker.from_env()

    work_dir = Path(__file__).parent.parent / "solve" / "observe-test" / instance_id
    work_dir.mkdir(parents=True, exist_ok=True)

    logger_fn = build_logger(work_dir, instance_id)
    dataset = load_dataset(DATASET_NAME, [instance_id])
    instance = dataset[0]

    test_spec = make_test_spec(instance)

    image_store = ImageStore(docker_client)
    image_store.ensure([test_spec])

    test_patch_path = Path(patch)
    if not test_patch_path.exists():
        print(f"Patch file {patch} not found.")
        sys.exit(1)

    test_patch_p = Patch.load_file(test_patch_path)

    observe_test = ObserveTest(logger_fn, work_dir, test_spec)

    observe_test_result = observe_test.run(docker_client, test_patch_p)
    if not observe_test_result or not observe_test_result.appmap_dir:
        raise Exception("No AppMap data found")

    appmap_dir = observe_test_result.appmap_dir
    print(f"AppMap data stored in {appmap_dir}")
    # Recursively find *.appmap.json in the appmap_dir
    for appmap_file in appmap_dir.rglob("*.appmap.json"):
        with appmap_file.open() as f:
            appmap_data = f.read()
            appmap = AppMap(appmap_data)
            print(appmap.list_locations())


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--patch", type=str, help="File containing the test patch", required=True
    )

    args = parser.parse_args()

    main(**vars(args))
