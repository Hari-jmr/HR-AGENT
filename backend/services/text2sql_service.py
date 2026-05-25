import re
from functools import lru_cache
from urllib.parse import quote_plus

from langchain.chains import create_sql_query_chain
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from backend.core.config import Config
from backend.services.db_helper import _TABLE_SOURCE_MAP


SUPPORTED_DATA_TABLES = tuple(_TABLE_SOURCE_MAP.keys())

DOMAIN_TABLES = {
    'leave': ('hr_holidays', 'hr_holidays_status', 'hr_employee'),
    'attendance': ('hr_daily_attendance', 'hr_attendance', 'hr_monthly_attendance', 'hr_employee'),
    'payroll': ('hr_payroll_monthly_line', 'hr_salary_payment_line', 'hr_employee_salary_income', 'hr_employee_bonus', 'hr_employee'),
    'timesheet': ('hr_timesheet_sheet_sheet', 'hr_employee'),
    'expense': ('hr_expense_expense', 'hr_expense_line', 'hr_employee'),
    'employee': ('hr_employee',),
}

DOMAIN_HINTS = {
    'leave': ('leave', 'cl', 'sl', 'el', 'pl', 'casual', 'sick', 'earned', 'privilege', 'balance', 'holiday'),
    'attendance': ('attendance', 'present', 'absent', 'punch', 'worked hours', 'regularisation', 'regularization', 'sign in', 'sign out'),
    'payroll': ('payroll', 'salary', 'payslip', 'pay slip', 'ctc', 'bonus', 'gross pay', 'net pay', 'deduction'),
    'timesheet': ('timesheet', 'time sheet', 'logged hours', 'project hours', 'time tracking'),
    'expense': ('expense', 'expenses', 'claim', 'claims', 'reimbursement', 'travel claim'),
    'employee': ('manager', 'department', 'designation', 'employee id', 'emp code', 'joining date', 'doj', 'reporting manager'),
}

TEXT2SQL_PROMPT = PromptTemplate.from_template(
    """You are a PostgreSQL Text-to-SQL assistant for an HRMS application.

Return exactly one SQL SELECT query when the question needs live data from the database.
If the question is about policies, handbook content, eligibility rules, benefits rules,
or ERP how-to guidance, return exactly NO_SQL.

Rules:
- Use PostgreSQL syntax only.
- Only generate SELECT queries.
- Never generate INSERT, UPDATE, DELETE, ALTER, DROP, CREATE, TRUNCATE, GRANT, or REVOKE.
- Only use the tables provided in {table_info}.
- Limit list queries to at most {top_k} rows unless the query is an aggregate returning one row.
- Use explicit JOINs and readable column names.
- Prefer hr_daily_attendance for attendance summaries because hr_monthly_attendance may contain NULL rollups.
- Leave balance comes from validated allocations minus validated removals in hr_holidays joined to hr_holidays_status.
- Payroll data comes from hr_payroll_monthly_line and hr_salary_payment_line.
- Expense data comes from hr_expense_expense and hr_expense_line.
- Timesheet data comes from hr_timesheet_sheet_sheet.

Access restrictions:
- Current employee_id: {employee_id}
- Current employee code: {employee_code}
- Current user role: {user_role}
- If the user role is employee and the query touches personal data, always filter by employee_id = {employee_id}.
- For payroll tables using emp_id/emp_code, use emp_id = {employee_id} or emp_code = '{employee_code}' for employee-scoped queries.

Question: {input}
SQLQuery:"""
)


def _clean_base_url(url: str) -> str:
    return url.removesuffix('/chat/completions')


def _text2sql_model_name() -> str:
    if Config.OPENROUTER_MODEL != 'openrouter/auto':
        return Config.OPENROUTER_MODEL
    if Config.OPENROUTER_AUTO_ALLOWED_MODELS:
        return Config.OPENROUTER_AUTO_ALLOWED_MODELS[0]
    return 'openai/gpt-4o-mini'


def _connection_uri() -> str:
    return (
        'postgresql+psycopg2://'
        f'{quote_plus(Config.DB_USER)}:{quote_plus(Config.DB_PASSWORD)}'
        f'@{Config.DB_HOST}:{Config.DB_PORT}/{quote_plus(Config.DB_NAME)}'
    )


@lru_cache(maxsize=1)
def get_sql_database() -> SQLDatabase:
    return SQLDatabase.from_uri(
        _connection_uri(),
        include_tables=list(SUPPORTED_DATA_TABLES),
        sample_rows_in_table_info=1,
        view_support=False,
    )


@lru_cache(maxsize=1)
def get_text2sql_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=_text2sql_model_name(),
        api_key=Config.OPENROUTER_API_KEY,
        base_url=_clean_base_url(Config.OPENROUTER_BASE_URL),
        temperature=0,
        default_headers={
            'HTTP-Referer': 'http://localhost:5000',
            'X-Title': 'JMR HRMS Chatbot',
        },
    )


def _strip_sql_payload(value: str) -> str:
    text = value.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:sql)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
    text = re.sub(r'^SQLQuery:\s*', '', text, flags=re.IGNORECASE)
    return text.strip()


def _normalize_query(text: str) -> str:
    return ' '.join(text.lower().split())


def _query_features(query: str) -> set[str]:
    tokens = re.findall(r'[a-z0-9]+', query)
    features = set(tokens)
    for size in (2, 3):
        for index in range(len(tokens) - size + 1):
            features.add(' '.join(tokens[index:index + size]))
    return features


def _relevant_tables_for_query(user_message: str) -> list[str]:
    query = _normalize_query(user_message)
    features = _query_features(query)
    selected = []

    for domain, hints in DOMAIN_HINTS.items():
        if any(hint in features for hint in hints):
            selected.extend(DOMAIN_TABLES[domain])

    if not selected:
        return list(SUPPORTED_DATA_TABLES)

    ordered = []
    seen = set()
    for table in selected:
        if table in SUPPORTED_DATA_TABLES and table not in seen:
            seen.add(table)
            ordered.append(table)
    return ordered or list(SUPPORTED_DATA_TABLES)


def generate_text2sql_query(user_message: str, employee_info: dict, is_hr: bool = False) -> str | None:
    table_names_to_use = _relevant_tables_for_query(user_message)
    prompt = TEXT2SQL_PROMPT.partial(
        employee_id=str(employee_info['employee_id']),
        employee_code=str(employee_info.get('emp_code', '')),
        user_role='hr' if is_hr else 'employee',
    )
    chain = create_sql_query_chain(
        get_text2sql_llm(),
        get_sql_database(),
        prompt=prompt,
        k=20,
    )
    response = chain.invoke({
        'question': user_message,
        'table_names_to_use': table_names_to_use,
    })
    sql = _strip_sql_payload(response)
    if sql.upper() == 'NO_SQL':
        return None
    return sql or None