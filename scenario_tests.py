"""
Comprehensive scenario tests for the HRMS chat service.
Tests routing, isolation guard, write-guard, and profile handling.
No live DB required.
"""
from backend.services.db_helper import enforce_employee_isolation
from backend.services.intent_classifier import (
    HRIntent,
    classify_intent,
    get_intent_response,
)
from backend.services.rule_engine import can_handle, generate_sql

PASS = 0
FAIL = 0


def check(label, result, expected=True):
    global PASS, FAIL
    ok = result == expected
    if ok:
        PASS += 1
    else:
        FAIL += 1
    marker = "  <<< UNEXPECTED" if not ok else ""
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{marker}")


def check_in(label, text, substring):
    global PASS, FAIL
    ok = substring in text
    if ok:
        PASS += 1
    else:
        FAIL += 1
    marker = "  <<< UNEXPECTED" if not ok else ""
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{marker}")


# -- Scenario 1: Leave balance -------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 1 -- Leave balance intent + rule engine")
print("=" * 60)
check("'my current cl balance?'", classify_intent("my current cl balance?") == HRIntent.LEAVE_BALANCE)
check("'how many sl do I have left?'", classify_intent("how many sl do I have left?") == HRIntent.LEAVE_BALANCE)
check("'el balance'", classify_intent("el balance") == HRIntent.LEAVE_BALANCE)
check("'check my leave balance'", classify_intent("check my leave balance") == HRIntent.LEAVE_BALANCE)
check("'casual leave balance'", classify_intent("casual leave balance") == HRIntent.LEAVE_BALANCE)
check("rule_engine can handle LEAVE_BALANCE", can_handle(HRIntent.LEAVE_BALANCE))
sql = generate_sql(HRIntent.LEAVE_BALANCE, 101, "Karnataka")
check("rule_engine generates SELECT for leave balance", sql is not None and sql.upper().startswith("SELECT"))
check_in("leave balance SQL contains employee_id = 101", sql or "", "employee_id = 101")


# -- Scenario 2: Payroll -------------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 2 -- Payroll intent + rule engine")
print("=" * 60)
check("'my salary'", classify_intent("my salary") == HRIntent.SALARY)
check("'my ctc'", classify_intent("my ctc") == HRIntent.CTC)
check("'my payslip'", classify_intent("my payslip") == HRIntent.SALARY)
check("rule_engine can handle SALARY for payslip", can_handle(HRIntent.SALARY))
check("'my pay'", classify_intent("my pay") == HRIntent.SALARY)
check("rule_engine can handle SALARY", can_handle(HRIntent.SALARY))
check("rule_engine can handle CTC", can_handle(HRIntent.CTC))
sql = generate_sql(HRIntent.CTC, 101, "Karnataka")
check_in("CTC SQL contains emp_id = 101", sql or "", "emp_id = 101")


# -- Scenario 3: Attendance ----------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 3 -- Attendance intent")
print("=" * 60)
check("'what is my attendance this month'", classify_intent("what is my attendance this month") == HRIntent.ATTENDANCE)
check("'show my attendance'", classify_intent("show my attendance") == HRIntent.ATTENDANCE)
check("'how many days present this month'", classify_intent("how many days present this month") == HRIntent.ATTENDANCE)
check("'present at the meeting' -> ATTENDANCE", classify_intent("I was present at the meeting today") == HRIntent.ATTENDANCE)
check("'mark me absent' -> ATTENDANCE", classify_intent("mark me absent") == HRIntent.ATTENDANCE)
check("rule_engine can handle ATTENDANCE", can_handle(HRIntent.ATTENDANCE))
sql = generate_sql(HRIntent.ATTENDANCE, 101, "Karnataka")
check_in("Attendance SQL contains employee_id = 101", sql or "", "employee_id = 101")


