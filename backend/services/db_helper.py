import psycopg2
import psycopg2.extras
import re
import logging
from backend.core.config import Config
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data source registry — maps SQL table names to their source descriptor.
# Used by classify_query_source() to annotate query responses for debugging.
# TODO: Verify that hr_payroll_monthly_line and hr_salary_payment_line are
#       populated directly by the Odoo Payroll module (account_payroll).
#       If payroll processing is done in an external system and only synced
#       into these tables, update the source descriptor below accordingly.
# ---------------------------------------------------------------------------
_TABLE_SOURCE_MAP = {
    'hr_payroll_monthly_line':  'Odoo Payroll module → hr_payroll_monthly_line (PostgreSQL: mar_9_26)',
    'hr_salary_payment_line':   'Odoo Payroll module → hr_salary_payment_line (PostgreSQL: mar_9_26)',
    'hr_employee_salary_income':'Odoo Payroll module → hr_employee_salary_income (PostgreSQL: mar_9_26)',
    'hr_employee_bonus':        'Odoo Payroll module → hr_employee_bonus (PostgreSQL: mar_9_26)',
    'hr_holidays':              'Odoo Leave module → hr_holidays (PostgreSQL: mar_9_26)',
    'hr_holidays_status':       'Odoo Leave module → hr_holidays_status (PostgreSQL: mar_9_26)',
    'hr_attendance':            'Odoo Attendance module → hr_attendance (PostgreSQL: mar_9_26)',
    'hr_daily_attendance':      'Odoo Attendance module → hr_daily_attendance (PostgreSQL: mar_9_26)',
    'hr_monthly_attendance':    'Odoo Attendance module → hr_monthly_attendance (PostgreSQL: mar_9_26)',
    'hr_timesheet_sheet_sheet': 'Odoo Timesheet module → hr_timesheet_sheet_sheet (PostgreSQL: mar_9_26)',
    'hr_expense_expense':       'Odoo Expense module → hr_expense_expense (PostgreSQL: mar_9_26)',
    'hr_expense_line':          'Odoo Expense module → hr_expense_line (PostgreSQL: mar_9_26)',
    'hr_employee':              'Odoo HR module → hr_employee (PostgreSQL: mar_9_26)',
}


def classify_query_source(sql):
    """Detect which Odoo module/table a SQL query targets and return a source descriptor.

    Returns a dict: {'tables': [...], 'sources': [...], 'domain': str}
    This is developer/admin-only information — never exposed in employee-facing responses.
    """
    sql_lower = sql.lower()
    matched_tables = [t for t in _TABLE_SOURCE_MAP if t in sql_lower]

    if not matched_tables:
        return {
            'tables': [],
            'sources': ['Unknown — table not in source registry'],
            'domain': 'unknown',
        }

    sources = list(dict.fromkeys(_TABLE_SOURCE_MAP[t] for t in matched_tables))

    # Determine high-level domain for log tagging
    if any(t in matched_tables for t in ('hr_payroll_monthly_line', 'hr_salary_payment_line',
                                          'hr_employee_salary_income', 'hr_employee_bonus')):
        domain = 'payroll'
    elif any(t in matched_tables for t in ('hr_holidays', 'hr_holidays_status')):
        domain = 'leave'
    elif any(t in matched_tables for t in ('hr_attendance', 'hr_daily_attendance', 'hr_monthly_attendance')):
        domain = 'attendance'
    elif 'hr_timesheet_sheet_sheet' in matched_tables:
        domain = 'timesheet'
    elif any(t in matched_tables for t in ('hr_expense_expense', 'hr_expense_line')):
        domain = 'expense'
    else:
        domain = 'hr'

    return {'tables': matched_tables, 'sources': sources, 'domain': domain}

crypt_ctx = CryptContext(['pbkdf2_sha512', 'plaintext'])


def get_connection():
    return psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        connect_timeout=10
    )


def authenticate_user(login, password):
    """Authenticate user against res_users table. Returns user dict or None."""

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, login, password, password_crypt, active "
            "FROM res_users WHERE login = %s AND active = true",
            (login,)
        )
        user = cur.fetchone()
        if not user:
            return None

        # Try password_crypt first (Odoo 8 auth_crypt)
        stored_hash = user.get('password_crypt')
        if stored_hash:
            try:
                if crypt_ctx.verify(password, stored_hash):
                    return {'id': user['id'], 'login': user['login']}
            except Exception:
                pass

        # Fallback: check plaintext password field
        stored_plain = user.get('password')
        if stored_plain and stored_plain == password:
            return {'id': user['id'], 'login': user['login']}

        return None
    finally:
        conn.close()


