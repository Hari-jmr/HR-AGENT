"""
Database helper — connection, auth, employee lookup, query safety,
and employee-isolation enforcement.

DB: PostgreSQL 192.168.1.52:5432  db=mar_9_26  user=user1
Schema: Odoo 8.0 HRMS
"""

import re
import logging

import psycopg2
import psycopg2.extras
from passlib.context import CryptContext

from backend.core.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HR schema description — injected into LLM prompts (no live DB needed)
# ---------------------------------------------------------------------------

HR_SCHEMA = """\
PostgreSQL database: mar_9_26 (Odoo 8 HRMS)  host=192.168.1.52

=== EMPLOYEE ===
hr_employee(id, name_related AS name, identification_id AS emp_code,
  work_email, work_phone, mobile_phone,
  department_id->hr_department, designation_id->hr_designation,
  parent_id->hr_employee (manager), doj, lwd, emp_state,
  grade, current_ctc, gender, marital, birthday, blood_group,
  pan_number, resource_id->resource_resource)
hr_department(id, name, dept_code, manager_id->hr_employee)
hr_designation(id, name)
-- res_users.id -> resource_resource.user_id -> hr_employee.resource_id

=== LEAVE ===
hr_holidays_status(id, name)
  -- leave type names: 'Casual Leave','Sick Leave','Earned Leave','Privilege Leave',
  --   'Optional Holiday','Comp Off','Emergency Leave','Maternity Leave',
  --   'Paternity Leave','Birthday Leave','Education Leave','National Holiday', etc.
hr_holidays(id, employee_id, holiday_status_id->hr_holidays_status,
  type, state, number_of_days_temp, date_from, date_to, name)
  -- type:  'add' = allocation,  'remove' = leave taken
  -- state: 'validate' = approved; also draft/confirm/validate1/refuse/cancel
  -- LEAVE BALANCE per type =
  --   SUM(number_of_days_temp WHERE type='add'    AND state='validate')
  -- - SUM(number_of_days_temp WHERE type='remove' AND state='validate')
  -- Always filter: employee_id = <current employee>
  -- Use ILIKE for matching hr_holidays_status.name

=== ATTENDANCE ===
hr_daily_attendance(id, employee_id, date, login_time, logout_time,
  worked_hours, final_result, state, leave_type)
  -- final_result: 'P'=Present 'A'=Absent 'WO'=Weekly Off 'H'=Holiday 'L'=Leave
hr_monthly_attendance(id, employee_id, month, date_from, date_to,
  total_present, total_absent, total_leave, total_weeklyoff,
  total_holiday, attendance_days, salary_days, total_days)
hr_attendance(id, employee_id, name AS punch_timestamp,
  action ('sign_in'/'sign_out'), punchdate, worked_hours)

=== PAYROLL  (IMPORTANT: filter column is emp_id, not employee_id) ===
hr_payroll_monthly_line(id, emp_id->hr_employee, emp_code,
  create_date,
  gross_sal_before_tax, gross_sal_after_tax,
  ctc_yearly, ctc_basic, ctc_hra, ctc_special_allowance,
  total_ded, tds, prof_tax, ewf_ded, employer_pf,
  d_join, bank_name, bank_acc_number, ifsc_code)
  -- NO year/month columns — use create_date for date filtering
  -- current_ctc on hr_employee is always 0 — use ctc_yearly here instead
hr_salary_payment_line(id, emp_id->hr_employee, emp_code,
  salary, payment_date, salary_payment_id)
hr_employee_salary_income(id, employee_id, year, month,
  component_name, amount)
hr_employee_bonus(id, employee_id, bonus_type, bonus_amount,
  date, state, month, note)

=== TIMESHEET ===
hr_timesheet_sheet_sheet(id, employee_id, user_id,
  date_from, date_to, state ('draft'/'confirm'/'done'),
  total_attendance, total_difference, project_names, approved_by)

=== EXPENSES ===
hr_expense_expense(id, employee_id, name, date,
  state ('draft'/'confirm'/'accepted'/'done'/'cancelled'),
  amount, department_id, jmr_ref, note)
hr_expense_line(id, expense_id->hr_expense_expense,
  name, date_value, unit_amount, unit_quantity, description)

=== HELPDESK ===
helpdesk_support_ticket(id, employee_id, emp_code, ticket_no,
  ref, description, state, priority, date_closed, project_id)

=== PROJECTS ===
project_project(id, name, active, state, analytic_account_id)

=== HOLIDAYS / COMPANY CALENDAR ===
holiday_calendar(id, name)
  -- location names: 'Karnataka','Kerala','Maharashtra','Tamil Nadu','Mumbai', etc.
holiday_calendar_year(id, name AS year, calendar_id->holiday_calendar)
holiday_calendar_line(id, name, date, year TEXT, restricted_holiday BOOL,
  calendar_year_id->holiday_calendar_year)
  -- restricted_holiday FALSE = mandatory public holiday (all employees)
  -- restricted_holiday TRUE  = optional/restricted holiday (employee's choice)
optional_holiday_line(id, name, date, holiday_year_id->holiday_calendar_year)
  -- specific optional holidays listed per location/year
"""

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

