def test_files_to_modules(directives: list) -> list:
    # For Django tests, remove extension + "tests/" prefix and convert slashes to dots (module referencing)
    directives_transformed = []
    for d in directives:
        d = d[: -len(".py")] if d.endswith(".py") else d
        d = d[len("tests/") :] if d.startswith("tests/") else d
        d = d.replace("/", ".")
        directives_transformed.append(d)
    return directives_transformed


def make_test_directives(repo: str, test_modules_or_paths: list) -> list:
    if repo == "django/django":
        return test_files_to_modules(test_modules_or_paths)

    return test_modules_or_paths