def get_employee_info(user_id):
    """Get employee info linked to a res_users id via resource_resource."""
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                e.id as employee_id,
                e.name_related as name,
                e.emp_first_name,
                e.emp_last_name,
                e.identification_id as emp_code,
                e.work_email,
                e.work_phone,
                e.mobile_phone,
                e.personal_email_id,
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
                e.designation_id,
                e.department_id,
                e.parent_id,
                e.job_id,
                d.name as department_name,
                des.name as designation_name,
                j.name as job_name,
                mgr.name_related as manager_name
            FROM hr_employee e
            JOIN resource_resource r ON e.resource_id = r.id
            LEFT JOIN hr_department d ON e.department_id = d.id
            LEFT JOIN hr_designation des ON e.designation_id = des.id
            LEFT JOIN hr_job j ON e.job_id = j.id
            LEFT JOIN hr_employee mgr ON e.parent_id = mgr.id
            WHERE r.user_id = %s
            LIMIT 1
        """, (user_id,))
        emp = cur.fetchone()
        if emp:
            return dict(emp)
        return None
    finally:
        conn.close()


def check_is_hr(user_id):
    """Check if user belongs to HR Manager group."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM res_groups_users_rel gur
                JOIN ir_model_data imd ON gur.gid = imd.res_id
                    AND imd.model = 'res.groups'
                WHERE gur.uid = %s
                    AND imd.module = 'hr'
                    AND imd.name IN ('group_hr_manager', 'group_hr_user')
            )
        """, (user_id,))
        return cur.fetchone()[0]
    finally:
        conn.close()


DANGEROUS_KEYWORDS = re.compile(
    r'\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE|GRANT|REVOKE|EXECUTE|EXEC)\b',
    re.IGNORECASE
)


def validate_sql(sql):
    """Validate that SQL is a safe SELECT-only query."""
    cleaned = sql.strip().rstrip(';')
    if not cleaned.upper().startswith('SELECT'):
        return False, "Only SELECT queries are allowed."
    if DANGEROUS_KEYWORDS.search(cleaned):
        return False, "Query contains disallowed keywords."
    if '--' in cleaned or '/*' in cleaned:
        return False, "Comments not allowed in queries."
    return True, "OK"


def execute_safe_query(sql, params=None, limit=50):
    """Execute a validated SELECT query with automatic LIMIT.

    Returns (result_dict, error_string). result_dict includes a 'data_source' key
    with developer-facing provenance info (domain, tables, source descriptors).
    This data_source field must NOT be rendered in employee-facing UI.
    """
    is_valid, msg = validate_sql(sql)
    if not is_valid:
        return None, msg

    cleaned = sql.strip().rstrip(';')
    if 'LIMIT' not in cleaned.upper():
        cleaned += f' LIMIT {limit}'

    # Classify data source before executing — logged for developer/admin visibility
    source_info = classify_query_source(cleaned)
    logger.info(
        '[DATA_SOURCE] domain=%s tables=%s sources=%s',
        source_info['domain'],
        source_info['tables'],
        source_info['sources'],
    )
    if source_info['domain'] == 'payroll':
        logger.info(
            '[PAYROLL] Query targets Odoo Payroll tables: %s. '
            'Data is read-only from PostgreSQL DB %s@%s:%s. '
            'No external payroll API or mock data involved.',
            source_info['tables'],
            'mar_9_26', '192.168.1.52', '5432',
        )

    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(cleaned, params)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        return {
            'columns': columns,
            'rows': [dict(r) for r in rows],
            'count': len(rows),
            'data_source': source_info,   # developer/admin only — strip before employee response
        }, None
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()


HR_SCHEMA = """
=== HR DATABASE SCHEMA (PostgreSQL / Odoo 8.0) ===

-- Employee Master (2156 employees)
hr_employee: id, name_related (full name), emp_first_name, emp_last_name, emp_middle_name,
  identification_id (employee code), department_id->hr_department, designation_id->hr_designation,
  job_id->hr_job, parent_id->hr_employee (manager), doj (date of joining), lwd (last working date),
  gender, marital, birthday, work_email, work_phone, mobile_phone, personal_email_id, personal_mobile,
  current_ctc, grade, payroll_category, emp_state ('active','left','relieving','notice_period','absconded'),
  blood_group, pan_number, place_birth, children, marriage_anniversary,
  tot_exp, tot_relevant_exp, higest_qualification, confirmation_status, confirmation_date,
  resource_id->resource_resource (links to res_users via resource_resource.user_id)

-- Departments (56 depts)
hr_department: id, name, dept_code, dept_category, dept_main_category, manager_id->hr_employee,
  parent_id->hr_department, company_id, target

-- Designations (630)
hr_designation: id, name

-- Job Positions (671)
hr_job: id, name, department_id, company_id, state, no_of_employee, no_of_recruitment

