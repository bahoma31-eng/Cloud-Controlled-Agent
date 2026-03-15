# MISSION PLAN
GOAL: قم بحذف جميع التقارير الموجودة في outbox بإستثناء آخر تقريرين.
STATE: PROCESSING
UPDATED_AT: 2026-03-15T22:02:08.367800+00:00

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
TITLE: Connect to outbox and retrieve list of reports
STATUS: RETRY
ENGINE: POWERSHELL
SUCCESS_CRITERIA:
- List of reports is successfully retrieved.
COMMAND_HINT:
- Use outbox API to fetch report list.
RETRIES: 2

## STEP 3
TITLE: Filter out last two reports from the list
STATUS: PENDING
ENGINE: PYTHON
SUCCESS_CRITERIA:
- List of reports to be deleted is generated.
COMMAND_HINT:
- Use list slicing to exclude last two reports.
RETRIES: 0

## NOTES
- Device information has been parsed correctly.
- Next steps involve connecting to outbox and filtering reports.
- STEP 2 FAIL: No reason.
- STEP 2 HINT: Retry with safer command.
- STEP 2 FAIL: The report indicates that the planner output is malformed.
- STEP 2 HINT: Verify the planner output format to ensure it is executable.
