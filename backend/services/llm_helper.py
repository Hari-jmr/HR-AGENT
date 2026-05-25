import re
import json
import requests
from backend.core.config import Config
from backend.services.db_helper import HR_SCHEMA, execute_safe_query
from backend.services.text2sql_service import generate_text2sql_query


_LEAVE_TYPE_ALIASES = {
    'casual leave': ('cl', 'casual leave'),
    'sick leave': ('sl', 'sick leave'),
    'earned leave': ('el', 'earned leave'),
    'privilege leave': ('pl', 'privilege leave'),
    'emergency leave': ('emergency leave',),
    'maternity leave': ('maternity leave',),
    'paternity leave': ('paternity leave',),
    'adoption leave': ('adoption leave',),
    'birthday leave': ('birthday leave',),
    'compoff leave': ('compoff', 'comp off', 'compoff leave'),
    'celebration holiday': ('celebration holiday',),
    'education leave': ('education leave',),
    'optional holiday': ('optional holiday',),
}

_LEAVE_TYPE_SHORT_CODES = {
    'casual leave': 'CL',
    'sick leave': 'SL',
    'earned leave': 'EL',
    'privilege leave': 'PL',
}

_LEAVE_BALANCE_CONTEXT = ('balance', 'current', 'remaining', 'available', 'left', 'used', 'my', 'me', 'still', 'have', 'day', 'days', 'show')
_PAYROLL_SUMMARY_TERMS = ('payroll', 'salary', 'payslip', 'pay slip', 'net pay', 'gross pay')
_LATEST_TERMS = ('latest', 'last', 'recent', 'current')


def _normalize_query(text):
    return ' '.join(text.lower().split())


def _detect_leave_type(query):
    for leave_type, aliases in _LEAVE_TYPE_ALIASES.items():
        for alias in aliases:
            if re.search(rf'\b{re.escape(alias)}\b', query):
                return leave_type
    return None


def _is_leave_balance_request(query):
    leave_type = _detect_leave_type(query)
    has_balance_context = any(re.search(rf'\b{re.escape(term)}\b', query) for term in _LEAVE_BALANCE_CONTEXT)
    has_leave_balance_phrase = 'leave balance' in query
    query_tokens = re.findall(r'[a-z0-9]+', query)
    shorthand_request = leave_type is not None and len(query_tokens) <= 2
    return (leave_type is not None and has_balance_context) or has_leave_balance_phrase or shorthand_request


def _format_day_value(value):
    number = float(value or 0)
    if number.is_integer():
        return str(int(number))
    return f'{number:.2f}'.rstrip('0').rstrip('.')


def _format_amount_value(value):
    number = float(value or 0)
    return f'{number:,.2f}'


def _normalize_leave_type_name(value):
    normalized = re.sub(r'\d+', '', str(value or '').strip().lower())
    normalized = ' '.join(normalized.split())
    replacements = {
        'casual leave': 'casual leave',
        'sick leaves': 'sick leave',
        'maternity leave': 'maternity leave',
        'paternity leave': 'paternity leave',
        'compoff leave': 'compoff leave',
    }
    return replacements.get(normalized, normalized)


def _format_leave_type_label(leave_type):
    leave_type = _normalize_leave_type_name(leave_type)
    short_code = _LEAVE_TYPE_SHORT_CODES.get(leave_type)
    title = leave_type.title()
    if short_code:
        return f'{title} ({short_code})'
    return title


def _aggregate_leave_rows(rows):
    aggregated = {}
    for row in rows:
        normalized_name = _normalize_leave_type_name(row.get('leave_type'))
        if not normalized_name:
            continue
        aggregated[normalized_name] = aggregated.get(normalized_name, 0.0) + float(row.get('balance_days') or 0)

    return [
        {
            'leave_type': leave_type,
            'label': _format_leave_type_label(leave_type),
            'balance_days': balance_days,
        }
        for leave_type, balance_days in sorted(
            aggregated.items(),
            key=lambda item: (-item[1], _format_leave_type_label(item[0])),
        )
    ]


