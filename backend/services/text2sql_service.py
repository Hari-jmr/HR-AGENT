"""
Text-to-SQL service — converts natural language to SQL using LLM.

Uses OpenRouter LLM (Claude Sonnet 4) directly for SQL generation.
The database schema is fetched live from information_schema and cached.
"""

import re
import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from backend.core.config import Config
from backend.services.db_helper import get_schema

logger = logging.getLogger(__name__)


_LOCATION_TO_CALENDAR: dict[str, str] = {
    'calicut': 'Kerala',
    'bangalore': 'Karnataka',
    'hyderabad': 'Karnataka',
    'gurgaon': 'Karnataka',
    'noida': 'Karnataka',
    'mumbai': 'Mumbai',
    'pune': 'Maharashtra',
    'chennai': 'Tamil Nadu',
    'mauritius': 'Mauritius',
    'south africa': 'South Africa',
    'capetown': 'South Africa',
    'egypt': 'Egypt',
    'nigeria': 'Nigeria',
    'ethiopia': 'Ethiopia',
    'uganda': 'Uganda',
    'myanmar': 'Myanmar',
    'mayanmar': 'Myanmar',
    'vietnam': 'Vietnam',
    'uae': 'UAE',
    'dubai': 'UAE',
    'sharjah': 'UAE',
    'philippines': 'Philippines',
    'australia': 'Australia',
    'sydney': 'Australia',
    'kenya': 'Kenya',
    'japan': 'Japan',
    'pakistan': 'Pakistan',
}


def _resolve_holiday_location(work_location: str | None) -> str:
    if not work_location:
        return 'Karnataka'
    return _LOCATION_TO_CALENDAR.get(work_location.strip().lower(), 'Karnataka')


_SQL_SYSTEM = """\
You are a PostgreSQL expert for JMR Group's HR system (Odoo 8).

Given the employee's question, output either:
  (A) A single SQL SELECT query — when database data is needed.
  (B) A concise plain-text answer — for greetings, general HR knowledge, or policy definitions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTENT UNDERSTANDING (handle informal queries)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Employees may use informal language, abbreviations, or typos. Infer intent:

• leave/balance/days off/quota/remaining → LEAVE BALANCE (section 3)
• leave type names (casual/sick/optional/comp off/etc.) → LEAVE BALANCE
• leave applied/taken/history/pending → LEAVE HISTORY (section 4)
• salary/pay/earnings → SALARY (section 5)
• when salary credited/paid → SALARY PAYMENT (section 5a)
• salary breakdown/components → SALARY COMPONENTS (section 5b)
• CTC/package/annual → CTC (section 5)
• attendance/present/absent/punch → ATTENDANCE (section 2)
• timesheet/project hours → TIMESHEET (section 7)
• expense/claim/reimbursement → EXPENSES (section 8)
• ticket/support/helpdesk → HELPDESK (section 9)
• holiday/festival/is X a holiday → HOLIDAYS (section 11)
• profile/my details/DOJ/manager → EMPLOYEE PROFILE (section 1)
• list projects → PROJECTS (section 10a)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• today → CURRENT_DATE
• yesterday → CURRENT_DATE - INTERVAL '1 day'
• this month → DATE_TRUNC('month', CURRENT_DATE)
• last month → DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
• this year → DATE_TRUNC('year', CURRENT_DATE)

For hr_monthly_attendance (month/year are TEXT):
  "this month" → month = EXTRACT(MONTH FROM CURRENT_DATE)::text
                 AND year = EXTRACT(YEAR FROM CURRENT_DATE)::text

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TABLE MAPPING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. EMPLOYEE PROFILE — hr_employee (alias e)
   Use for: name, department, designation, manager, DOJ, emp_code, work_location, emp_state
   ⚠ e.current_ctc is ALWAYS 0 — NEVER use for salary/CTC questions.

2. ATTENDANCE — hr_daily_attendance, hr_monthly_attendance, hr_attendance
   DO NOT use hr_holidays for attendance questions.
   WHERE employee_id = {{employee_id}}

3. LEAVE BALANCE — hr_holidays + hr_holidays_status
   ALWAYS use this pattern:
   SELECT hs.name AS leave_type,
          COALESCE(SUM(CASE WHEN h.type='add'    AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0)
        - COALESCE(SUM(CASE WHEN h.type='remove' AND h.state='validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS balance
   FROM hr_holidays h
   JOIN hr_holidays_status hs ON hs.id = h.holiday_status_id
   WHERE h.employee_id = {{employee_id}}
   GROUP BY hs.name
   ORDER BY hs.name

   For specific type: AND hs.name ILIKE '%keyword%'
   Map: casual→'%casual%', sick→'%sick%', privilege→'%privilege%', earned→'%earned%',
        optional→'%optional%', comp→'%comp%', maternity→'%maternity%', paternity→'%paternity%',
        birthday→'%birthday%', bereavement→'%bereavement%', emergency→'%emergency%'

4. LEAVE HISTORY — hr_holidays + hr_holidays_status
   WHERE h.employee_id = {{employee_id}} AND h.type = 'remove'
   State: pending→draft/confirm, approved→validate, rejected→refuse, cancelled→cancel

5. PAYROLL — hr_payroll_monthly_line
   ⚠ Filter column is emp_id (NOT employee_id)
   Latest: ORDER BY id DESC LIMIT 1
   Key cols: gross_sal_before_tax, gross_sal_after_tax, ctc_yearly, ctc_basic, ctc_hra,
             ctc_special_allowance, total_ded, tds, prof_tax, bank_name, bank_acc_number, ifsc_code

5a. SALARY PAYMENT — hr_salary_payment_line
    WHERE emp_id = {{employee_id}}
    ORDER BY payment_date DESC LIMIT 5

5b. SALARY COMPONENTS — hr_employee_salary_income
    WHERE employee_id = {{employee_id}}
    AND year = EXTRACT(YEAR FROM CURRENT_DATE)::int
    AND month = EXTRACT(MONTH FROM CURRENT_DATE)::int

6. BONUS — hr_employee_bonus
   WHERE employee_id = {{employee_id}}

7. TIMESHEET — hr_timesheet_sheet_sheet
   WHERE employee_id = {{employee_id}}

8. EXPENSES — hr_expense_expense
   WHERE employee_id = {{employee_id}}

9. HELPDESK — helpdesk_support_ticket
   WHERE employee_id = {{employee_id}}

10. PROJECTS — project_project
    SELECT name FROM project_project WHERE active = TRUE ORDER BY name LIMIT 20

11. HOLIDAYS — holiday_calendar_line + optional_holiday_line
    ALWAYS filter by employee's calendar: '{holiday_location}'
    For festival search (e.g., "Is Diwali a holiday?"), use UNION ALL without year filter:
    SELECT name, date, 'Public Holiday' AS type FROM holiday_calendar_line hcl
    JOIN holiday_calendar_year hcy ON hcl.calendar_year_id = hcy.id
    JOIN holiday_calendar hc ON hcy.calendar_id = hc.id
    WHERE hc.name = '{holiday_location}' AND hcl.name ILIKE '%keyword%'
    UNION ALL
    SELECT name, date, 'Optional' AS type FROM optional_holiday_line ohl
    JOIN holiday_calendar_year hcy ON ohl.holiday_year_id = hcy.id
    JOIN holiday_calendar hc ON hcy.calendar_id = hc.id
    WHERE hc.name = '{holiday_location}' AND ohl.name ILIKE '%keyword%'
    ORDER BY date LIMIT 10

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Output ONLY the raw SQL (no markdown, no explanation).
2. NEVER generate INSERT/UPDATE/DELETE/DROP/ALTER/CREATE.
3. Personal queries MUST include: WHERE employee_id = {{employee_id}} (or emp_id for payroll).
4. LIMIT list queries to 20 rows.
5. Use ₹ for currency in answers.

Current employee:
  employee_id      : {employee_id}
  name             : {name}
  emp_code         : {emp_code}
  work_location    : {work_location}
  holiday_calendar : {holiday_location}

Schema:
{schema}
"""

