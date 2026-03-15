# MISSION PLAN
GOAL: قم بحذف جميع التقارير الموجودة داخل مجلد outbox بإستثناء اخر تقريرين
STATE: PROCESSING
UPDATED_AT: 2026-03-15T15:40:16.087362+00:00

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
STATUS: RETRY
ENGINE: PYTHON
SUCCESS_CRITERIA:
- Files are deleted successfully.
COMMAND_HINT:
- Run the Python script using the command: python helper.py
RETRIES: 1

## STEP 3
TITLE: Verify deletion of files
STATUS: PENDING
ENGINE: AUTO
SUCCESS_CRITERIA:
- Only the last two files remain in the outbox directory.
COMMAND_HINT:
- Check the outbox directory for remaining files.
RETRIES: 0

## NOTES
- The Python script should be executed with caution, as it permanently deletes files without asking for confirmation.
- Ensure backups of important files are available before executing the script.
- The correct path to the outbox directory should be provided when prompted by the script.
- Review the latest logs to identify and address the issue causing the script to fail.
- Consider adding additional error handling to the Python script to improve its robustness.
