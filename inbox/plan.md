# MISSION PLAN
GOAL: قم بحذف جميع التقارير الموجودة داخل مجلد outbox بإستثناء اخر تقريرين
STATE: PROCESSING
UPDATED_AT: 2026-03-15T15:43:47.287104+00:00

## STEP 1
TITLE: Analyze goal and propose first executable action
STATUS: DONE
ENGINE: AUTO
SUCCESS_CRITERIA:
- First concrete executable action is produced.
COMMAND_HINT:
- Generate command/script for first action.
RETRIES: 0

## STEP 2
TITLE: Execute Python script to delete files
STATUS: IN_PROGRESS
ENGINE: PYTHON
SUCCESS_CRITERIA:
- Files are deleted successfully.
COMMAND_HINT:
- Run the Python script using the command: python helper.py
RETRIES: 3

## STEP 3
TITLE: Verify deletion of files
STATUS: PENDING
ENGINE: AUTO
SUCCESS_CRITERIA:
- Only the last two files remain in the outbox directory.
COMMAND_HINT:
- Check the outbox directory for remaining files.
RETRIES: 0

## STEP 4
TITLE: Review and adjust Python script for error handling
STATUS: DONE
ENGINE: PYTHON
SUCCESS_CRITERIA:
- The script includes error handling for file operations.
COMMAND_HINT:
- Review the latest logs to identify and address the issue causing the script to fail.
RETRIES: 0

## STEP 5
TITLE: Address the 'terminator' issue in the Python script execution
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- The script executes without the 'terminator' error.
COMMAND_HINT:
- Ensure the correct execution of the Python script using PowerShell.
RETRIES: 0

## NOTES
- The Python script should be executed with caution, as it permanently deletes files without asking for confirmation.
- Ensure backups of important files are available before executing the script.
- The correct path to the outbox directory should be provided when prompted by the script.
- Review the latest logs to identify and address the issue causing the script to fail.
- Consider adding additional error handling to the Python script to improve its robustness.
- The 'terminator' issue needs to be addressed to ensure correct script execution.
