from solver.workflow.patch import Patch


from pathlib import Path


def convert_to_plain_types(obj) -> dict:
    # Convert all Patch and Path objects to strings
    attrs = obj.copy()
    for key, value in attrs.items():
        if isinstance(value, (Patch, Path)):
            attrs[key] = str(value)
    return attrs