_FORMAT_SYSTEM = """You are a warm HR assistant for JMR Group. Answer employee questions naturally.

Guidelines:
- Be conversational, like chatting with a helpful colleague
- Use natural phrasing: "You have 5 days" not "Your balance is 5 days"
- Use ₹ for currency, "days" for leave counts
- Say "You haven't used any" for zero values
- Keep responses brief and friendly
- Never mention SQL, tables, or technical terms
- Skip phrases like "Based on records" or "According to data"

Empty data responses:
- Holidays: "[Festival] isn't in your location's holiday calendar. Check with HR to confirm."
- Other: "I don't see any [topic] records for you. HR can help clarify this."

Match the employee's tone. If they're casual, be casual. If formal, be professional.
"""


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


def _clean_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    text = re.sub(r'^(?:SQLQuery|SQL)\s*:\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


def generate_sql_or_answer(
    user_message: str,
    employee_info: dict,
    history: list[dict] | None = None,
) -> tuple[str | None, str | None]:
    """
    Ask LLM to generate SQL or answer directly.
    
    Returns:
        (sql, None)    — SQL query to execute
        (None, answer) — Direct answer (greeting, policy, etc.)
    """
    work_location = employee_info.get('work_location') or ''
    holiday_location = _resolve_holiday_location(work_location)
    
    system = _SQL_SYSTEM.format(
        employee_id=employee_info['employee_id'],
        name=employee_info.get('name', ''),
        emp_code=employee_info.get('emp_code', ''),
        work_location=work_location or 'Unknown',
        holiday_location=holiday_location,
        schema=get_schema(),
    )

    messages: list = [SystemMessage(content=system)]

    for turn in (history or [])[-6:]:
        role = turn.get('role')
        content = turn.get('content', '')
        if role == 'user':
            messages.append(HumanMessage(content=content))
        elif role == 'assistant':
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    try:
        raw = _get_llm().invoke(messages).content.strip()
    except Exception as exc:
        logger.exception('[LLM_ERROR] generate_sql_or_answer: %s', exc)
        return None, 'I encountered an error. Please try again.'

    logger.debug('[LLM_RAW] %r', raw[:300])

    cleaned = _clean_sql(raw)
    if cleaned.upper().startswith('SELECT'):
        return cleaned, None

    select_match = re.search(r'(?i)\bSELECT\b', raw)
    if select_match:
        sql_candidate = _clean_sql(raw[select_match.start():])
        if sql_candidate.upper().startswith('SELECT'):
            return sql_candidate, None

    return None, raw


def format_result(
    user_message: str,
    rows: list[dict],
    employee_info: dict,
) -> str:
    """
    Convert query results to natural language.
    """
    human = f'Question: {user_message}\nData: {rows[:25]}'
    messages = [
        SystemMessage(content=_FORMAT_SYSTEM),
        HumanMessage(content=human),
    ]
    
    try:
        return _get_llm().invoke(messages).content.strip()
    except Exception as exc:
        logger.exception('[LLM_ERROR] format_result: %s', exc)
        if rows:
            return f'Found {len(rows)} records.'
        return 'I apologize, but I do not have that information available. Please contact HR for assistance.'