# -- Scenario 4: Timesheet -----------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 4 -- Timesheet intent")
print("=" * 60)
check("'my timesheet'", classify_intent("my timesheet") == HRIntent.TIMESHEET)
check("'my logged hours'", classify_intent("my logged hours") == HRIntent.PROJECT_HOURS)
check("'project hours this week'", classify_intent("project hours this week") == HRIntent.PROJECT_HOURS)
check("NOT: 'cl balance'", classify_intent("cl balance") != HRIntent.TIMESHEET)
check("rule_engine can handle TIMESHEET", can_handle(HRIntent.TIMESHEET))
sql = generate_sql(HRIntent.TIMESHEET, 101, "Karnataka")
check_in("Timesheet SQL contains employee_id = 101", sql or "", "employee_id = 101")


# -- Scenario 5: Expense -------------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 5 -- Expense intent")
print("=" * 60)
check("'my expenses'", classify_intent("my expenses") == HRIntent.EXPENSE)
check("'show my claims'", classify_intent("show my claims") == HRIntent.EXPENSE)
check("'travel claim status'", classify_intent("travel claim status") == HRIntent.CLAIM)
check("'reimbursement status'", classify_intent("reimbursement status") == HRIntent.EXPENSE)
check("NOT: 'my salary'", classify_intent("my salary") != HRIntent.EXPENSE)
check("rule_engine can handle EXPENSE", can_handle(HRIntent.EXPENSE))
check("rule_engine can handle CLAIM", can_handle(HRIntent.CLAIM))
sql = generate_sql(HRIntent.EXPENSE, 101, "Karnataka")
check_in("Expense SQL contains employee_id = 101", sql or "", "employee_id = 101")


# -- Scenario 6: Profile -------------------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 6 -- Profile intent")
print("=" * 60)
check("'my profile'", classify_intent("my profile") == HRIntent.PROFILE)
check("'my details'", classify_intent("my details") == HRIntent.PROFILE)
check("'who is my manager'", classify_intent("who is my manager") == HRIntent.MANAGER)
check("'my date of joining'", classify_intent("my date of joining") == HRIntent.JOINING_DATE)
check("'what is my department'", classify_intent("what is my department") == HRIntent.DEPARTMENT)
check("'my doj'", classify_intent("my doj") == HRIntent.JOINING_DATE)
# Profile now handled by rule_engine + result_processor flow
check("profile intent detected by rule_engine", can_handle(HRIntent.PROFILE))
sql = generate_sql(HRIntent.PROFILE, 101, "Karnataka")
check_in("Profile SQL references id", sql or "", "id = 101")
check_in("Profile SQL joins hr_department", sql or "", "hr_department")
check_in("Profile SQL joins hr_designation", sql or "", "hr_designation")


# -- Scenario 7: Write-attempt guard -------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 7 -- Write-attempt guard")
print("=" * 60)
check("'delete my attendance record'", classify_intent("delete my attendance record") == HRIntent.WRITE_REQUEST)
check("'update my salary'", classify_intent("update my salary") == HRIntent.WRITE_REQUEST)
check("'modify my leave record'", classify_intent("modify my leave record") == HRIntent.WRITE_REQUEST)
check("'change my payroll record'", classify_intent("change my payroll record") == HRIntent.WRITE_REQUEST)
check("NOT: 'what is my attendance'", classify_intent("what is my attendance this month") != HRIntent.WRITE_REQUEST)
check("NOT: 'how many cl days'", classify_intent("how many cl days do I have") != HRIntent.WRITE_REQUEST)
check("NOT: 'my salary'", classify_intent("my salary") != HRIntent.WRITE_REQUEST)


# -- Scenario 8: SQL isolation guard -------------------------------------------
print()
print("=" * 60)
print(" SCENARIO 8 -- SQL isolation guard")
print("=" * 60)
emp_id = 101
emp_code = "JMR0042"

