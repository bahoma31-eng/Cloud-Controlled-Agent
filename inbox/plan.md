# MISSION PLAN
GOAL: قم بحذف جميع ملفات التقارير في مجلد outbox باستثناء آخر ملفين. ملاحظة: استخدم حصراً الدوال البرمجية المدمجة للتعامل مع GitHub (مثل list_outbox_files و delete_file_content) ولا تحاول الاتصال بـ API خارجي.
STATE: PROCESSING
UPDATED_AT: 2026-03-15T22:11:36.177898+00:00

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
STATUS: IN_PROGRESS
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- List of files in outbox directory is retrieved.
COMMAND_HINT:
- Use list_outbox_files function to retrieve file list.
RETRIES: 1

## STEP 3
TITLE: Sort files by date and select files to delete
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- Files to delete are identified.
COMMAND_HINT:
- Use sorting and filtering to select files for deletion.
RETRIES: 0

## STEP 4
TITLE: Delete selected files
STATUS: PENDING
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- Selected files are deleted.
COMMAND_HINT:
- Use delete_file_content function to delete files.
RETRIES: 0

## NOTES
- Initial plan generated automatically.
- Planner output corrected to produce executable content.
- Next steps defined to achieve mission goal.
- STEP 2 FAIL: No reason.
- STEP 2 HINT: Retry with safer command.
