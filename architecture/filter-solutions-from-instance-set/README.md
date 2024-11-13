# Feature: Filter Solutions from Instance Set

## Overview

The "Filter Solutions from Instance Set" feature identifies and filters out solved instance IDs from a set of instances. The feature primarily focuses on extracting unsolved instances from a given dataset, ensuring users work with fresh data for further processing or evaluation.

## Usage

### Command-line Interface

This feature is executed through a command-line interface (CLI) which is accessible by running the `filter_solutions_from_instance_set.py` script. Users will invoke this script when they want to process instance sets and filter out instances that have already been marked as solved.

### User Inputs

- **Instance Set (`--instance_set`)**: Accepts one or more instance set names as input. These are the sets the user wants to filter by removing solved instances.
- **Output Instance Set (`--output_instance_set`)**: Specifies the name of the output file where unsolved instance IDs will be saved.
- **Filter By (`--filter_by`)**: Determines whether to filter by "code" or "test" patches, affecting the directory (`code_patches` or `test_patches`) from which solved instances are identified.

### Operational Flow

1. **Load Instances**: The script begins by loading all instance IDs from the provided instance set(s).
2. **Select Filter Directory**: Depending on the `filter_by` parameter, the script selects the appropriate directory (either `data/code_patches` or `data/test_patches`) to identify solved instances.
3. **Exclude Solved Instances**: It iterates through solution files to exclude all solved instance IDs from the original instance set.
4. **Output Results**: The remaining unsolved instance IDs are sorted and written to the specified output file. The output file is also prefixed with metadata information, such as the creation date and current commit SHA for traceability.

### Key Output

The primary output is a text file containing unsolved instance IDs. This file serves to update and maintain the dataset by ignoring already processed or solved problems.

### Error Handling

If the provided filter type is invalid (`not "code" or "test"`), an appropriate error message is raised, halting execution to prevent unintended filtering.

### Automation

This feature fits into a larger workflow where it can be called automatically after solving activities within a pipeline, ensuring that subsequent processing steps only deal with active, unsolved instances.