# MISSION PLAN
GOAL: قم بحذف جميع التقارير الموجودة داخل outbox الموجود داخل مجلد Cloud-Controlled-Agent بإستثناء اخر تقريرين
STATE: PROCESSING
UPDATED_AT: 2026-03-15T16:38:27.875696+00:00

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
TITLE: Implement Python script to delete files
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- Files are correctly listed and sorted by last modification time.
- All but the last two files are deleted.
COMMAND_HINT:
- Execute the provided Python script using the correct path to the "outbox" directory.
RETRIES: 0

## STEP 3
TITLE: Verify deletion of files
STATUS: PENDING
ENGINE: AUTO
SUCCESS_CRITERIA:
- The last two files remain in the "outbox" directory.
- All other files are deleted.
COMMAND_HINT:
- Check the "outbox" directory for the remaining files.
RETRIES: 0

## NOTES
- The provided Python script seems mostly correct but needs to be executed correctly with the right path to the "outbox" directory.
- Ensure to handle potential errors during file listing, sorting, and deletion.
- The script should be executed using Python, and the correct path to the "outbox" directory should be provided when prompted.
