"""
Comprehensive scenario tests for the HRMS chat service.
Tests routing, isolation guard, write-guard, and profile handler.
No live DB required.
"""
from backend.services.db_helper import enforce_employee_isolation
from backend.services.llm_helper import (
    _normalize_query as q,
    _is_write_attempt,
    _is_leave_balance_request,
    _is_latest_payroll_summary_request,
    _is_attendance_request,
    _is_timesheet_request,
    _is_expense_request,
    _is_profile_request,
    resolve_employee_profile,
    _WRITE_REFUSAL,
)

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


# ── Scenario 1: Leave balance ─────────────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 1 — Leave balance routing")
print("=" * 60)
check("my current cl balance?",         _is_leave_balance_request(q("my current cl balance?")))
check("how many sl do I have left?",    _is_leave_balance_request(q("how many sl do I have left?")))
check("el balance",                     _is_leave_balance_request(q("el balance")))
check("check my leave balance",         _is_leave_balance_request(q("check my leave balance")))
check("tell me my cl",                  _is_leave_balance_request(q("tell me my cl")))
check("how many pl days remaining",     _is_leave_balance_request(q("how many pl days remaining")))
check("casual leave balance",           _is_leave_balance_request(q("casual leave balance")))
check("sick leave days left",           _is_leave_balance_request(q("sick leave days left")))
check("compoff balance",                _is_leave_balance_request(q("compoff balance")))
check("NOT: weather today",             _is_leave_balance_request(q("what is the weather today")), False)
check("NOT: leave application status",  _is_leave_balance_request(q("leave application status")), False)

# ── Scenario 2: Payroll ───────────────────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 2 — Payroll routing")
print("=" * 60)
check("my salary",                      _is_latest_payroll_summary_request(q("my salary")))
check("my ctc",                         _is_latest_payroll_summary_request(q("my ctc")))
check("my pay",                         _is_latest_payroll_summary_request(q("my pay")))
check("my income",                      _is_latest_payroll_summary_request(q("my income")))
check("my payslip",                     _is_latest_payroll_summary_request(q("my payslip")))
check("what is my latest payslip",      _is_latest_payroll_summary_request(q("what is my latest payslip")))
check("show my current salary",         _is_latest_payroll_summary_request(q("show my current salary")))
check("last month salary",              _is_latest_payroll_summary_request(q("last month salary")))
check("my net pay",                     _is_latest_payroll_summary_request(q("my net pay")))
check("my gross pay",                   _is_latest_payroll_summary_request(q("my gross pay")))
check("NOT: my leave",                  _is_latest_payroll_summary_request(q("my leave")), False)
check("NOT: my profile",                _is_latest_payroll_summary_request(q("my profile")), False)

# ── Scenario 3: Attendance (narrowed) ────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 3 — Attendance routing (narrowed — no false-positives)")
print("=" * 60)
check("what is my attendance this month", _is_attendance_request(q("what is my attendance this month")))
check("show my attendance",             _is_attendance_request(q("show my attendance")))
check("attendance report",              _is_attendance_request(q("attendance report")))
check("how many days present this month", _is_attendance_request(q("how many days present this month")))
check("worked hours today",             _is_attendance_request(q("worked hours today")))
check("punch in time today",            _is_attendance_request(q("punch in time today")))
check("NOT: present at the meeting",    _is_attendance_request(q("I was present at the meeting today")), False)
check("NOT: mark me absent",            _is_attendance_request(q("mark me absent")), False)
check("NOT: absent today tell manager", _is_attendance_request(q("I am absent today tell my manager")), False)
check("NOT: my salary",                 _is_attendance_request(q("my salary")), False)

# ── Scenario 4: Timesheet ─────────────────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 4 — Timesheet routing")
print("=" * 60)
check("my timesheet",                   _is_timesheet_request(q("my timesheet")))
check("show my hours",                  _is_timesheet_request(q("show my hours")))
check("my logged hours",                _is_timesheet_request(q("my logged hours")))
check("project hours this week",        _is_timesheet_request(q("project hours this week")))
check("how many hours did I log",       _is_timesheet_request(q("how many hours did I log")))
check("NOT: cl balance",                _is_timesheet_request(q("cl balance")), False)
check("NOT: my expenses",               _is_timesheet_request(q("my expenses")), False)

# ── Scenario 5: Expense ───────────────────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 5 — Expense routing")
print("=" * 60)
check("my expenses",                    _is_expense_request(q("my expenses")))
check("show my claims",                 _is_expense_request(q("show my claims")))
check("travel claim status",            _is_expense_request(q("travel claim status")))
check("reimbursement status",           _is_expense_request(q("reimbursement status")))
check("expense claim",                  _is_expense_request(q("expense claim")))
check("my pending reimbursements",      _is_expense_request(q("my pending reimbursements")))
check("NOT: my salary",                 _is_expense_request(q("my salary")), False)
check("NOT: my timesheet",              _is_expense_request(q("my timesheet")), False)

