from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS


def make_run_test_command(repo, version, test_directives):
    return " ".join(
        [
            MAP_REPO_VERSION_TO_SPECS[repo][version]["test_cmd"],
            *test_directives,
        ]
    )


def make_run_test_prep_commands(specs, env_name, custom_eval=True):
    # Build eval commands for a given instance.
    # Unlike swebench.harness.test_spec.make_eval_script_list, this function does not
    # install the patch file, reset the repo, run the tests, or reset the repo after testing.
    # It just builds the commands that set everything up for the test command to actually run.
    # See make_run_test_command for the actual test command.

    # Commands that are present in make_eval_script_list have been removed here, because
    # the are run later. They are:
    #
    # cd {repo_directory}
    # source /opt/miniconda3/bin/activate
    # conda activate {env_name}

    repo_directory = f"/{env_name}"

    eval_commands = []
    if custom_eval:
        if "eval_commands" in specs:
            eval_commands += specs["eval_commands"]
    eval_commands += [
        f"cd {repo_directory}",
        "source /opt/miniconda3/bin/activate",
        f"conda activate {env_name}",
    ]
    if "install" in specs:
        eval_commands.append(specs["install"])

    return eval_commands