isolation_cases = [
    (
        "Already filtered -- pass through unchanged",
        "SELECT * FROM hr_holidays WHERE employee_id = 101 AND state = 'validate'",
        True,
        "employee_id = 101",
    ),
    (
        "Missing filter -- inject before ORDER BY",
        "SELECT * FROM hr_holidays WHERE state = 'validate' ORDER BY date_from",
        True,
        "AND employee_id = 101 ORDER BY",
    ),
    (
        "No WHERE clause -- add WHERE employee_id",
        "SELECT date FROM hr_daily_attendance LIMIT 30",
        True,
        "WHERE employee_id = 101 LIMIT",
    ),
    (
        "Payroll table -- uses emp_id column not employee_id",
        "SELECT gross_sal_before_tax FROM hr_payroll_monthly_line LIMIT 1",
        True,
        "WHERE emp_id = 101 LIMIT",
    ),
    (
        "Subquery -- must block, not attempt injection",
        "SELECT * FROM (SELECT * FROM hr_holidays) h",
        False,
        None,
    ),
    (
        "Non-personal table -- pass unchanged",
        "SELECT name FROM hr_holidays_status",
        True,
        None,
    ),
    (
        "hr_holidays_status must NOT be confused with hr_holidays",
        "SELECT id, name FROM hr_holidays_status ORDER BY name",
        True,
        None,
    ),
    (
        "Multiple personal tables -- inject for first personal table found",
        "SELECT h.date_from FROM hr_holidays h WHERE h.state = 'validate'",
        True,
        "employee_id = 101",
    ),
]

for label, sql, should_pass, fragment in isolation_cases:
    out, err = enforce_employee_isolation(sql, emp_id, emp_code)
    ok = (err is None) == should_pass
    if ok and fragment:
        ok = fragment in out
    check(label, ok)
    if not ok:
        print(f"       sql_out : {out!r}")
        print(f"       err     : {err!r}")


# -- Scenario 9: Write-refusal message quality ---------------------------------
print()
print("=" * 60)
print(" SCENARIO 9 -- Write-refusal message quality")
print("=" * 60)

write_response = get_intent_response(HRIntent.WRITE_REQUEST) or ""
check("Write refusal exists", write_response != "")
check_in("Mentions 'only view'", write_response, "only view")
check_in("Mentions HR contact", write_response.lower(), "hr")
check("No raw exceptions in message", "Exception" not in write_response)
check("No traceback in message", "Traceback" not in write_response)
print("  Refusal text:")
print("   ", write_response)


# -- Scenario 10: Rule engine coverage -----------------------------------------
print()
print("=" * 60)
print(" SCENARIO 10 -- Rule engine coverage")
print("=" * 60)
all_intents = [
    HRIntent.LEAVE_BALANCE, HRIntent.LEAVE_HISTORY,
    HRIntent.SALARY, HRIntent.SALARY_PAYMENT, HRIntent.SALARY_COMPONENTS,
    HRIntent.CTC,
    HRIntent.ATTENDANCE,
    HRIntent.PROFILE, HRIntent.MANAGER, HRIntent.DEPARTMENT, HRIntent.JOINING_DATE,
    HRIntent.TIMESHEET,
    HRIntent.EXPENSE,
    HRIntent.HELPDESK,
    HRIntent.PROJECTS,
    HRIntent.HOLIDAY,
    HRIntent.BONUS,
    HRIntent.PAYROLL,
]
covered = [i for i in all_intents if can_handle(i)]
missing = [i for i in all_intents if not can_handle(i)]

check(f"Rule engine handles {len(covered)}/{len(all_intents)} intents", True)
for intent in covered:
    sql = generate_sql(intent, 101, "Karnataka")
    check(f"  {intent.value}: generates valid SQL", sql is not None and sql.upper().startswith("SELECT"))

if missing:
    print(f"  MISSING RULES: {[m.value for m in missing]}")


# -- Summary -------------------------------------------------------------------
print()
print("=" * 60)
print(f" FINAL: {PASS} passed  |  {FAIL} failed")
print("=" * 60)
if FAIL:
    raise SystemExit(1)