def _is_latest_payroll_summary_request(query):
    has_payroll_term = any(term in query for term in _PAYROLL_SUMMARY_TERMS)
    has_latest_term = any(term in query for term in _LATEST_TERMS)
    return has_payroll_term and has_latest_term


def resolve_leave_balance(user_message, employee_info):
    query = _normalize_query(user_message)
    leave_type = _detect_leave_type(query)
    sql = """
        SELECT
            hs.name AS leave_type,
            COALESCE(SUM(CASE WHEN h.type = 'add' AND h.state = 'validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS allocated_days,
            COALESCE(SUM(CASE WHEN h.type = 'remove' AND h.state = 'validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS used_days,
            COALESCE(SUM(CASE WHEN h.type = 'add' AND h.state = 'validate' THEN h.number_of_days_temp ELSE 0 END), 0)
              - COALESCE(SUM(CASE WHEN h.type = 'remove' AND h.state = 'validate' THEN h.number_of_days_temp ELSE 0 END), 0) AS balance_days
        FROM hr_holidays_status hs
        LEFT JOIN hr_holidays h
          ON h.holiday_status_id = hs.id
         AND h.employee_id = %s
    """
    params = [employee_info['employee_id']]

    if leave_type:
        sql += " WHERE LOWER(hs.name) = %s"
        params.append(leave_type)

    sql += " GROUP BY hs.id, hs.name ORDER BY hs.name"

    result, error = execute_safe_query(sql, tuple(params), limit=100)
    if error:
        return None, sql, None, error

    rows = _aggregate_leave_rows(result['rows'] if result else [])
    if leave_type and rows:
        row = rows[0]
        return (
            f"You currently have {_format_day_value(row['balance_days'])} day(s) of {row['label']} available.",
            sql,
            result.get('data_source'),
            None,
        )

    if not rows:
        return 'No leave balance data found for your account.', sql, result.get('data_source') if result else None, None

    positive_rows = [row for row in rows if row['balance_days'] > 0]
    if not positive_rows:
        return 'You currently do not have any leave balance available.', sql, result.get('data_source'), None

    lines = ['Here is your current leave balance:']
    lines.extend(
        f"{row['label']}: {_format_day_value(row['balance_days'])} day(s)"
        for row in positive_rows
    )

    zero_count = len(rows) - len(positive_rows)
    if zero_count > 0:
        lines.append(f'{zero_count} other leave type(s) are currently at 0 day(s).')

    return '\n'.join(lines), sql, result.get('data_source'), None


def resolve_latest_payroll_summary(employee_info):
    sql = """
        SELECT
            id AS payroll_id,
            gross_sal_before_tax,
            gross_sal_after_tax,
            total_ded,
            ctc_yearly
        FROM hr_payroll_monthly_line
        WHERE emp_id = %s
        ORDER BY id DESC
        LIMIT 1
    """

    result, error = execute_safe_query(sql, (employee_info['employee_id'],), limit=1)
    if error:
        return None, sql, None, error

    rows = result['rows'] if result else []
    if not rows:
        fallback_sql = """
            SELECT id AS payment_id, salary
            FROM hr_salary_payment_line
            WHERE emp_id = %s
            ORDER BY id DESC
            LIMIT 1
        """
        fallback_result, fallback_error = execute_safe_query(fallback_sql, (employee_info['employee_id'],), limit=1)
        if fallback_error:
            return None, fallback_sql, None, fallback_error
        fallback_rows = fallback_result['rows'] if fallback_result else []
        if not fallback_rows:
            return 'No payroll data found for your account.', fallback_sql, fallback_result.get('data_source') if fallback_result else None, None

        row = fallback_rows[0]
        return (
            f"Your latest payroll summary shows salary {_format_amount_value(row['salary'])}.",
            fallback_sql,
            fallback_result.get('data_source'),
            None,
        )

    row = rows[0]
    return (
        'Your latest payroll summary shows gross pay '
        f"{_format_amount_value(row['gross_sal_before_tax'])}, net pay {_format_amount_value(row['gross_sal_after_tax'])}, "
        f"deductions {_format_amount_value(row['total_ded'])}, and annual CTC {_format_amount_value(row['ctc_yearly'])}.",
        sql,
        result.get('data_source'),
        None,
    )


