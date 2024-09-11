from pathlib import Path
from solver.appmap import AppMap
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


def load_and_function_code(source_file: Path, lineno: int):
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
        code = source_code[function_node.start_byte : function_node.end_byte]
        # IDK why this is happening. Just fix it up.
        if code.startswith("f "):
            code = "de" + code
        return code
    else:
        return None


def collect_appmap_context_from_directory(
    log,
    appmap_dir: Path,
):
    result: dict[str, str] = {}
    for appmap_file in appmap_dir.rglob("*.appmap.json"):
        with appmap_file.open() as f:
            appmap_data = f.read()
            try:
                appmap = AppMap(appmap_data)
                result = collect_appmap_context(log, appmap, result)
            except Exception as e:
                log(
                    "collect_appmap_context_from_directory",
                    f"Error processing {appmap_file}: {e}",
                )
    return result


def collect_appmap_context(
    log, appmap: AppMap, result: dict[str, str] = {}
) -> dict[str, str]:
    locations = appmap.list_locations()
    new_locations = [location for location in locations]
    for location in new_locations:
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

    return result
