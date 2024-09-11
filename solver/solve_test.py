from argparse import ArgumentParser
from os import chdir
from pathlib import Path
import sys
import docker
from solver.workflow.validate_test import validate_test
from tree_sitter import Language, Parser

from solver.appmap.appmap import AppMap

# Assuming you have built the language parsers into a library
# Alternatively, download pre-built parsers from https://github.com/tree-sitter/tree-sitter-python
Language.build_library("build/my-languages.so", ["vendor/tree-sitter-python"])

PY_LANGUAGE = Language("build/my-languages.so", "python")


def load_and_print_function_code(source_file: Path, lineno: int):
    parser = Parser()
    parser.set_language(PY_LANGUAGE)

    with source_file.open() as f:
        source_code = f.read()

    tree = parser.parse(bytes(source_code, "utf8"))
    root_node = tree.root_node

    def find_function_node(node, lineno):
        if node.type == "function_definition":
            function_start_line = node.start_point[0] + 1
            function_end_line = node.end_point[0] + 1
            if function_start_line <= lineno <= function_end_line:
                return node
        for child in node.children:
            result = find_function_node(child, lineno)
            if result:
                return result
        return None

    function_node = find_function_node(root_node, lineno)

    if function_node is not None:
        function_code = source_code[function_node.start_byte : function_node.end_byte]
        print(function_code)
    else:
        print("Function containing the specified line number not found.")


# Integrate into your existing function
def print_appmap(appmap: AppMap, source_dir: str):
    for location in appmap.list_locations():
        print(location)
        print(source_dir)
        if source_dir:
            path, lineno = location.split(":")
            if not lineno:
                print(f"Line number not found in {location}")
                continue

            lineno = int(lineno)
            source_file = Path(source_dir) / path
            if source_file.exists():
                with source_file.open() as f:
                    source = f.readlines()
                    snippet = source[int(lineno) - 1 : int(lineno) + 10]
                    print("".join(snippet))

                # Load and print the function code with tree-sitter
                load_and_print_function_code(source_file, lineno)


sys.path.append(
    str(Path(__file__).resolve().parents[1] / "submodules" / "navie-editor")
)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from swebench.harness.test_spec import make_test_spec

from solver.workflow.work_dir import WorkDir
from solver.workflow.choose_test_file import choose_test_files
from solver.workflow.generate_and_validate_test import (
    TestPatchResult,
    generate_and_validate_test,
    Context,
    is_optimal_test_patch,
    patch_score,
)
from solver.harness.image_store import ImageStore
from solver.solve import DATASET_NAME
from solver.cli import (
    apply_limits,
    apply_clean_option,
    build_limits,
    build_logger,
    build_work_dir,
    build_workflow,
    configure_limits,
    configure_clean_option,
    load_dataset,
)


def main(
    instance_id: str,
    limits: dict,
):
    """
    Generate a test that reproduces the problem_statement in a given instance.
    """

    docker_client = docker.from_env()
    work_dir = build_work_dir(instance_id)
    logger_fn = build_logger(work_dir, instance_id)
    limits_obj = build_limits(limits)
    dataset = load_dataset(DATASET_NAME, [instance_id])

    instance = dataset[0]
    navie_work_dir = WorkDir(work_dir / "navie")
    source_dir = work_dir / "source"

    navie_work_dir.path.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        raise Exception(
            f"Source directory {source_dir} does not exist. It should already be checked out to run this script. Try running solve.py first, then using this script for re-runs."
        )

    test_spec = make_test_spec(instance)
    image_store = ImageStore(docker_client)
    image_store.ensure([test_spec])

    print(f"[solve_test]Changing directory to {source_dir}")
    chdir(source_dir)

    workflow = build_workflow(
        logger_fn, navie_work_dir.path, docker_client, instance, limits_obj
    )

    def validate(work_dir: WorkDir, path: Path) -> bool:
        return validate_test(logger_fn, work_dir.path, docker_client, test_spec, path)

    edit_test_files = choose_test_files(
        logger_fn,
        navie_work_dir,
        workflow.trajectory_file,
        workflow.issue_text,
        limits_obj.test_files_limit,
        validate,
    )
    if not edit_test_files:
        print("[solve_test] No test files to edit.")
        return

    patches = generate_and_validate_test(
        Context(
            limits_obj,
            logger_fn,
            navie_work_dir,
            docker_client,
            test_spec.repo,
            test_spec.version,
            [],
        ),
        edit_test_files,
        workflow.generate_test,
        workflow.run_test,
        workflow.invert_test,
    )

    def print_patch(patch: TestPatchResult):
        print("[solve_test] Test patch:")
        print(patch["test_patch"])
        print("[solve_test] Inverted test patch:")
        print(patch["inverted_patch"])

    if not patches:
        print("[solve_test] No test patches generated.")
        return

    optimal_patches = [patch for patch in patches if is_optimal_test_patch(patch)]
    if optimal_patches:
        print("[solve_test] Generated optimal test patch:")
        for patch in optimal_patches:
            print_patch(patch)
        return

    print("[solve_test] Generated sub-optimal test patch:")

    patches.sort(key=patch_score, reverse=True)
    patch = patches[0]
    print_patch(patch)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--instance_id", type=str, help="Instance ID to run", required=True
    )
    configure_clean_option(parser)
    configure_limits(parser)

    args = parser.parse_args()

    apply_limits(args)
    apply_clean_option(args)

    main(**vars(args))