crypt_ctx = CryptContext(['pbkdf2_sha512', 'plaintext'])


def get_connection():
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        connect_timeout=10,
    )


# ---------------------------------------------------------------------------
# Auth & employee lookup
# ---------------------------------------------------------------------------

def authenticate_user(login: str, password: str):
    """Return {'id': ..., 'login': ...} on success, None on failure."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, login, password, password_crypt, active "
            "FROM res_users WHERE login = %s AND active = true",
            (login,),
        )
        user = cur.fetchone()
        if not user:
            return None

        stored_hash = user.get('password_crypt')
        if stored_hash:
            try:
                if crypt_ctx.verify(password, stored_hash):
                    return {'id': user['id'], 'login': user['login']}
            except Exception:
                pass

        stored_plain = user.get('password')
        if stored_plain and stored_plain == password:
            return {'id': user['id'], 'login': user['login']}

        return None
    finally:
        conn.close()


def get_employee_info(user_id: int):
    """Return employee dict linked to a res_users id, or None."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT
                e.id                        AS employee_id,
                e.name_related              AS name,
                e.emp_first_name,
                e.emp_last_name,
                e.identification_id         AS emp_code,
                e.work_email,
                e.work_phone,
                e.mobile_phone,
                e.gender,
                e.birthday,
                e.doj,
                e.lwd,
                e.marital,
                e.current_ctc,
                e.grade,
                e.emp_state,
                e.pan_number,
                e.blood_group,
                e.work_location,
                e.designation_id,
                e.department_id,
                e.parent_id,
                e.job_id,
                d.name                      AS department_name,
                des.name                    AS designation_name,
                j.name                      AS job_name,
                mgr.name_related            AS manager_name
            FROM hr_employee e
            JOIN resource_resource r ON e.resource_id = r.id
            LEFT JOIN hr_department  d   ON e.department_id  = d.id
            LEFT JOIN hr_designation des ON e.designation_id = des.id
            LEFT JOIN hr_job         j   ON e.job_id         = j.id
            LEFT JOIN hr_employee    mgr ON e.parent_id      = mgr.id
            WHERE r.user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        emp = cur.fetchone()
        return dict(emp) if emp else None
    finally:
        conn.close()


def check_is_hr(user_id: int) -> bool:
    """Return True if user belongs to hr_manager / hr_user group."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM res_groups_users_rel gur
                JOIN ir_model_data imd
                  ON gur.gid = imd.res_id AND imd.model = 'res.groups'
                WHERE gur.uid = %s
                  AND imd.module = 'hr'
                  AND imd.name IN ('group_hr_manager', 'group_hr_user')
            )
            """,
            (user_id,),
        )
        return bool(cur.fetchone()[0])
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SQL safety validation
# ---------------------------------------------------------------------------

_DANGEROUS_KW = re.compile(
    r'\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE|GRANT|REVOKE|EXECUTE|EXEC)\b',
    re.IGNORECASE,
)


def validate_sql(sql: str) -> tuple[bool, str]:
    """Return (True, 'OK') for safe SELECT queries, (False, reason) otherwise."""
    cleaned = sql.strip().rstrip(';')
    if not cleaned.upper().startswith('SELECT'):
        return False, 'Only SELECT queries are allowed.'
    if _DANGEROUS_KW.search(cleaned):
        return False, 'Query contains disallowed keywords.'
    if '--' in cleaned or '/*' in cleaned:
        return False, 'SQL comments are not allowed.'
    return True, 'OK'


