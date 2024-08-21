from argparse import ArgumentParser
from os import chdir, unlink
from pathlib import Path
import resource
import tarfile
from time import time
import sys
import docker

sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)

from navie.editor import Editor

from swebench.harness.docker_build import (
    build_container,
    build_env_images,
    close_logger,
    setup_logger,
)
from swebench.harness.docker_utils import (
    clean_images,
    cleanup_container,
    exec_run_with_timeout,
    list_images,
)
from swebench.harness.test_spec import make_test_spec
from swebench.harness.utils import load_swebench_dataset, str2bool


def main(
    dataset_name: str,
    split: str,
    instance_ids: list,
    max_workers: int,
    force_rebuild: bool,
    cache_level: str,
    clean: bool,
    open_file_limit: int,
    run_id: str,
):
    """
    Run evaluation harness for the given dataset and predictions.
    """
    work_dir = Path(__file__).parent.parent / "work" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    resource.setrlimit(resource.RLIMIT_NOFILE, (open_file_limit, open_file_limit))
    client = docker.from_env()

    full_dataset = load_swebench_dataset(dataset_name, split, instance_ids)
    dataset = full_dataset
    existing_images = list_images(client)
    print(f"Running {len(dataset)} unevaluated instances...")
    if not dataset:
        print("No instances to run.")
        return

    # build environment images
    build_env_images(client, dataset, force_rebuild, max_workers)

    for instance in dataset:
        instance_id = instance["instance_id"]
        issue_text = instance["problem_statement"]

        test_spec = make_test_spec(instance)

        log_dir = work_dir / "logs" / "plan" / instance_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "run_instance.log"
        logger = setup_logger(instance_id, log_file)

        tmp_dir = work_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        source_dir = work_dir / "source"
        navie_work_dir = work_dir / "navie"

        # plan the issue
        container = None
        try:
            # Build + start instance container (instance image should already be built)
            container = build_container(
                test_spec, client, run_id, logger, False, force_rebuild
            )
            container.start()
            logger.info(f"Container for {instance_id} started: {container.id}")

            # If source_dir doesn't exist, create it and clone the repo
            if not source_dir.exists():
                source_dir.mkdir(parents=True, exist_ok=True)

                # Export the .git directory from the container as a tar file
                # Unpack it into the work directory
                logger.info("Creating git archive in the container")
                exec_run_with_timeout(
                    container, "git archive --format=tar.gz -o /tmp/source.tar.gz HEAD"
                )
                logger.info(
                    f"Copying git archive out of the container and unpacking it to {source_dir}"
                )
                (archive, _) = container.get_archive("/tmp/source.tar.gz")
                with open(tmp_dir / "source.tar", "wb") as f:
                    for chunk in archive:
                        f.write(chunk)

                # Unpack the tar file to the temp directory
                with tarfile.open(tmp_dir / "source.tar") as tar:
                    tar.extractall(tmp_dir)
                # Unpack the source.tar.gz to the source directory
                with tarfile.open(tmp_dir / "source.tar.gz") as tar:
                    tar.extractall(source_dir)

                # Delete the files in tmp dir
                for file in ["source.tar", "source.tar.gz"]:
                    unlink(tmp_dir / file)

            # Run the plan script
            logger.info("Running plan script")

            # os chdir to source_dir
            pwd = Path.cwd()
            chdir(source_dir)
            try:
                editor = Editor(navie_work_dir)
                editor.plan(issue_text)
            finally:
                chdir(pwd)

        except Exception as e:
            print(f"[plan] Error running plan for {instance_id}: {e}")
        finally:
            close_logger(logger)
            # Remove instance container + image, close logger
            cleanup_container(client, container, logger)

    return


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--dataset_name",
        default="princeton-nlp/SWE-bench_Lite",
        type=str,
        help="Name of dataset or path to JSON file.",
    )
    parser.add_argument(
        "--split", type=str, default="test", help="Split of the dataset"
    )
    parser.add_argument(
        "--instance_ids",
        nargs="+",
        type=str,
        help="Instance IDs to run (space separated)",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=4,
        help="Maximum number of workers (should be <= 75%% of CPU cores)",
    )
    parser.add_argument(
        "--open_file_limit", type=int, default=4096, help="Open file limit"
    )
    parser.add_argument(
        "--force_rebuild",
        type=str2bool,
        default=False,
        help="Force rebuild of all images",
    )
    parser.add_argument(
        "--cache_level",
        type=str,
        choices=["none", "base", "env", "instance"],
        help="Cache level - remove images above this level",
        default="env",
    )
    # if clean is true then we remove all images that are above the cache level
    # if clean is false, we only remove images above the cache level if they don't already exist
    parser.add_argument(
        "--clean", type=str2bool, default=False, help="Clean images above cache level"
    )
    parser.add_argument("--run_id", type=str, help="Run ID - identifies the run")

    args = parser.parse_args()
    if not args.run_id:
        time_millis = int(time() * 1000)
        args.run_id = f"plan_{time_millis}"
        print(f"Generated run ID: {args.run_id}")

    main(**vars(args))
