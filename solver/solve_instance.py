from argparse import ArgumentParser
from json import dumps
from os import chdir, getenv
from pathlib import Path
import sys
from typing import Optional, Union
import docker


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.constants import SWEbenchInstance

from solver.workflow.solution_listener import SolutionListener, solution_to_plain_types
from solver.harness.image_store import ImageStore
from solver.predictions_manager import PredictionsManager

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
)
from solver.checkout_code import checkout_code
from solver.workflow.patch import Patch

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
    limits_obj = build_limits(limits)
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
    print(f"Using LLM: {llm}")

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

        solution_listener = SolutionListener(instance_id)
        chdir(source_dir)
        workflow = None
        try:
            workflow = build_workflow(
                logger_fn,
                navie_work_dir,
                docker_client,
                instance,
                limits_obj,
            )
            workflow.solve_listeners.append(solution_listener)
            workflow.run()
        finally:
            chdir(pwd)

        solution = solution_listener.build_solution()
        solution_attrs = solution_to_plain_types(solution)
        with open(navie_work_dir / "solution.json", "w") as f:
            f.write(dumps(solution_attrs, indent=2))

        # Clone the instance as predictions
        prediction: dict = instance.copy()  # type: ignore

        def add_prediction(key: str, value: Union[str, Patch, Path, None]):
            prediction[key] = str(value) if value else None

        model_name_or_path = f"navie_082024+{llm}"

        add_prediction("model_patch", workflow.code_patch)
        add_prediction("model_name_or_path", model_name_or_path)
        add_prediction("model_test_patch", workflow.test_patch)
        add_prediction("model_inverted_patch", workflow.inverted_patch)
        add_prediction("model_edit_test_file", workflow.edit_test_file)

        PredictionsManager.add_prediction(predictions_file, prediction)

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