def build_system_prompt(employee_info, is_hr=False):
    role_note = (
        "The current user is an HR team member. They can query data about ANY employee."
        if is_hr else
        "The current user is a regular employee. They can ONLY see their OWN data. "
        "Always filter queries by employee_id = {emp_id}.".format(emp_id=employee_info['employee_id'])
    )

    return f"""You are the JMR Group HR Policy Agent & Assistant. You are an expert on ALL company HR policies,
procedures, and employee guidelines. You provide CRISP, SPECIFIC, and ACTIONABLE answers.

CURRENT USER:
- Name: {employee_info.get('name', 'N/A')}
- Employee ID: {employee_info['employee_id']}
- Employee Code: {employee_info.get('emp_code', 'N/A')}
- Department: {employee_info.get('department_name', 'N/A')}
- Designation: {employee_info.get('designation_name', 'N/A')}
- Manager: {employee_info.get('manager_name', 'N/A')}
- Date of Joining: {employee_info.get('doj', 'N/A')}

ACCESS LEVEL: {role_note}

{HR_SCHEMA}

===== RESPONSE INSTRUCTIONS =====

**STRICT ANTI-HALLUCINATION RULES (HIGHEST PRIORITY):**
1. ONLY answer policy questions using content that is explicitly present in the knowledge base above.
2. If a specific policy, benefit, or eligibility rule is NOT mentioned anywhere in the knowledge base,
   respond with EXACTLY this message (fill in the policy name):
   "The [Policy Name] policy is not currently available in our system. Please contact HR for details."
3. Do NOT infer, estimate, assume, or generate eligibility criteria, amounts, or rules that are not
   explicitly stated in the knowledge base. No creative interpretations.
4. Do NOT use phrases like "typically", "usually", "generally" to fill gaps — if you don't have
   the specific rule, use the fallback message above.
5. This rule applies to ALL policy types: bonuses, allowances, onsite, travel, insurance, etc.

**FOR HR POLICY QUESTIONS** (leave, travel, conduct, security, harassment, insurance, etc.):
- Answer DIRECTLY from the knowledge base above. Do NOT generate SQL for policy questions.
- Give CRISP, SPECIFIC answers — not vague references. Include actual rules, numbers, and steps.
- Structure your response with:
  - **Direct Answer** (1-2 lines answering the core question)
  - **Key Details** (bullet points with specific rules, limits, entitlements)
  - **Process/Steps** (numbered steps if the question involves a procedure)
  - **Important Notes** (any exceptions, deadlines, or conditions)
- Use bold for key terms and numbers.
- Keep answers concise but complete — no unnecessary filler.

**FOR DATA/DATABASE QUESTIONS** (leave balance, attendance, salary, team info, etc.):
- Output EXACTLY ONE sql code block:
```sql
SELECT ...
```
- ONLY use SELECT statements. Never modify data.
- For leave balance: Allocated = SUM(number_of_days_temp) WHERE type='add' AND state='validate',
  Used = SUM(number_of_days_temp) WHERE type='remove' AND state='validate', Balance = Allocated - Used.
  Group by holiday_status_id and join hr_holidays_status for leave type names.
- Add reasonable LIMITs. Use JOINs for readable names instead of IDs.
- For the current employee, filter by employee_id = {employee_info['employee_id']}.

**RESPONSE FORMAT FOR DATA ANSWERS (STRICT):**
- For leave balance queries (any leave type — CL, SL, EL, PL, etc.): respond with EXACTLY one sentence:
  "Your current <Leave Type> balance is <value> day(s)."
  If multiple types are returned, list each on its own line in the same format.
- Do NOT add motivational commentary, explanations, or filler phrases such as:
  "This gives you flexibility...", "Feel free to use...", "Make sure to plan...", etc.
- For all other single data-point answers (salary, attendance count, etc.), return one factual sentence only.
- Only expand with bullet points or tables when the result contains multiple columns or rows that need context.

**FOR ERP HOW-TO QUESTIONS** (how to apply leave, timesheet, travel request, etc.):
- Give the exact step-by-step process from the ERP Guides.
- Include the menu navigation path (e.g., Human Resources → Leaves → Leave Request).
- Mention any important tips or common mistakes.

**GENERAL RULES:**
1. Be friendly, professional, and concise.
2. Format responses with bullet points, bold text, and numbered steps.
3. Dates should be formatted nicely (e.g., "15 Mar 2026").
4. If you don't have specific information about a policy detail, say so honestly
   and suggest the employee contact HR for the exact detail.
5. Never make up policy rules that aren't in the knowledge base.
6. For complex policy scenarios, explain the general rule first, then note any exceptions.
"""


