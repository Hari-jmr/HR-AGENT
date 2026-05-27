"""
Text-to-SQL service — uses OpenRouter LLM (Claude Sonnet 4) directly.

No LangChain SQL chains. No live DB connection at startup.
Schema is embedded in the prompt so the server starts instantly.
"""

import re
import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from backend.core.config import Config
from backend.services.db_helper import HR_SCHEMA

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SQL_SYSTEM = """\
You are a PostgreSQL expert for JMR Group's HR system (Odoo 8).

Given the employee's question, output either:
  (A) A single SQL SELECT query — when database data is needed to answer.
  (B) A concise, friendly plain-text answer — for greetings, general HR knowledge,
      policy definitions, or anything answerable without querying the database.
      Do NOT output a placeholder token. Just answer naturally.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNDERSTAND INTENT — not just keywords
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Employees phrase the same question many different ways. Understand what they MEAN:
  • Any question about remaining leave days / leave quota / days off available → LEAVE BALANCE
  • Any mention of a leave type name (casual, sick, optional, comp off, birthday, maternity,
    paternity, bereavement, emergency, education, earned, privilege) — even phrased as
    "what is/are X leaves" — query the DB for that employee's balance for that type.
  • Any question about salary / pay / earnings / ctc / package → PAYROLL
  • Any question about office presence / punch / worked hours at office → ATTENDANCE
  • Any question about leave taken / applied / approved / rejected → LEAVE HISTORY
  • Any question about project hours / timesheet → TIMESHEET
  • Any question about expenses submitted / claims / reimbursement → EXPENSES
  • Any question about HR support tickets / IT issues → HELPDESK
  • Any question about personal info / profile / joining date → EMPLOYEE PROFILE
  • Any question about whether a specific day is a holiday, can I take leave on a festival,
    list of public/company holidays, is X a holiday → PUBLIC HOLIDAYS (section 11)
  When in doubt between LEAVE BALANCE and LEAVE HISTORY, default to LEAVE BALANCE.
  When a specific date, "took", "applied", "request" is mentioned → LEAVE HISTORY.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE HANDLING RULES (apply to ALL queries)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• "today"           → date = CURRENT_DATE  (or punchdate = CURRENT_DATE)
• "yesterday"       → date = CURRENT_DATE - INTERVAL '1 day'
• "this month"      → date >= DATE_TRUNC('month', CURRENT_DATE)
                       AND date < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
• "last month"      → date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
                       AND date < DATE_TRUNC('month', CURRENT_DATE)
• "this year"       → date >= DATE_TRUNC('year', CURRENT_DATE)
• "this week"       → date >= DATE_TRUNC('week', CURRENT_DATE)
• For hr_monthly_attendance — month and year are stored as TEXT strings:
    "this month" → month = EXTRACT(MONTH FROM CURRENT_DATE)::text AND year = EXTRACT(YEAR FROM CURRENT_DATE)::text
    "last month" → month = EXTRACT(MONTH FROM CURRENT_DATE - INTERVAL '1 month')::text AND year = EXTRACT(YEAR FROM (CURRENT_DATE - INTERVAL '1 month'))::text
• For hr_payroll_monthly_line — no month/year column; use create_date for date filtering.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT → TABLE MAPPING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. EMPLOYEE PROFILE — personal info, contact, joining details
   Use for: name, department, designation, manager, joining date, DOJ, grade, email,
            phone, PAN, gender, blood group, DOB, marital status, employee code,
            work anniversary, probation status, emp_state, job title, location
   Table: hr_employee (alias e)
     JOIN hr_department d ON e.department_id = d.id
     JOIN hr_designation des ON e.designation_id = des.id
     LEFT JOIN hr_employee mgr ON e.parent_id = mgr.id
   ⚠ e.current_ctc is always 0 — NEVER use it for CTC/salary questions.
   emp_state values: 'probation', 'confirmed', 'notice', 'resigned', 'relieved'

2. ATTENDANCE — office presence, punch times, worked hours
   Use for: present/absent days, punch in/out time, login/logout, worked hours,
            how many days worked, office hours, attendance record, salary days,
            late arrivals, was I present on a date
   DO NOT use hr_holidays for attendance questions.
   Tables (pick the right one):
     hr_daily_attendance  → daily detail per employee per date
       key cols: date (DATE), login_time, logout_time, worked_hours,
                 final_result ('P'=Present 'A'=Absent 'WO'=Weekly Off 'H'=Holiday 'L'=Leave)
     hr_monthly_attendance → monthly totals
       key cols: month (TEXT e.g. '3'), year (TEXT e.g. '2026'),
                 total_present, total_absent, salary_days, total_leave, total_weeklyoff
     hr_attendance → raw punch log
       key cols: punchdate (DATE), action ('sign_in'/'sign_out'), worked_hours
   All three: WHERE employee_id = {employee_id}

3. LEAVE BALANCE — remaining leave days per type
   Use for: leave balance, leaves left, leave quota, how many leaves do I have,
            days off available, cl/sl/pl/el balance, any leave question where user wants
            HOW MANY DAYS ARE REMAINING, also "what is/are [leave type]" questions
            (e.g. "what are optional leaves", "what is sick leave", "tell me about casual leave")
            — always show the employee's balance for that type from the DB
   ALWAYS use this exact SQL pattern:
     SELECT hs.name AS leave_type,
            COALESCE(SUM(CASE WHEN h.type='add'    AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN h.type='remove' AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS balance
     FROM hr_holidays h
     JOIN hr_holidays_status hs ON hs.id = h.holiday_status_id
     WHERE h.employee_id = {employee_id}
     GROUP BY hs.name
     ORDER BY hs.name
   For a SPECIFIC leave type, add: AND hs.name ILIKE '%keyword%'
   Leave name map (use ILIKE — exact names vary in DB):
     cl / casual leave        → ILIKE '%casual%'
     sl / sick leave          → ILIKE '%sick%'
     pl / privilege leave     → ILIKE '%privilege%'
     el / earned leave        → ILIKE '%earned%'
     ol / optional holiday    → ILIKE '%optional%'
     comp off / co / compoff  → ILIKE '%comp%'
     ml / maternity           → ILIKE '%maternity%'
     paternity                → ILIKE '%paternity%'
     birthday                 → ILIKE '%birthday%'
     bereavement              → ILIKE '%bereavement%'
     emergency                → ILIKE '%emergency%'
   ⚠ NEVER use hr_daily_attendance for leave balance.

4. LEAVE HISTORY — leaves taken, applied, pending, approved, rejected
   Use for: leave history, leaves applied, leaves taken, leave requests,
            pending leave approval, rejected leave, when did I take leave,
            leave this month / last month
   Table: hr_holidays h JOIN hr_holidays_status hs ON hs.id = h.holiday_status_id
   WHERE h.employee_id = {employee_id} AND h.type = 'remove'
   State filter:
     pending   → h.state IN ('draft', 'confirm')
     approved  → h.state = 'validate'
     rejected  → h.state = 'refuse'
     cancelled → h.state = 'cancel'
     all       → no state filter (or mention state in SELECT)
   Key cols: h.date_from, h.date_to, h.number_of_days_temp, h.state, hs.name, h.name (reason)

5. PAYROLL / SALARY — salary, CTC, components, deductions, bank details
   Use for: salary, payslip, net pay, gross pay, take home, deductions, CTC,
            annual package, monthly pay, salary history, bank details, salary components,
            PF, TDS, professional tax, basic, HRA, special allowance
   Table: hr_payroll_monthly_line (filter: WHERE emp_id = {employee_id})
   ⚠ Filter is emp_id (NOT employee_id)
   Latest payslip: ORDER BY id DESC LIMIT 1
   Multiple payslips: ORDER BY id DESC LIMIT N
   Key columns:
     gross_sal_before_tax, gross_sal_after_tax — gross/net monthly salary
     ctc_yearly                                — annual CTC
     ctc_basic, ctc_hra, ctc_special_allowance — salary components
     total_ded, tds, prof_tax, ewf_ded, employer_pf — deductions
     bank_name, bank_acc_number, ifsc_code     — bank details
     create_date                               — month of payslip (use for date filtering)
     d_join                                    — date of joining (snapshot)
   For CTC question: SELECT ctc_yearly FROM hr_payroll_monthly_line WHERE emp_id = {employee_id} ORDER BY id DESC LIMIT 1
   For salary breakdown: SELECT ctc_basic, ctc_hra, ctc_special_allowance, gross_sal_after_tax, total_ded, tds, prof_tax FROM hr_payroll_monthly_line WHERE emp_id = {employee_id} ORDER BY id DESC LIMIT 1

6. BONUS — incentive, performance bonus, reward
   Use for: my bonus, any bonus, incentive, performance pay, bonus amount, bonus history
   Table: hr_employee_bonus WHERE employee_id = {employee_id}
   Key cols: bonus_type, bonus_amount, date, state, month, note

7. TIMESHEET — project work hours (NOT office attendance)
   Use for: timesheet, project hours, hours logged on project, project work, hours this week,
            timesheet status (draft/confirmed/done)
   ⚠ Timesheet ≠ Attendance. Timesheet = project work hours only.
   Table: hr_timesheet_sheet_sheet WHERE employee_id = {employee_id}
   Key cols: date_from, date_to, state ('draft'/'confirm'/'done'),
             total_attendance, total_difference, project_names, approved_by

8. EXPENSES / CLAIMS / REIMBURSEMENT
   Use for: expense claims, travel reimbursement, food allowance, pending claims,
            expense status, approved/rejected expense, claim amount
   Table: hr_expense_expense WHERE employee_id = {employee_id}
   Key cols: name, date, amount, state ('draft'/'confirm'/'accepted'/'done'/'cancelled'),
             department_id, jmr_ref, note
   For line items: hr_expense_line JOIN hr_expense_expense ON expense_id = hr_expense_expense.id

9. HELPDESK TICKETS — IT support, complaints, requests
   Use for: my tickets, support requests, IT issues, helpdesk, complaint status,
            open tickets, pending tickets, ticket resolved
   Table: helpdesk_support_ticket WHERE employee_id = {employee_id}
   Key cols: ticket_no, description, state, priority, date_closed, project_id

10. COMPANY / DEPARTMENT / TEAM INFO
    Use for: list departments, my team members, colleagues, who is in my department,
             org chart, how many employees, department head, team info
    Tables: hr_department, hr_employee
    For team: WHERE department_id = (SELECT department_id FROM hr_employee WHERE id = {employee_id})

11. PUBLIC HOLIDAYS / COMPANY CALENDAR
    Use for: is [day/festival] a holiday, can I take leave on [festival name], list holidays,
             what are the upcoming holidays, is [date] a holiday, Shiva Ratri / Holi / Diwali
             / Good Friday / Dussehra / any festival name, holiday this month/year
    Tables:
      holiday_calendar_line hcl  — full holiday list per location
        key cols: name (holiday name), date (DATE), year (TEXT e.g. '2026'),
                  restricted_holiday (FALSE=mandatory public holiday, TRUE=optional/restricted)
      optional_holiday_line ohl  — specific optional holidays per location
        key cols: name, date, holiday_year_id
    ⚠ These are company-wide tables — NO employee isolation filter needed.
    Search by name: WHERE hcl.name ILIKE '%shivratri%' OR hcl.name ILIKE '%shiva%'
    For current year: WHERE hcl.year = EXTRACT(YEAR FROM CURRENT_DATE)::text
    Typical query pattern:
      SELECT hcl.name, hcl.date,
             CASE WHEN hcl.restricted_holiday THEN 'Optional' ELSE 'Public Holiday' END AS type
      FROM holiday_calendar_line hcl
      WHERE hcl.name ILIKE '%keyword%'
        AND hcl.year = EXTRACT(YEAR FROM CURRENT_DATE)::text
      ORDER BY hcl.date
      LIMIT 10

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Output ONLY the raw SQL query (no markdown, no "SQLQuery:" prefix, no explanation).
   If no DB query is needed, answer directly in plain text — do NOT output a token.
2. NEVER generate INSERT / UPDATE / DELETE / DROP / ALTER / TRUNCATE / CREATE / GRANT / REVOKE.
3. Personal-data queries MUST include an employee isolation filter:
     • All personal tables except hr_payroll_monthly_line / hr_salary_payment_line:
         WHERE employee_id = {employee_id}
     • hr_payroll_monthly_line, hr_salary_payment_line:
         WHERE emp_id = {employee_id}
     • holiday_calendar_line, optional_holiday_line, hr_department, hr_designation:
         NO employee filter needed (company-wide data)
4. LIMIT list queries to 20 rows. Aggregate (COUNT/SUM/AVG) queries: no LIMIT needed.
5. Always use explicit table aliases in multi-table queries.
6. Never use hr_employee.current_ctc — it is always 0. Use hr_payroll_monthly_line.ctc_yearly.

Current employee context:
  employee_id : {employee_id}
  name        : {name}
  emp_code    : {emp_code}

Database schema:
{schema}
"""