# ── Scenario 6: Profile ───────────────────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 6 — Profile routing")
print("=" * 60)
check("my profile",                     _is_profile_request(q("my profile")))
check("my details",                     _is_profile_request(q("my details")))
check("who is my manager",              _is_profile_request(q("who is my manager")))
check("my date of joining",             _is_profile_request(q("my date of joining")))
check("what is my department",          _is_profile_request(q("what is my department")))
check("my designation",                 _is_profile_request(q("my designation")))
check("my doj",                         _is_profile_request(q("my doj")))
check("about me",                       _is_profile_request(q("about me")))
check("my employee info",               _is_profile_request(q("my employee info")))
check("NOT: my salary",                 _is_profile_request(q("my salary")), False)
check("NOT: my expenses",               _is_profile_request(q("my expenses")), False)

# ── Scenario 7: Write-attempt guard ──────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 7 — Write-attempt guard")
print("=" * 60)
check("delete my attendance record",    _is_write_attempt(q("delete my attendance record")))
check("update my salary",               _is_write_attempt(q("update my salary")))
check("drop attendance table",          _is_write_attempt(q("drop attendance table")))
check("modify my leave record",         _is_write_attempt(q("modify my leave record")))
check("change my payroll record",       _is_write_attempt(q("change my payroll record")))
check("NOT: what is my attendance",     _is_write_attempt(q("what is my attendance this month")), False)
check("NOT: how many cl days",          _is_write_attempt(q("how many cl days do I have")), False)
check("NOT: show my expenses",          _is_write_attempt(q("show my expenses")), False)
check("NOT: my salary",                 _is_write_attempt(q("my salary")), False)
check("NOT: my leave balance",          _is_write_attempt(q("my current cl balance")), False)

# ── Scenario 8: SQL isolation guard ──────────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 8 — SQL isolation guard")
print("=" * 60)
emp_id = 101
emp_code = "JMR0042"

isolation_cases = [
    (
        "Already filtered — pass through unchanged",
        "SELECT * FROM hr_holidays WHERE employee_id = 101 AND state = 'validate'",
        True,
        "employee_id = 101",
    ),
    (
        "Missing filter — inject before ORDER BY",
        "SELECT * FROM hr_holidays WHERE state = 'validate' ORDER BY date_from",
        True,
        "AND employee_id = 101 ORDER BY",
    ),
    (
        "No WHERE clause — add WHERE employee_id",
        "SELECT date FROM hr_daily_attendance LIMIT 30",
        True,
        "WHERE employee_id = 101 LIMIT",
    ),
    (
        "Payroll table — uses emp_id column not employee_id",
        "SELECT gross_sal_before_tax FROM hr_payroll_monthly_line LIMIT 1",
        True,
        "WHERE emp_id = 101 LIMIT",
    ),
    (
        "Subquery — must block, not attempt injection",
        "SELECT * FROM (SELECT * FROM hr_holidays) h",
        False,
        None,
    ),
    (
        "Non-personal table — pass unchanged",
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
        "Multiple personal tables — inject for first personal table found",
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

# ── Scenario 9: Profile handler (no DB) ──────────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 9 — Employee profile handler (no DB needed)")
print("=" * 60)
mock_emp = {
    "employee_id": 101,
    "name": "Hari Kumar",
    "emp_code": "JMR0042",
    "department_name": "Engineering",
    "designation_name": "Senior Developer",
    "manager_name": "Ramesh B",
    "doj": "2021-06-01",
    "work_email": "hari@jmr.com",
    "work_phone": "+91-9876543210",
    "mobile_phone": None,
}
text, sql_used, _, error = resolve_employee_profile(mock_emp)
check("No error returned",   error is None)
check("No SQL query needed", sql_used is None)
check("Shows full name",     "Hari Kumar" in text)
check("Shows department",    "Engineering" in text)
check("Shows manager",       "Ramesh B" in text)
check("Shows DOJ",           "2021-06-01" in text)
check("Shows employee code", "JMR0042" in text)
print("  Profile preview:")
for line in text.splitlines():
    print("    " + line)

# ── Scenario 10: Write-refusal message quality ────────────────────────────────
print()
print("=" * 60)
print(" SCENARIO 10 — Write-refusal message quality")
print("=" * 60)
check("Mentions read-only",          "read-only" in _WRITE_REFUSAL)
check("Mentions contact HR",         "contact HR" in _WRITE_REFUSAL)
check("No raw exceptions in message","Exception" not in _WRITE_REFUSAL)
check("No traceback in message",     "Traceback" not in _WRITE_REFUSAL)
print("  Refusal text:")
print("   ", _WRITE_REFUSAL)

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print(f" FINAL: {PASS} passed  |  {FAIL} failed")
print("=" * 60)
if FAIL:
    raise SystemExit(1)
