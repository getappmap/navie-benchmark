from pathlib import Path
import sys
from typing import Optional
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

sys.path.append(str(Path(__file__)))

from solver.appmap import AppMap

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)


def load_and_print_function_code(source_file: Path, lineno: int):
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
        if source_dir:
            path, lineno = location.split(":")
            if lineno:
                lineno = int(lineno)
            source_file = Path(source_dir) / path
            if source_file.exists():
                # with source_file.open() as f:
                #     source = f.readlines()
                #     snippet = source[int(lineno) - 1 : int(lineno) + 10]
                #     print("".join(snippet))

                # Load and print the function code with tree-sitter
                print(f"Printing function code for {source_file}:{lineno}")
                load_and_print_function_code(source_file, lineno)


def main(appmap_dir_name: str, source_dir: str):
    """
    Print locations from all appmap files in the given directory.
    """
    appmap_dir = Path(appmap_dir_name)
    if not appmap_dir.exists():
        print(f"AppMap directory {appmap_dir} not found.")
        sys.exit(1)

    # # Recursively find *.appmap.json in the appmap_dir
    # def print_appmap(appmap: AppMap):
    #     for location in appmap.list_locations():
    #         print(location)
    #         print(source_dir)
    #         if source_dir:
    #             path, lineno = location.split(":")
    #             if lineno:
    #                 lineno = int(lineno)
    #             source_file = Path(source_dir) / path
    #             if source_file.exists():
    #                 with source_file.open() as f:
    #                     source = f.readlines()
    #                     snippet = source[int(lineno) - 1 : int(lineno) + 10]
    #                     print("".join(snippet))

    #                 # Load and print the function code with tree-sitter

    for appmap_file in appmap_dir.rglob("*.appmap.json"):
        with appmap_file.open() as f:
            appmap_data = f.read()
            appmap = AppMap(appmap_data)
            print_appmap(appmap, source_dir)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
