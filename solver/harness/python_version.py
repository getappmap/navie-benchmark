from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS
from swebench.harness.test_spec import TestSpec


def python_version_for_test_spec(test_spec: TestSpec) -> str:
    return python_version_for_repo_and_version(test_spec.repo, test_spec.version)


def python_version_for_repo_and_version(repo: str, version: str) -> str:
    config = MAP_REPO_VERSION_TO_SPECS[repo][version]
    if not config.get("python"):
        raise ValueError(f"Python version not found for {repo} {version}")

    return config["python"]


def python_version_ok_for_test_spec(
    test_spec: TestSpec, major: int, minor: int
) -> bool:
    python_version = python_version_for_test_spec(test_spec)
    parsed_version = tuple(map(int, python_version.split(".")))
    return parsed_version >= (major, minor)