def call_llm(messages):
    """Call OpenRouter API with cost-aware routing."""
    headers = {
        'Authorization': f'Bearer {Config.OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': 'http://localhost:5000',
        'X-Title': 'JMR HRMS Chatbot'
    }
    provider = {
        'sort': Config.OPENROUTER_PROVIDER_SORT,
    }
    max_price = {}
    if Config.OPENROUTER_MAX_PRICE_PROMPT is not None:
        max_price['prompt'] = Config.OPENROUTER_MAX_PRICE_PROMPT
    if Config.OPENROUTER_MAX_PRICE_COMPLETION is not None:
        max_price['completion'] = Config.OPENROUTER_MAX_PRICE_COMPLETION
    if max_price:
        provider['max_price'] = max_price

    payload = {
        'model': Config.OPENROUTER_MODEL,
        'messages': messages,
        'max_tokens': 2048,
        'temperature': 0.3,
        'provider': provider,
    }

    if Config.OPENROUTER_MODEL == 'openrouter/auto' and Config.OPENROUTER_AUTO_ALLOWED_MODELS:
        payload['plugins'] = [{
            'id': 'auto-router',
            'allowed_models': Config.OPENROUTER_AUTO_ALLOWED_MODELS,
        }]

    resp = requests.post(Config.OPENROUTER_BASE_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data['choices'][0]['message']['content']


def extract_sql(text):
    """Extract SQL query from ```sql ... ``` blocks."""
    pattern = r'```sql\s*(.*?)\s*```'
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[0].strip()
    return None


def chat(user_message, conversation_history, employee_info, is_hr=False):
    """
    Process a chat message. Two-step flow:
    1. Send user question to LLM -> may get SQL
    2. If SQL found, execute it, send results back -> get formatted answer

    Returns (response_text, sql_used, data_source_info).
    data_source_info is a dict for admin/debug use only — must NOT be shown to employees.
    """
    import logging
    logger = logging.getLogger(__name__)

    normalized_query = _normalize_query(user_message)

    if not is_hr and _is_leave_balance_request(normalized_query):
        response_text, sql_used, data_source, error = resolve_leave_balance(user_message, employee_info)
        if error:
            return f'I tried to query the database but encountered an error: {error}', sql_used, data_source
        return response_text, sql_used, data_source

    if not is_hr and _is_latest_payroll_summary_request(normalized_query):
        response_text, sql_used, data_source, error = resolve_latest_payroll_summary(employee_info)
        if error:
            return f'I tried to query the database but encountered an error: {error}', sql_used, data_source
        return response_text, sql_used, data_source

    system_prompt = build_system_prompt(employee_info, is_hr)

    messages = [{'role': 'system', 'content': system_prompt}]
    # Add recent conversation history (last 10 exchanges)
    for msg in conversation_history[-20:]:
        messages.append(msg)
    messages.append({'role': 'user', 'content': user_message})

    llm_response = None

    # Step 1: Try LangChain Text-to-SQL for live-data questions.
    try:
        generated_sql = generate_text2sql_query(user_message, employee_info, is_hr)
        if generated_sql:
            llm_response = f'```sql\n{generated_sql}\n```'
    except Exception as exc:
        logger.warning('[TEXT2SQL_ERROR] query=%r error=%s', user_message, exc)

    # Step 2: Fall back to document/policy answering when Text-to-SQL says NO_SQL
    # or if SQL generation was unavailable.
    if llm_response is None:
        logger.info(
            '[POLICY_GUARDRAIL] No local policy knowledge is available for query=%r — returning fallback',
            user_message,
        )
        return (
            'No HR policy data found for this question. Please contact HR for details.',
            None,
            None,
        )

    # Check for SQL query
    sql = extract_sql(llm_response)
    if not sql:
        return llm_response, None, None

    # ------------------------------------------------------------------
    # Hard employee isolation guard (non-HR users only).
    # The LLM is instructed to filter by the logged-in employee's ID, but
    # that is a soft instruction. We enforce it here at the app layer so
    # that a crafted message cannot retrieve another employee's data.
    # ------------------------------------------------------------------
    if not is_hr:
        emp_id_str = str(employee_info['employee_id'])
        emp_code_str = str(employee_info.get('emp_code', ''))
        sql_lower = sql.lower()
        has_emp_id   = emp_id_str   in sql
        has_emp_code = emp_code_str in sql if emp_code_str else False
        # Allow queries that don't touch personal tables (e.g. hr_holidays_status lookup)
        personal_tables = ('hr_holidays', 'hr_payroll_monthly_line', 'hr_salary_payment_line',
                           'hr_daily_attendance', 'hr_attendance', 'hr_monthly_attendance',
                           'hr_timesheet_sheet_sheet', 'hr_expense_expense', 'hr_employee_bonus',
                           'hr_employee_salary_income', 'hr_employee')
        touches_personal = any(t in sql_lower for t in personal_tables)
        if touches_personal and not has_emp_id and not has_emp_code:
            logger.warning(
                '[ISOLATION_BLOCK] SQL missing employee filter for user=%s emp_id=%s sql=%r',
                employee_info.get('name'), emp_id_str, sql,
            )
            return (
                "I can only retrieve your own data. Please ask about your own leave, "
                "payroll, or attendance.",
                None, None,
            )

    # Step 2: Execute SQL and get formatted results
    result, error = execute_safe_query(sql)
    data_source = result.get('data_source') if result else None

    if error:
        # Tell LLM about the error, let it try to fix or explain
        messages.append({'role': 'assistant', 'content': llm_response})
        messages.append({
            'role': 'user',
            'content': f"The SQL query returned an error: {error}\nPlease fix the query or explain the issue."
        })
        try:
            retry_response = call_llm(messages)
            retry_sql = extract_sql(retry_response)
            if retry_sql:
                result, error2 = execute_safe_query(retry_sql)
                if error2:
                    return f"I tried to query the database but encountered an error: {error2}", sql, None
                retry_source = result.get('data_source') if result else None
                # Format the successful retry results
                messages.append({'role': 'assistant', 'content': retry_response})
                messages.append({
                    'role': 'user',
                    'content': format_results_message(result)
                })
                final_response = call_llm(messages)
                return final_response, retry_sql, retry_source
            return retry_response, sql, None
        except Exception:
            return f"I tried to query the database but encountered an error: {error}", sql, None

    # Format results and send back to LLM
    messages.append({'role': 'assistant', 'content': llm_response})
    messages.append({
        'role': 'user',
        'content': format_results_message(result)
    })

    try:
        final_response = call_llm(messages)
    except Exception as e:
        # If second LLM call fails, format results ourselves
        return format_results_fallback(result), sql, data_source

    return final_response, sql, data_source


def format_results_message(result):
    """Format query results as a message for the LLM."""
    if not result or not result['rows']:
        return "The query returned no results. Please provide a helpful response explaining this."

    rows_text = json.dumps(result['rows'][:30], default=str, indent=2)
    return (
        f"The query returned {result['count']} row(s). Here are the results:\n"
        f"Columns: {', '.join(result['columns'])}\n"
        f"Data:\n{rows_text}\n\n"
        "Please format these results into a clear, friendly response for the employee. "
        "Use bullet points or a table format. Don't show raw JSON."
    )


def format_results_fallback(result):
    """Simple result formatter if LLM second call fails."""
    if not result or not result['rows']:
        return "No data found for your query."

    lines = []
    for row in result['rows'][:20]:
        parts = [f"**{k}**: {v}" for k, v in row.items() if v is not None]
        lines.append(" | ".join(parts))
    return "\n".join(lines)
