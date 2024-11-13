The purpose of this issue is to provide instructions on how to verify the open source status and benchmark results for AppMap Navie v2 on the Lite and Verified benchmarks.

## Navie is open source

You can find the benchmark code for Navie V2 here:

[https://github.com/getappmap/navie-benchmark](https://github.com/getappmap/navie-benchmark)

Within that project, there are two git submodules, which are also open source:

* [https://github.com/getappmap/appmap-js/](https://github.com/getappmap/appmap-js/)
* [https://github.com/getappmap/navie-editor](https://github.com/getappmap/navie-editor)

These three projects completely contain the code of Navie v2.

## Running the benchmark

### General instructions

You'll be using the GitHub Workflow `official.yml` to run the solver. It will generate test patches ("synthetic tests"), code patches ("solutions"), and then evaluate the results.

For best results, use `claude-3-5-sonnet-20241022` with GitHub Action environment variable `ANTHROPIC_API_KEY`.

Use the default branch of the repository, which is `swe-bench-2`.

### Instance set option

The primary input that you need to select is the instance set. The `instance_set` option names a ".txt" file that's located in `data/instance_sets`. For example, the instance set `verified_33_pct_1` includes 1/3 of the instances from the Verified set (every 3rd instance). Using instance sets enables you to run solver more quickly and cheaply than running the entire dataset. 

To run a quick "smoke" test, use instance set `smoke`.

To run the entire Verified dataset, use instance set `verified`.

### Other options

- **llm** `claude-3-5-sonnet-20241022`
- **context_token_limit** `64000` For economy, you can run with a smaller token limit (e.g. `16000`), however you'll lose a couple of percent in the solve rate.
- **context_token_limit_increase** `20` (default)
- **temperature_increase** `0.1` (default)
- **test_patch_solve_threshold** `1` (default)
- **max_test_solve_iterations** `3` (default)
- **num_runners** Size these according to the instance set that you use. We recommend using one runner for every 20-30 instances. With this many runners, you can expect the workflow to complete in 1-2 hours.
- **name** As desired

## Notes

_Evaluation_

If you prefer to use your own evaluation, rather than the code in this fork of swe-bench, you can remove that section from the Workflow.

_Environments other than GitHub Actions_

Of course, you don’t have to use GitHub Actions to run Navie. It’s just easy because it’s all configured. 

You can see from the official.yml that, aside from building a conda environment and installing some dependencies, it’s necessary to build submodules/appmap-js using yarn. 

---

Please let me know if you have any questions, or if you would like these instructions in a different format or for a different target system. 


