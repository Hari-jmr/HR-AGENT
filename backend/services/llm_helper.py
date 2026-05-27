"""
Main chat handler — pure LLM-driven, no hardcoded routing patterns.

Flow:
  1. Write guard  → refuse immediately (no LLM cost)
  2. LLM decides  → generate_sql_or_answer()
  3. Validate SQL → validate_sql()
  4. Isolate      → enforce_employee_isolation()
  5. Execute      → execute_safe_query()
  6. Format       → format_result()

Called by chat_service.py as:
  response_text, sql_used, data_source = chat(user_message, history, employee_info, is_hr)
"""

import re
import logging

from backend.services.db_helper import (
    validate_sql,
    enforce_employee_isolation,
    execute_safe_query,
)
from backend.services.text2sql_service import (
    generate_sql_or_answer,
    format_result,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Write guard — catches obvious data-modification requests before any LLM call
# ---------------------------------------------------------------------------
_WRITE_RE = re.compile(
    r'\b(delete|drop|truncate)\b'
    r'|\b(update|modify|change|edit|alter|insert)\s+(?:my\s+|the\s+|a\s+)?'
    r'(salary|payroll|attendance|leave|timesheet|expense|record|data|entry'
    r'|table|database|profile|details)\b',
    re.IGNORECASE | re.DOTALL,
)

_WRITE_REFUSAL = (
    'I can only read HR data — I cannot create, modify, or delete records. '
    'Please contact your HR team for any data corrections.'
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat(
    user_message: str,
    history: list[dict],
    employee_info: dict,
    is_hr: bool = False,
) -> tuple[str, str | None, str | None]:
    """
    Handle one chat turn.

    Args:
        user_message  : The user's current message.
        history       : List of {'role': 'user'|'assistant', 'content': '...'} dicts.
        employee_info : Dict from db_helper.get_employee_info() — must include
                        employee_id, name, emp_code.
        is_hr         : True when the authenticated user is an HR manager.

    Returns:
        (response_text, sql_used, data_source)
        sql_used / data_source may be None when no DB query was run.
    """
    if not user_message or not user_message.strip():
        return 'Please type a question — I am here to help!', None, None

    # ── 1. Write guard ────────────────────────────────────────────────────────
    if _WRITE_RE.search(user_message):
        logger.info('[WRITE_GUARD] blocked: %r', user_message[:80])
        return _WRITE_REFUSAL, None, 'write_guard'

    employee_id = employee_info.get('employee_id')
    emp_code    = employee_info.get('emp_code', '')

    # ── 2. LLM decides SQL vs direct answer ──────────────────────────────────
    try:
        sql, direct_answer = generate_sql_or_answer(user_message, employee_info, history)
    except Exception as exc:
        logger.exception('[LLM_ERROR] generate_sql_or_answer: %s', exc)
        return (
            'I encountered an error while processing your request. '
            'Please try again or contact IT support.',
            None, 'error',
        )

    # ── 3. Direct answer (no DB needed) ──────────────────────────────────────
    if sql is None:
        return direct_answer or 'I could not answer that. Please contact HR.', None, 'llm_direct'

    # ── 4. Validate SQL ───────────────────────────────────────────────────────
    valid, reason = validate_sql(sql)
    if not valid:
        logger.warning('[VALIDATE_FAIL] %s | sql=%r', reason, sql[:200])
        return (
            f'I generated an unsafe query and blocked it for safety. ({reason}) '
            'Please rephrase your question or contact HR.',
            sql, 'blocked',
        )

    # ── 5. Employee isolation ─────────────────────────────────────────────────
    safe_sql, block_reason = enforce_employee_isolation(sql, employee_id, emp_code)
    if block_reason:
        logger.warning('[ISOLATION_FAIL] %s | sql=%r', block_reason, sql[:200])
        return (
            'I could not safely scope that query to your data. '
            'Please rephrase or contact HR.',
            sql, 'blocked',
        )

    # ── 6. Execute ────────────────────────────────────────────────────────────
    result, db_err = execute_safe_query(safe_sql)
    if db_err:
        logger.error('[DB_ERROR] %s | sql=%r', db_err, safe_sql[:200])
        return (
            f'I ran into a database error: {db_err}. '
            'Please contact IT support if this persists.',
            safe_sql, 'db_error',
        )

    rows = result.get('rows', []) if result else []

    # ── 7. Format results ─────────────────────────────────────────────────────
    try:
        answer = format_result(user_message, rows, employee_info)
    except Exception as exc:
        logger.exception('[LLM_ERROR] format_result: %s', exc)
        # Fallback: raw data
        if rows:
            answer = f'Here is the data I found:\n{rows}'
        else:
            answer = 'No matching data was found.'

    return answer, safe_sql, 'db'
