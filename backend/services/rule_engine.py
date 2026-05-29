import logging
from typing import Optional

from backend.services.intent_classifier import HRIntent

logger = logging.getLogger(__name__)


_LEAVE_BALANCE_SQL = """
SELECT hs.name AS leave_type,
       COALESCE(SUM(CASE WHEN h.type='add'    AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS allocated,
       COALESCE(SUM(CASE WHEN h.type='remove' AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS taken,
       COALESCE(SUM(CASE WHEN h.type='add'    AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0)
     - COALESCE(SUM(CASE WHEN h.type='remove' AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS balance
FROM hr_holidays h
JOIN hr_holidays_status hs ON hs.id = h.holiday_status_id
WHERE h.employee_id = {employee_id}
GROUP BY hs.name
ORDER BY hs.name
"""

_LEAVE_HISTORY_SQL = """
SELECT hs.name AS leave_type, h.number_of_days_temp AS days, h.date_from, h.date_to, h.state, h.name AS reason
FROM hr_holidays h
JOIN hr_holidays_status hs ON hs.id = h.holiday_status_id
WHERE h.employee_id = {employee_id} AND h.type = 'remove'
ORDER BY h.date_from DESC
"""

_PROFILE_SQL = """
SELECT e.name_related AS name, e.identification_id AS emp_code, e.work_email, e.work_phone,
       e.mobile_phone, e.doj, e.lwd, e.emp_state, e.grade, e.gender, e.birthday,
       d.name AS department, des.name AS designation
FROM hr_employee e
LEFT JOIN hr_department d ON e.department_id = d.id
LEFT JOIN hr_designation des ON e.designation_id = des.id
WHERE e.id = {employee_id}
"""

_MANAGER_SQL = """
SELECT mgr.name_related AS manager_name
FROM hr_employee e
LEFT JOIN hr_employee mgr ON e.parent_id = mgr.id
WHERE e.id = {employee_id}
"""

_DEPARTMENT_SQL = """
SELECT d.name AS department_name, d.dept_code
FROM hr_employee e
JOIN hr_department d ON e.department_id = d.id
WHERE e.id = {employee_id}
"""

_JOINING_DATE_SQL = """
SELECT e.doj, e.lwd, e.emp_state
FROM hr_employee e
WHERE e.id = {employee_id}
"""

_CTC_SQL = """
SELECT ctc_yearly, ctc_basic, ctc_hra, ctc_special_allowance
FROM hr_payroll_monthly_line
WHERE emp_id = {employee_id}
ORDER BY id DESC LIMIT 1
"""

_SALARY_SQL = """
SELECT gross_sal_before_tax, gross_sal_after_tax, ctc_yearly, ctc_basic, ctc_hra,
       ctc_special_allowance, total_ded, tds, prof_tax, bank_name
FROM hr_payroll_monthly_line
WHERE emp_id = {employee_id}
ORDER BY id DESC LIMIT 1
"""

_SALARY_PAYMENT_SQL = """
SELECT salary, create_date AS payment_date
FROM hr_salary_payment_line
WHERE emp_id = {employee_id}
ORDER BY create_date DESC LIMIT 5
"""

_SALARY_COMPONENTS_SQL = """
SELECT
    ctc_basic AS basic_salary,
    ctc_hra AS hra,
    ctc_special_allowance AS special_allowance,
    ctc_pf AS pf,
    gross_sal_before_tax,
    gross_sal_after_tax,
    total_ded,
    tds,
    prof_tax,
    ewf_ded
FROM hr_payroll_monthly_line
WHERE emp_id = {employee_id}
ORDER BY id DESC LIMIT 1
"""

_ATTENDANCE_MONTHLY_SQL = """
SELECT month, year, total_present, total_absent, total_leave, total_weeklyoff, total_holiday,
       attendance_days, salary_days, total_days, date_from, date_to
FROM hr_monthly_attendance
WHERE employee_id = {employee_id}
ORDER BY date_from DESC NULLS LAST
LIMIT 1
"""

_BONUS_SQL = """
SELECT bonus_type, bonus_amount, date, state, note
FROM hr_employee_bonus
WHERE employee_id = {employee_id}
ORDER BY date DESC
"""

