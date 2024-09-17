from argparse import ArgumentParser
from json import dumps
import json
from os import chdir, getenv
from pathlib import Path
import sys
from typing import Callable, Optional, Union, cast
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.docker_build import (
    build_container,
    setup_logger,
)
from swebench.harness.docker_utils import (
    cleanup_container,
)
from swebench.harness.test_spec import make_test_spec
from swebench.harness.constants import SWEbenchInstance

from solver.workflow.convert_to_plain_types import convert_to_plain_types
from solver.workflow.generate_and_validate_test import TestPatchResult
from solver.workflow.patch import Patch
from solver.prediction import Prediction
from solver.workflow.solution_listener import (
    Solution,
    SolutionListener,
)
from solver.harness.image_store import ImageStore
from solver.predictions_file import PredictionsFile

from solver.solve import DATASET_NAME
from solver.cli import (
    apply_limits,
    apply_clean_option,
    build_limits,
    build_logger,
    build_work_dir,
    build_solve_test,
    build_solve_code,
    configure_clean_option,
    configure_limits,
    load_dataset,
)
from solver.checkout_code import checkout_code


def report_solution(
    log,
    navie_work_dir: Path,
    llm: str,
    predictions_file: str,
    instance: SWEbenchInstance,
    test_solver: bool,
    code_solver: bool,
    solution: Solution,
):
    def result_str(obj: Union[TestPatchResult, Solution]):
        result = []
        for k, v in obj.items():
            value = v
            if isinstance(v, Patch):
                value = True if v else False

            if value is None:
                value = ""
            result.append(f"  {k}: {value}")
        return "\n".join(result)

    def print_solution():
        log(
            "info",
            "solve-instance",
            f"Solution for {instance['instance_id']}:",
        )
        print(result_str(solution))

    def print_test_patch_result(test_patch_result: TestPatchResult):
        log(
            "info",
            "solve-instance",
            f"Test patch result for {instance['instance_id']}:",
        )
        print(result_str(test_patch_result))

    if code_solver:
        print_solution()
    solution_attrs = convert_to_plain_types(solution)
    with open(navie_work_dir / "solution.json", "w") as f:
        f.write(dumps(solution_attrs, indent=2))

    if solution["edit_test_file"]:
        test_patch_result = TestPatchResult(
            edit_test_file=solution["edit_test_file"],
            test_patch=solution["test_patch"],
            inverted_patch=solution["test_inverted_patch"],
        )
        if test_solver and not code_solver:
            print_test_patch_result(test_patch_result)
        test_patch_result_attrs = convert_to_plain_types(test_patch_result)
        with open(navie_work_dir / "test_patch.json", "w") as f:
            f.write(dumps(test_patch_result_attrs, indent=2))

    predictions = Prediction.build_predictions(instance, llm)
    predictions.add_prediction("model_patch", solution["code_patch"] or "")
    predictions.add_prediction("model_test_patch", solution["test_patch"])
    predictions.add_prediction("model_inverted_patch", solution["test_inverted_patch"])
    predictions.add_prediction("model_edit_test_file", solution["edit_test_file"])

    PredictionsFile.add_prediction(predictions_file, predictions.as_dict())


def report_error(
    log,
    navie_work_dir: Path,
    llm: str,
    predictions_file: str,
    instance: SWEbenchInstance,
    e: Exception,
):
    log("info", "solve-instance", f"Error: {e}")
    import traceback

    traceback.print_exc()

    navie_work_dir.mkdir(parents=True, exist_ok=True)
    with open(navie_work_dir / "error.txt", "w") as f:
        f.write(str(e))
        f.write("\n")
        traceback.print_exc(file=f)

    predictions = Prediction.build_predictions(instance, llm)
    predictions.add_prediction("model_error", str(e))

    PredictionsFile.add_prediction(predictions_file, predictions.as_dict())


