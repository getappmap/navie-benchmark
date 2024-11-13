from argparse import ArgumentParser
from os import environ
from pathlib import Path
from subprocess import run
import sys
from typing import Optional
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed as futures_as_completed,
)

import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec
from swebench.harness.constants import SWEbenchInstance

from solver.load_instance_set import load_instance_set
from solver.workflow.workflow_limits import WorkflowLimits
from solver.harness.image_store import ImageStore
from solver.predictions_file import PredictionsFile
from solver.cli import (
    configure_clean_option,
    configure_limits,
    configure_runner_index,
    load_dataset,
    parse_limits,
    select_instances_for_runner,
)

DATASET_NAME = "princeton-nlp/SWE-bench_Lite"
DATASET_SPLIT = "test"


def main(
    instance_set: str,
    instance_ids: list,
    clean_work_dir: bool,
    clean_navie: bool,
    limit: list,
    num_runners: Optional[int] = None,
    runner_index: Optional[int] = None,
    test_patch_dir: Optional[str] = None,
    observe_tests: bool = False,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """

    limits_obj = WorkflowLimits.from_dict(parse_limits(limit))

    if not instance_ids:
        instance_ids = []

    if instance_set:
        instance_ids.extend(load_instance_set(instance_set))

    dataset = load_dataset(DATASET_NAME, instance_ids)
    dataset = select_instances_for_runner(dataset, num_runners, runner_index)

    if not dataset:
        print("[solve] No instances to run.")
        return

    print(f"[solve] Running {len(dataset)} unevaluated instances...")

    docker_client = docker.from_env()

    test_specs = [make_test_spec(instance) for instance in dataset]
    image_store = ImageStore(
        docker_client,
    )
    image_store.set_image_types(["base", "env"])
    image_store.ensure(test_specs)

    def log_fn(context, msg):
        print(f"[{context}] {msg}")
        sys.stdout.flush()

    predictions_manager = PredictionsFile(
        log_fn,
        instance_set,
        num_runners,
        runner_index,
    )

    solver_path = Path(__file__).parent / "solve_instance.py"
    log_fn(
        "solve",
        f"Solving with {limits_obj.concurrency_limit} concurrent worker processes",
    )

    def run_instance(index: int, instance: SWEbenchInstance):
        instance_id = instance["instance_id"]
        temp_prediction_path = f"{predictions_manager.predictions_path}.{index}"
        solve_args = [
            "python",
            str(solver_path),
            "--instance_id",
            instance_id,
            "--predictions",
            temp_prediction_path,
        ]
        if observe_tests:
            solve_args.append("--observe_tests")
        if clean_work_dir:
            solve_args.append("--clean_work_dir")
        if clean_navie:
            solve_args.append("--clean_navie")
        if limit:
            solve_args.append("--limit")
            solve_args.extend(limit)
        if test_patch_dir:
            solve_args.append("--test_patch_dir")
            solve_args.append(test_patch_dir)

        print(f"[solve] ({instance_id}) {' '.join(solve_args)}")

        # Run this as a separate process so that it can change the working directory.
        solve_result = run(solve_args)

        if solve_result.returncode != 0:
            print(
                f"[solve] ({instance_id}) Failed with exit code {solve_result.returncode}"
            )

        # Concatenate temp_predictions to predictions
        with open(temp_prediction_path, "r") as temp_predictions_file:
            predictions_manager.write_predictions(temp_predictions_file.read())

    with ThreadPoolExecutor(max_workers=limits_obj.concurrency_limit) as executor:

        def instances_with_index():
            for index, instance in enumerate(dataset):
                yield index, instance

        futures = [
            executor.submit(run_instance, index, instance)
            for index, instance in instances_with_index()
        ]
        for future in futures_as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[solve] Error: {e}")

    print("[solve] Writing predictions to predictions.jsonl")
    predictions_manager.collect_predictions(Path("predictions.jsonl"))

    print("[solve] Done!")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "--instance_set",
        type=str,
        help="Instance set to run",
    )
    parser.add_argument(
        "--test_patch_dir",
        type=str,
        help="Directory containing existing test patches. Existing test patches will not be re-solved, and will be used to seed the code solver.",
        default="data/test_patches",
    )
    parser.add_argument(
        "--observe_tests",
        action="store_true",
        help="Observe synthetic tests to collect AppMap data",
    )

    configure_runner_index(parser)
    configure_clean_option(parser)
    configure_limits(parser)

    args = parser.parse_args()

    appmap_command = environ.get("APPMAP_COMMAND")
    if appmap_command:
        print(f"[solve] Running with appmap command: {appmap_command}")

    if environ.get("OPENAI_API_KEY"):
        print("[solve] Running with OpenAI API key")
    elif environ.get("ANTHROPIC_API_KEY"):
        print("[solve] Running with Anthropic API key")
    else:
        print("[solve] WARNING: OpenAI API key not found in environment")

    main(**vars(args))
