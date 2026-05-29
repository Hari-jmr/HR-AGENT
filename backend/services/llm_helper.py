"""
Main chat handler — intent-driven HR agent with strict guardrails.

Flow:
  1. Intent classification → identify what user wants
  2. Write guard → refuse data modifications
  3. Other user guard → refuse cross-employee access
  4. LLM SQL generation → for data queries
  5. Validation → security checks
  6. Employee isolation → enforce data scoping
  7. Execute → run safe query
  8. Format → convert to natural language
"""

import logging
from typing import Optional

from backend.services.db_helper import (
    validate_sql,
    enforce_employee_isolation,
    execute_safe_query,
)
from backend.services.text2sql_service import (
    generate_sql_or_answer,
    format_result,
)
from backend.services.intent_classifier import (
    HRIntent,
    classify_intent,
    is_readonly_intent,
    get_intent_response,
)

logger = logging.getLogger(__name__)


def chat(
    user_message: str,
    history: list[dict],
    employee_info: dict,
    is_hr: bool = False,
) -> tuple[str, str | None, str | None]:
    """
    Handle one chat turn with intent-based routing.
    
    Args:
        user_message: The user's current message.
        history: List of {'role': 'user'|'assistant', 'content': '...'} dicts.
        employee_info: Dict with employee_id, name, emp_code.
        is_hr: True when authenticated user is HR manager.
    
    Returns:
        (response_text, sql_used, data_source)
    """
    if not user_message or not user_message.strip():
        return "Hi! How can I help you today?", None, None

    msg = user_message.strip()
    
    intent = classify_intent(msg)
    logger.info('[INTENT] %s → %s', intent.value, msg[:50])
    
    predefined_response = get_intent_response(intent)
    if predefined_response:
        return predefined_response, None, f'intent_{intent.value}'

    if not is_readonly_intent(intent):
        logger.warning('[BLOCKED_INTENT] %s for: %r', intent.value, msg[:80])
        return (
            "I can only view your HR info — making changes is outside what I can do. "
            "Please reach out to HR for any updates or corrections.",
            None, f'blocked_{intent.value}'
        )

    employee_id = employee_info.get('employee_id')
    emp_code = employee_info.get('emp_code', '')

    if not employee_id:
        logger.error('[NO_EMPLOYEE_ID] Cannot process query without employee context')
        return "I couldn't find your employee record. Try logging in again or check with HR.", None, 'error'

    try:
        sql, direct_answer = generate_sql_or_answer(msg, employee_info, history)
    except Exception as exc:
        logger.exception('[LLM_ERROR] generate_sql_or_answer: %s', exc)
        return "Something went wrong. Can you try asking again?", None, 'error'

    if sql is None:
        answer = direct_answer or "I'm not sure about that. Could you try rephrasing?"
        return answer, None, 'llm_direct'

    valid, reason = validate_sql(sql)
    if not valid:
        logger.warning('[VALIDATE_FAIL] %s | sql=%r', reason, sql[:200])
        return "I couldn't figure that out. Could you ask differently?", None, 'blocked'

    safe_sql, block_reason = enforce_employee_isolation(sql, employee_id, emp_code)
    if block_reason:
        logger.warning('[ISOLATION_FAIL] %s | sql=%r', block_reason, sql[:200])
        return "I couldn't figure that out. Could you ask differently?", None, 'blocked'

    result, db_err = execute_safe_query(safe_sql)
    if db_err:
        logger.error('[DB_ERROR] %s | sql=%r', db_err, safe_sql[:200])
        return "Something went wrong on my end. Try again or let IT know if it keeps happening.", None, 'db_error'

    rows = result.get('rows', []) if result else []

    try:
        answer = format_result(msg, rows, employee_info)
    except Exception as exc:
        logger.exception('[LLM_ERROR] format_result: %s', exc)
        if rows:
            answer = f"Found {len(rows)} record(s) for you."
        else:
            answer = "I don't see matching records. Check with HR if that doesn't seem right."

    return answer, safe_sql, 'db'
