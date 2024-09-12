from argparse import ArgumentParser
from json import dumps
from os import chdir, getenv
from pathlib import Path
import sys
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from solver.workflow.patch import Patch
from swebench.harness.docker_build import (
    build_container,
    setup_logger,
)
from swebench.harness.docker_utils import (
    cleanup_container,
)
from swebench.harness.test_spec import make_test_spec
from swebench.harness.constants import SWEbenchInstance

from solver.prediction import Prediction
from solver.workflow.solution_listener import (
    Solution,
    SolutionListener,
    solution_to_plain_types,
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
    solution: Solution,
):
    def solution_str(solution: Solution):
        result = []
        for k, v in solution.items():
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
        print(solution_str(solution))

    print_solution()
    solution_attrs = solution_to_plain_types(solution)
    with open(navie_work_dir / "solution.json", "w") as f:
        f.write(dumps(solution_attrs, indent=2))

    predictions = Prediction.build_predictions(instance, llm)
    predictions.add_prediction("model_patch", solution["code_patch"])
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
    assert predictions_file

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

    instance_id = instance["instance_id"]

    test_spec = make_test_spec(instance)

    image_store = ImageStore(
        docker_client,
    )
    image_store.ensure([test_spec])

    tmp_dir = work_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    source_dir = work_dir / "source"
    navie_work_dir = work_dir / "navie"

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

        solution_listener = SolutionListener(instance_id)
        solution_listener.on_solve_start(navie_work_dir)
        chdir(source_dir)
        try:
            solve_test = build_solve_test(
                logger_fn,
                navie_work_dir,
                docker_client,
                instance,
                limits_obj,
            )
            solve_test.solve_listeners.append(solution_listener)
            solve_test.solve()

            solve_code = build_solve_code(
                logger_fn,
                navie_work_dir,
                docker_client,
                instance,
                limits_obj,
                solve_test.edit_test_file,
                solve_test.test_patch,
                solve_test.inverted_patch,
            )
            solve_code.solve_listeners.append(solution_listener)
            solve_code.solve()
        finally:
            solution_listener.on_completed()
            chdir(pwd)

        solution = solution_listener.build_solution()
        report_solution(
            logger_fn,
            navie_work_dir,
            llm,
            predictions_file,
            instance,
            solution,
        )
    except Exception as e:
        report_error(
            logger_fn,
            navie_work_dir,
            llm,
            predictions_file,
            instance,
            e,
        )
    finally:
        # Remove instance container + image, close logger
        if container:
            logger_fn("info", "solve-instance", f"Cleaning up container {container.id}")
            cleanup_container(docker_client, container, docker_logger)

    return


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

    configure_limits(parser)
    configure_clean_option(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_clean_option(args)

    args.predictions_file = args.predictions or "predictions.jsonl"
    del args.predictions  # type: ignore
    main(**vars(args))