def main(
    instance_id: str,
    limits: dict,
    predictions_file: str,
    test_patch_dir: str,
    observe_tests: bool,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """
    docker_client = docker.from_env()
    work_dir = build_work_dir(instance_id)
    docker_log_file = work_dir / "docker.log"
    docker_logger = setup_logger(instance_id, docker_log_file)
    logger_fn = build_logger(work_dir, instance_id)
    limits_obj = build_limits(instance_id, limits)
    dataset = load_dataset(DATASET_NAME, [instance_id])
    instance: SWEbenchInstance = dataset[0]
    instance_id = instance["instance_id"]

    assert predictions_file

    logger_fn(
        "info",
        "solve",
        f"Solving instance with test_files={limits_obj.test_files_limit}, code_files={limits_obj.code_files_limit} in directory {work_dir}",
    )

    if getenv("APPMAP_NAVIE_MODEL"):
        llm = getenv("APPMAP_NAVIE_MODEL")
    elif getenv("OPENAI_API_KEY"):
        llm = "openai"
    elif getenv("ANTHROPIC_API_KEY"):
        llm = "anthropic"
    else:
        raise Exception(
            "Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set; what LLM are we using?"
        )
    assert llm
    logger_fn("solve-instance", f"Using LLM: {llm}")

    test_spec = make_test_spec(instance)

    image_store = ImageStore(
        docker_client,
    )
    image_store.ensure([test_spec])

    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    source_dir = work_dir / "source"
    navie_work_dir = work_dir / "navie"
    navie_work_dir.mkdir(parents=True, exist_ok=True)

    test_patch_file = Path(test_patch_dir) / f"{instance_id}.json"
    test_patch_result: Optional[TestPatchResult] = None
    if test_patch_file.exists():
        logger_fn(
            "info",
            "solve",
            f"Loading test patch from {test_patch_file}",
        )
        with open(test_patch_file) as f:
            test_patch_result_dict: dict[str, Optional[str]] = json.load(f)
            test_patch_result = TestPatchResult(
                edit_test_file=Path(
                    cast(str, test_patch_result_dict["edit_test_file"])
                ),
                test_patch=(
                    Patch(test_patch_result_dict["test_patch"])
                    if test_patch_result_dict["test_patch"]
                    else None
                ),
                inverted_patch=(
                    Patch(test_patch_result_dict["inverted_patch"])
                    if test_patch_result_dict["inverted_patch"]
                    else None
                ),
            )

    solution_listener = SolutionListener(instance_id)

    def with_container(fn: Callable[[docker.models.containers.Container], None]):
        container = build_container(
            test_spec, docker_client, instance_id, docker_logger, False
        )
        container.start()
        logger_fn("solve", f"Container started: {container.id}")
        try:
            return fn(container)
        finally:
            cleanup_container(docker_client, container, docker_logger)

    def with_error_reporting(fn: Callable):
        try:
            return fn()
        except Exception as e:
            report_error(
                logger_fn,
                navie_work_dir,
                llm,
                predictions_file,
                instance,
                e,
            )

    def in_source_dir(fn: Callable):
        pwd = Path.cwd()
        chdir(str(source_dir))
        try:
            return fn()
        finally:
            chdir(pwd)

    def load_test_patch() -> Optional[TestPatchResult]:
        if test_patch_result:
            logger_fn(
                "info",
                "solve",
                f"Using test patch result from {test_patch_file}",
            )
            solution_listener.on_test_patch(
                test_patch_result["edit_test_file"],
                test_patch_result["test_patch"],
                test_patch_result["inverted_patch"],
            )
            return test_patch_result

    def solve_test_patch() -> Optional[TestPatchResult]:
        if limits_obj.test_files_limit == 0:
            logger_fn(
                "info",
                "solve",
                "Skipping test solver because test_files_limit is 0",
            )
            return None

        logger_fn("info", "solve", "Solving test patch")
        solver = build_solve_test(
            logger_fn,
            navie_work_dir,
            docker_client,
            instance,
            limits_obj,
        )
        solver.solve_listeners.append(solution_listener)
        solver.solve()

        if not solver.edit_test_file:
            return None

        return TestPatchResult(
            edit_test_file=solver.edit_test_file,
            test_patch=solver.test_patch,
            inverted_patch=solver.inverted_patch,
        )

    def get_test_patch() -> Optional[TestPatchResult]:
        return load_test_patch() or in_source_dir(solve_test_patch)

    def solve_code(
        edit_test_file: Optional[Path],
        test_patch: Optional[Patch],
        inverted_patch: Optional[Patch],
    ):
        solver = build_solve_code(
            logger_fn,
            navie_work_dir,
            docker_client,
            instance,
            limits_obj,
            observe_tests,
            edit_test_file,
            test_patch,
            inverted_patch,
        )
        solver.solve_listeners.append(solution_listener)
        solver.solve()

    def solve_test_and_code(container: docker.models.containers.Container):
        # If source_dir doesn't exist, create it and clone the repo
        if not source_dir.exists():
            checkout_code(logger_fn, container, source_dir, tmp_dir)

        solution_listener.on_solve_start(navie_work_dir)
        try:
            test_patch_result = get_test_patch()
            if test_patch_result:
                edit_test_file = test_patch_result["edit_test_file"]
                test_patch = test_patch_result["test_patch"]
                inverted_patch = test_patch_result["inverted_patch"]
            else:
                edit_test_file = None
                test_patch = None
                inverted_patch = None

            if limits_obj.code_files_limit == 0:
                logger_fn(
                    "info",
                    "solve",
                    "Skipping code solver because code_files_limit is 0",
                )
            else:
                in_source_dir(
                    lambda: solve_code(edit_test_file, test_patch, inverted_patch)
                )
        finally:
            solution_listener.on_completed()

        solution = solution_listener.build_solution()
        report_solution(
            logger_fn,
            navie_work_dir,
            llm,
            predictions_file,
            instance,
            limits_obj.test_files_limit > 0,
            limits_obj.code_files_limit > 0,
            solution,
        )

    with_error_reporting(lambda: with_container(solve_test_and_code))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    parser.add_argument(
        "--predictions",
        type=str,
        help="File to write the prediction",
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

    configure_limits(parser)
    configure_clean_option(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_clean_option(args)

    args.predictions_file = args.predictions or "predictions.jsonl"
    del args.predictions  # type: ignore
    main(**vars(args))