_TIMESHEET_SQL = """
SELECT date_from, date_to, state, total_attendance, project_names
FROM hr_timesheet_sheet_sheet
WHERE employee_id = {employee_id}
ORDER BY date_from DESC LIMIT 5
"""

_EXPENSE_SQL = """
SELECT name, date, state, amount
FROM hr_expense_expense
WHERE employee_id = {employee_id}
ORDER BY date DESC LIMIT 10
"""

_HELPDESK_SQL = """
SELECT ticket_no, description, state, priority, date_closed
FROM helpdesk_support_ticket
WHERE employee_id = {employee_id}
ORDER BY id DESC LIMIT 10
"""

_PROJECTS_SQL = """
SELECT aaa.name AS project_name, pp.state, pp.active
FROM project_project pp
JOIN account_analytic_account aaa ON pp.analytic_account_id = aaa.id
WHERE pp.active = TRUE
ORDER BY aaa.name
LIMIT 20
"""

_HOLIDAYS_SQL = """
SELECT name, date, holiday_type FROM (
    SELECT hcl.name, hcl.date, 'Public Holiday' AS holiday_type
    FROM holiday_calendar_line hcl
    JOIN holiday_leave_calendar hlc ON hlc.holiday_line_id = hcl.id
    JOIN holiday_calendar hc ON hlc.holiday_id = hc.id
    WHERE hc.name = '{holiday_location}' AND hcl.date >= CURRENT_DATE
    UNION ALL
    SELECT ohl.name, ohl.date, 'Optional Holiday' AS holiday_type
    FROM optional_holiday_line ohl
    JOIN holiday_calendar_year hcy ON ohl.holiday_year_id = hcy.id
    JOIN holiday_calendar hc ON hcy.calendar_id = hc.id
    WHERE hc.name = '{holiday_location}' AND ohl.date >= CURRENT_DATE
) holidays
ORDER BY date LIMIT 30
"""

_PAYROLL_SQL = """
SELECT gross_sal_before_tax, gross_sal_after_tax, ctc_yearly, total_ded, tds, prof_tax
FROM hr_payroll_monthly_line
WHERE emp_id = {employee_id}
ORDER BY id DESC LIMIT 3
"""


_RULES: dict[HRIntent, str] = {
    HRIntent.LEAVE_BALANCE: _LEAVE_BALANCE_SQL,
    HRIntent.LEAVE_HISTORY: _LEAVE_HISTORY_SQL,
    HRIntent.PROFILE: _PROFILE_SQL,
    HRIntent.MANAGER: _MANAGER_SQL,
    HRIntent.DEPARTMENT: _DEPARTMENT_SQL,
    HRIntent.JOINING_DATE: _JOINING_DATE_SQL,
    HRIntent.CTC: _CTC_SQL,
    HRIntent.SALARY: _SALARY_SQL,
    HRIntent.PAYSLIP: _SALARY_SQL,
    HRIntent.SALARY_PAYMENT: _SALARY_PAYMENT_SQL,
    HRIntent.SALARY_COMPONENTS: _SALARY_COMPONENTS_SQL,
    HRIntent.ATTENDANCE: _ATTENDANCE_MONTHLY_SQL,
    HRIntent.BONUS: _BONUS_SQL,
    HRIntent.TIMESHEET: _TIMESHEET_SQL,
    HRIntent.EXPENSE: _EXPENSE_SQL,
    HRIntent.CLAIM: _EXPENSE_SQL,
    HRIntent.HELPDESK: _HELPDESK_SQL,
    HRIntent.TICKET: _HELPDESK_SQL,
    HRIntent.PROJECTS: _PROJECTS_SQL,
    HRIntent.HOLIDAY: _HOLIDAYS_SQL,
    HRIntent.PAYROLL: _PAYROLL_SQL,
}


def can_handle(intent: HRIntent) -> bool:
    return intent in _RULES


def generate_sql(
    intent: HRIntent,
    employee_id: int,
    holiday_location: str = 'Karnataka',
) -> Optional[str]:
    template = _RULES.get(intent)
    if not template:
        return None
    sql = template.format(employee_id=employee_id, holiday_location=holiday_location)
    return sql.strip()