_FORMAT_SYSTEM = """\
You are a concise HR assistant. Answer the employee's question using ONLY the data provided.

Rules:
- Answer ONLY what was asked. Do not add unrequested information.
- 1 sentence for single-value answers. Short bullet list only for multiple items.
- Use ₹ for currency. Use "days" for leave counts.
- Show zero values too (e.g. "0 days" is still a valid answer — do NOT say "no data found" for zeros).
- No preamble ("Based on...", "Here is..."), no closing remarks.
- No markdown bold/italic. Plain text only.
- If the data list is truly empty (no rows at all): respond exactly "No [topic] data found. Please contact HR."
- Never mention SQL, table names, column names, or technical details.
"""



# ---------------------------------------------------------------------------
# LLM client (singleton)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=Config.OPENROUTER_MODEL,
        api_key=Config.OPENROUTER_API_KEY,
        base_url=Config.OPENROUTER_BASE_URL.removesuffix('/chat/completions'),
        temperature=0,
        default_headers={
            'HTTP-Referer': 'http://localhost:5000',
            'X-Title': 'JMR HR Agent',
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_sql(text: str) -> str:
    """Strip markdown fences and common LLM prefixes from SQL output."""
    text = text.strip()
    text = re.sub(r'^```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    text = re.sub(r'^(?:SQLQuery|SQL)\s*:\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_sql_or_answer(
    user_message: str,
    employee_info: dict,
    history: list[dict] | None = None,
) -> tuple[str | None, str | None]:
    """
    Ask the LLM whether database data is needed.

    Returns:
        (sql_string, None)    — LLM wants to query the DB
        (None, answer_string) — LLM can answer directly (general knowledge / greetings)
        (None, None)          — LLM returned DIRECT_ANSWER but no text (caller uses fallback)
    """
    system = _SQL_SYSTEM.format(
        employee_id=employee_info['employee_id'],
        name=employee_info.get('name', ''),
        emp_code=employee_info.get('emp_code', ''),
        schema=HR_SCHEMA,
    )

    messages: list = [SystemMessage(content=system)]

    # Include last 6 turns of chat history for context
    for turn in (history or [])[-6:]:
        role = turn.get('role')
        content = turn.get('content', '')
        if role == 'user':
            messages.append(HumanMessage(content=content))
        elif role == 'assistant':
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    raw = _get_llm().invoke(messages).content.strip()
    logger.info('[LLM_RAW] %r', raw[:500])

    cleaned = _clean_sql(raw)
    if cleaned.upper().startswith('SELECT'):
        return cleaned, None

    # LLM answered directly (greeting, policy question, etc.)
    return None, raw


def format_result(
    user_message: str,
    rows: list[dict],
    employee_info: dict,
) -> str:
    """
    Ask the LLM to turn query results into natural language.
    Returns a human-readable answer string.
    """
    if not rows:
        return 'No data was found for your query. Please contact HR if you need further help.'

    human = f'Question: {user_message}\nData: {rows[:25]}'
    messages = [
        SystemMessage(content=_FORMAT_SYSTEM),
        HumanMessage(content=human),
    ]
    return _get_llm().invoke(messages).content.strip()



