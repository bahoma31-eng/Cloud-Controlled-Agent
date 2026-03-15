# MISSION PLAN
GOAL: Execute Python script to list, sort, and delete files in the "outbox" directory
STATE: PROCESSING
UPDATED_AT: 2026-03-15T18:32:06.693829+00:00

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
TITLE: Execute Python script to list, sort, and delete files
STATUS: IN_PROGRESS
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- Files are correctly listed and sorted by their last modification time.
- All but the last two files are deleted.
COMMAND_HINT:
- Run the Python script using the command: python helper.py
RETRIES: 0

## STEP 3
TITLE: Verify file deletion
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- The "outbox" directory contains only the last two files.
COMMAND_HINT:
- Use the command: Get-ChildItem -Path "path/to/outbox" to verify the files.
RETRIES: 0

## NOTES
- The Python script must be executed correctly to avoid errors.
- Ensure the correct path to the "outbox" directory is provided when prompted by the script.
- The script permanently deletes files without asking for confirmation, so use it with caution and ensure backups of important files are available.
