from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional, Tuple
from solver.appmap import AppMap
import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Tree


PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


@lru_cache
def parse_file(file_path: Path) -> Tuple[Tree, bytes]:
    with open(file_path, "rb") as f:
        source = f.read()
        return parser.parse(source), source


def load_and_function_code(source_file: Path, lineno: int) -> Optional[str]:
    tree, source_code = parse_file(source_file)
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
        code = source_code[function_node.start_byte : function_node.end_byte]
        # IDK why this is happening. Just fix it up.
        if code.startswith(b"f "):
            code = b"de" + code
        return code.decode("utf-8")
    else:
        return None


def collect_appmap_context_from_directory(
    log,
    appmap_dir: Path,
):
    locations: set[str] = set()
    for appmap_file in appmap_dir.rglob("*.appmap.json"):
        with appmap_file.open() as f:
            appmap_data = f.read()
            try:
                appmap = AppMap(appmap_data)
                locations.update(appmap.list_locations())
            except Exception as e:
                log(
                    "collect_appmap_context_from_directory",
                    f"Error processing {appmap_file}: {e}",
                )
    return collect_appmap_context(log, locations)


def collect_appmap_context(log, locations: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for location in locations:
        path, lineno = location.split(":")
        if not lineno:
            log(
                "collect_appmap_context",
                f"Skipping location without line number: {location}",
            )
            continue

        lineno = int(lineno)
        source_file = Path(path)
        if source_file.exists():
            function_code = load_and_function_code(source_file, lineno)
            if function_code:
                result[location] = function_code
        else:
            log(
                "collect_appmap_context",
                f"Source file not found: {source_file}",
            )

    return result
