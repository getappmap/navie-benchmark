from argparse import ArgumentParser
from pathlib import Path
import sys
import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.constants import KEY_INSTANCE_ID
from swebench.harness.docker_build import build_env_images, setup_logger
from swebench.harness.test_spec import make_test_spec
from swebench.harness.utils import load_swebench_dataset

from solver.workflow.patch import Patch
from solver.workflow.run_test import RunTest


def main(
    dataset_name: str,
    instance_id: list,
    run_id: str,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """
    work_dir = Path(__file__).parent.parent / "work" / run_id
    navie_work_dir = work_dir / "navie"
    navie_work_dir.mkdir(parents=True, exist_ok=True)

    test_patch_file = Path(navie_work_dir) / "test.patch"
    if not test_patch_file.exists():
        print(f"Test patch file {test_patch_file} not found.")
        sys.exit(1)

    docker_client = docker.from_env()

    test_dataset = load_swebench_dataset(dataset_name, "test")
    dev_dataset = load_swebench_dataset(dataset_name, "dev")

    dataset = [
        instance
        for instance in test_dataset + dev_dataset
        if instance[KEY_INSTANCE_ID] == instance_id
    ]
    if not dataset:
        print(f"Instance ID {instance_id} not found in dataset.")
        sys.exit(1)

    if len(dataset) > 1:
        print(f"Found multiple instances with ID {instance_id}.")
        sys.exit(1)

    # build environment images
    build_env_images(docker_client, dataset)

    instance = dataset[0]

    test_spec = make_test_spec(instance)

    log_dir = work_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "run_test.log"

    print(f"Logging to {log_file}")
    logger = setup_logger(instance_id, log_file)

    def logger_fn(facility, msg):
        message = f"[{facility}] ({instance_id}) {msg}"
        print(message)
        logger.info(message)

    run_test = RunTest(
        logger_fn, navie_work_dir, instance["repo"], instance["version"], test_spec
    )

    with test_patch_file.open("r") as f:
        test_patch = Patch(f.read())

    run_test_result = run_test.run(docker_client, test_patch)
    print(run_test_result)


if __name__ == "__main__":
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

    args = parser.parse_args()
    args.run_id = f"solve_{args.instance_id}"

    main(**vars(args))
