# Import Solve Test Run Feature

## Overview

The "Import Solve Test Run" feature facilitates the process of importing data from a solve test run, which might have been executed locally or as part of a GitHub Workflow. The feature is designed to organize and make this data accessible for further analysis and testing processes. It can handle both locally stored data and data that needs to be downloaded from GitHub.

## Usage

The feature is executed via a command-line interface, and it provides several options to import and organize the solve test run data effectively. 

### Command-Line Options

- `--run_id`: Specifies the GitHub Workflow run ID to download and import. If this option is used, the feature will handle downloading the data from GitHub.
- `--solve_dir`: Specifies a local directory that contains the solve results to be imported and organized.
- `--local_run_name`: Assigns a name to the local run being archived, with a default name of "local".
- `--no_download`: Prevents downloading of artifacts if set, instead, only unpacks and organizes existing data.
- `--no_link`: Skips the creation of symlinks to the test patches.
- `--test_patch_dir`: Specifies an optional directory to store symlinks to the test patches. If not provided, a default location is used.

## Process

1. **Data Directory Setup**: Based on the provided options, it initializes the run directory for storing the imported data, ensuring all necessary parent directories exist.

2. **Data Download**: If a `run_id` is specified and `no_download` is not set, the feature downloads the artifacts from GitHub using the provided run ID.

3. **Data Import and Archival**: 
   - If `solve_dir` is specified, local data is archived to create a standardized set of artifacts similar to those downloadable from a GitHub Workflow run. This includes prediction, solution, solve, and test patch data.
   - Extraction and organization of test patches into a structured format for easy access and analysis.

4. **Test Patch Management**:
   - Handles the symlinking of new, optimal test patches to a specified directory, facilitating easier access and reference.
   - Validates test patches to ensure they are optimal before linking.

5. **Test Patch Unpacking**:
   - Unpacks compressed test patch files and organizes them under a standardized directory structure for consistent access.

The feature integrates with other components to ensure that the solve test data is accurately imported, organized, and prepared for subsequent activities such as testing and evaluation.