-- Leave Management
hr_holidays_status: id, name (leave type names like 'Casual Leave','Sick Leave','Earned Leave', etc.)
hr_holidays (91349 rows): id, employee_id->hr_employee, holiday_status_id->hr_holidays_status,
  type ('remove'=leave request, 'add'=leave allocation),
  state ('draft','confirm','validate1','validate','refuse','cancel'),
  date_from, date_to, number_of_days_temp (number of days), name (reason/description),
  department_id, manager_id
  -- Leave BALANCE = SUM(number_of_days_temp) WHERE type='add' AND state='validate'
  --              - SUM(number_of_days_temp) WHERE type='remove' AND state='validate'
  -- Filter by employee_id and holiday_status_id for per-type balance

-- Attendance
hr_attendance (4.7M rows): id, employee_id, name (timestamp of punch), action ('sign_in'/'sign_out'),
  punchdate (date), worked_hours, sheet_id
hr_daily_attendance (1.6M rows): id, employee_id, date, login_time, logout_time, worked_hours,
  final_result ('P'=Present,'A'=Absent,'WO'=WeeklyOff,'H'=Holiday,'L'=Leave),
  state, leave_type, monthly_attendance_id, note
hr_monthly_attendance (55683 rows): id, employee_id, date_from, date_to, month,
  total_present, total_absent, total_leave, attendance_days, salary_days,
  total_holiday, total_weeklyoff, total_days, month_days, total_co, total_unpaid_leave

-- Timesheets (70859 rows)
hr_timesheet_sheet_sheet: id, employee_id, user_id, date_from, date_to, state ('draft','confirm','done'),
  department_id, total_attendance, total_difference, project_names, approved_by

-- Payroll
hr_payroll_monthly_line (57666 rows): id, emp_id->hr_employee, emp_code, department_id, designation_id,
  gross_sal_before_tax, gross_sal_after_tax, total_ded, employer_pf, ctc_yearly, d_join,
  bank_name, bank_acc_number, ifsc_code
hr_salary_payment_line (48993 rows): id, emp_id->hr_employee, emp_code, salary, salary_payment_id,
  account_id, partner_id, reconcile, process

-- Expenses (4474 claims)
hr_expense_expense: id, employee_id, name, date, state ('draft','confirm','accepted','done','cancelled'),
  amount, department_id, jmr_ref, note
hr_expense_line: id, expense_id->hr_expense_expense, name, date_value, unit_amount, unit_quantity, description

-- Employee Bonuses (1767)
hr_employee_bonus: id, employee_id, bonus_type, bonus_amount, date, state, period_id,
  department_id, designation_id, month, note

-- Recruitment (22978 applicants)
hr_applicant: id, partner_name, job_id, department_id, stage_id, priority, create_date,
  user_id, date_closed, probability

-- Employee Documents (18132)
hr_employee_document: id, employee_id, name, identification_id, status

-- Helpdesk (39473 tickets)
helpdesk_support_ticket: id, employee_id, emp_code, ticket_no, ref, description, state, priority,
  date_closed, project_id, responsible_employee_id

-- Employee Salary & Income (41472)
hr_employee_salary_income: id (columns vary - stores salary/income history)

-- Leave Encashment
hr_holidays_encashment: id (788 rows), employee_id, state
hr_holidays_encashment_line: id (16509 rows)

-- Employee Insurance (1259)
hr_employee_insurance: id, employee_id
hr_employee_insurance_line: id (2446 rows)

-- Employee Qualifications (5761)
hr_employee_qualification: id, employee_id

-- Employee Relations/Family (6166)
hr_employee_relation: id, employee_id

-- Projects (1277)
project_project: id, name, active, state, analytic_account_id, business_unit_id, project_type

-- Companies (43)
res_company: id, name, partner_id, currency_id

-- Users (1977)
res_users: id, login, partner_id, active, company_id
-- Link: res_users.id -> resource_resource.user_id -> hr_employee.resource_id

-- Document Management System (DMS)
document_directory (278 dirs): id, name, parent_id->document_directory, type, company_id, create_date
  -- Key Policy Directories:
  --   379 = "Policies and Guidelines" (root)
  --   380 = "Human Resource" (11 HR policy files)
  --   381 = "Admin" (1 file)
  --   382 = "Quality Management" (1 file)
  --   383 = "Finance"
  --   452 = "ITIS" (4 files)
  --   453 = "Information Security" (30 files)
ir_attachment (158K records): id, name, datas_fname, file_size, mimetype, res_model, res_id,
  parent_id->document_directory, create_date, create_uid
  -- To list policies: SELECT a.name, a.datas_fname, a.file_size, d.name as directory
  --   FROM ir_attachment a JOIN document_directory d ON a.parent_id = d.id
  --   WHERE d.id IN (379, 380, 381, 382, 383, 452, 453) AND a.file_size > 1000

-- Blog / How-To Guides (12 posts)
blog_post: id, name (title), subtitle, content (HTML with guides on leave, travel, timesheet, etc.)
blog_tag: id, name
"""
