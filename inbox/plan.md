# MISSION PLAN
GOAL: قم بحذف جميع التقارير الموجودة داخل outbox الموجود داخل مجلد Cloud-Controlled-Agent بإستثناء اخر تقريرين
STATE: PROCESSING
UPDATED_AT: 2026-03-15T16:11:32.992836+00:00

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
RETRIES: 1

## STEP 3
TITLE: Verify file deletion
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- Verify that only the last two files remain in the outbox directory.
COMMAND_HINT:
- Use the command: Get-ChildItem -Path "path/to/outbox" to verify the files.
RETRIES: 0

## NOTES
- The Python script should be executed with caution, as it permanently deletes files without asking for confirmation.
- Ensure you have backups of your important files before running the script.
- The correct path to the "outbox" directory should be provided when prompted by the script.
- The latest logs indicate issues with the script execution, including missing terminators and parser errors, which need to be addressed before proceeding.
