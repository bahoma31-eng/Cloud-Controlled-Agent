# MISSION PLAN
GOAL: قم بحذف جميع ملفات التقارير في مجلد outbox باستثناء آخر ملفين. ملاحظة: استخدم حصراً الدوال البرمجية المدمجة للتعامل مع GitHub (مثل list_outbox_files و delete_file_content) ولا تحاول الاتصال بـ API خارجي.
STATE: PROCESSING
UPDATED_AT: 2026-03-15T22:30:51.024322+00:00

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
TITLE: List all files in outbox directory
STATUS: RETRY
ENGINE: PYTHON
SUCCESS_CRITERIA:
- List of files in outbox directory is obtained.
COMMAND_HINT:
- Use list_outbox_files function to get the list of files.
RETRIES: 1

## STEP 3
TITLE: Sort files by date and select files to delete
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- List of files to delete is generated.
COMMAND_HINT:
- Sort files by date and exclude the last two files.
RETRIES: 0

## STEP 4
TITLE: Delete selected files
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- Selected files are deleted.
COMMAND_HINT:
- Use delete_file_content function to delete the files.
RETRIES: 0

## NOTES
- Plan updated based on latest logs and mission goal.
- Next step is to list all files in outbox directory.
- STEP 2 FAIL: No reason.
