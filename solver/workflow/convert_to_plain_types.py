from solver.workflow.patch import Patch


from pathlib import Path


def convert_to_plain_types(obj):
    if isinstance(obj, dict):
        return {str(k): convert_to_plain_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_plain_types(v) for v in obj]
    elif isinstance(obj, (Path, Patch)):
        return str(obj)
    else:
        return obj