# ---------------------------------------------------------------------------
# Employee isolation enforcement
# ---------------------------------------------------------------------------
# Mapping: table → (primary_filter_col, optional_code_col)
_PERSONAL_TABLES: dict[str, tuple[str, str | None]] = {
    'hr_holidays':               ('employee_id', None),
    'hr_daily_attendance':       ('employee_id', None),
    'hr_attendance':             ('employee_id', None),
    'hr_monthly_attendance':     ('employee_id', None),
    'hr_timesheet_sheet_sheet':  ('employee_id', None),
    'hr_expense_expense':        ('employee_id', None),
    'hr_employee_bonus':         ('employee_id', None),
    'hr_employee_salary_income': ('employee_id', None),
    'hr_payroll_monthly_line':   ('emp_id', 'emp_code'),
    'hr_salary_payment_line':    ('emp_id', 'emp_code'),
    'helpdesk_support_ticket':   ('employee_id', 'emp_code'),
}

_WHERE_RE = re.compile(r'\bWHERE\b', re.IGNORECASE)
_CLAUSE_RE = re.compile(
    r'\b(ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|UNION\s+ALL|UNION|INTERSECT|EXCEPT)\b',
    re.IGNORECASE,
)
_TABLE_RE_CACHE: dict[str, re.Pattern] = {}


def _table_in_sql(table: str, sql_lower: str) -> bool:
    if table not in _TABLE_RE_CACHE:
        _TABLE_RE_CACHE[table] = re.compile(r'\b' + re.escape(table) + r'\b')
    return bool(_TABLE_RE_CACHE[table].search(sql_lower))


def _inject_condition(sql: str, condition: str) -> str:
    sql = sql.rstrip(';').rstrip()
    m = _CLAUSE_RE.search(sql)
    cut = m.start() if m else len(sql)
    while cut > 0 and sql[cut - 1] == ' ':
        cut -= 1
    tail = (' ' + sql[m.start():]) if m else ''
    if _WHERE_RE.search(sql[:cut]):
        return sql[:cut] + f' AND {condition}' + tail
    return sql[:cut] + f' WHERE {condition}' + tail


def enforce_employee_isolation(
    sql: str, employee_id: int, emp_code: str
) -> tuple[str, str | None]:
    """
    Guarantee every personal-table query is scoped to employee_id.

    Returns (safe_sql, None) — filter injected or already present.
    Returns (sql,  reason)   — blocked when injection is unsafe (subquery/CTE).
    """
    sql_lower = sql.lower()
    emp_id_str = str(employee_id)
    emp_code_lower = (emp_code or '').lower()

    is_complex = ('(select' in sql_lower) or sql_lower.lstrip().startswith('with ')
    modified = sql

    for table, (primary_col, code_col) in _PERSONAL_TABLES.items():
        if not _table_in_sql(table, sql_lower):
            continue

        already = (
            f'{primary_col} = {emp_id_str}' in sql_lower
            or f'{primary_col}={emp_id_str}' in sql_lower
        )
        if not already and code_col and emp_code_lower:
            already = f"'{emp_code_lower}'" in sql_lower

        if already:
            continue

        if is_complex:
            logger.warning(
                '[ISOLATION_BLOCK] table=%s emp_id=%s sql=%r', table, employee_id, sql
            )
            return sql, (
                f'Isolation filter missing on {table} in a complex query — blocked for safety.'
            )

        condition = f'{primary_col} = {employee_id}'
        logger.info('[ISOLATION_INJECT] %r into sql=%r', condition, modified)
        modified = _inject_condition(modified, condition)
        sql_lower = modified.lower()

    return modified, None


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

def execute_safe_query(
    sql: str, params=None, limit: int = 50
) -> tuple[dict | None, str | None]:
    """
    Run a validated SELECT query.
    Returns (result_dict, None) or (None, error_string).
    result_dict keys: columns, rows, count
    """
    valid, msg = validate_sql(sql)
    if not valid:
        return None, msg

    cleaned = sql.strip().rstrip(';')
    if 'LIMIT' not in cleaned.upper():
        cleaned += f' LIMIT {limit}'

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(cleaned, params)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        return {'columns': columns, 'rows': [dict(r) for r in rows], 'count': len(rows)}, None
    except Exception as exc:
        logger.error('[QUERY_ERROR] %s  sql=%r', exc, cleaned)
        return None, str(exc)
    finally:
        conn.close()
