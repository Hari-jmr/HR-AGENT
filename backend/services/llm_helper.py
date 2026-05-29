import logging

from backend.services.db_helper import (
    validate_sql,
    enforce_employee_isolation,
    execute_safe_query,
)
from backend.services.sql_generator import generate as sql_generate
from backend.services.result_processor import format_result
from backend.services.intent_classifier import (
    HRIntent,
    classify_intent,
    is_readonly_intent,
    get_intent_response,
)
from backend.services import cache as result_cache

logger = logging.getLogger(__name__)

# Per-intent TTL (seconds). Volatile intents (attendance/timesheet today) get
# a shorter TTL; relatively static lookups (profile, manager) cache longer.
_CACHE_TTL_BY_INTENT: dict[HRIntent, int] = {
    HRIntent.LEAVE_BALANCE: 60,
    HRIntent.LEAVE_HISTORY: 60,
    HRIntent.SALARY: 300,
    HRIntent.SALARY_PAYMENT: 300,
    HRIntent.SALARY_COMPONENTS: 300,
    HRIntent.CTC: 300,
    HRIntent.PAYSLIP: 300,
    HRIntent.PAYROLL: 300,
    HRIntent.ATTENDANCE: 30,
    HRIntent.PRESENCE_CHECK: 30,
    HRIntent.WORKED_HOURS: 30,
    HRIntent.PROFILE: 600,
    HRIntent.JOINING_DATE: 600,
    HRIntent.MANAGER: 600,
    HRIntent.DEPARTMENT: 600,
    HRIntent.TIMESHEET: 60,
    HRIntent.PROJECT_HOURS: 60,
    HRIntent.EXPENSE: 60,
    HRIntent.CLAIM: 60,
    HRIntent.HELPDESK: 60,
    HRIntent.TICKET: 60,
    HRIntent.HOLIDAY: 1800,
    HRIntent.FESTIVAL: 1800,
    HRIntent.PROJECTS: 300,
    HRIntent.TEAM: 600,
    HRIntent.BONUS: 300,
}
_DEFAULT_CACHE_TTL = 60


def chat(
    user_message: str,
    history: list[dict],
    employee_info: dict,
    is_hr: bool = False,
) -> tuple[str, str | None, str | None]:
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
    if not employee_id:
        logger.error('[NO_EMPLOYEE_ID] Cannot process query without employee context')
        return "I couldn't find your employee record. Try logging in again or check with HR.", None, 'error'

    cache_key = result_cache.make_key(employee_id, intent.value, msg)
    cached = result_cache.get(cache_key)
    if cached is not None:
        answer, safe_sql, sql_source = cached
        logger.info('[CACHE_HIT] intent=%s key=%s', intent.value, cache_key[-12:])
        return answer, safe_sql, f'{sql_source}+cache'

    sql, direct_answer, sql_source = sql_generate(intent, msg, employee_info, history)

    if sql is None:
        answer = direct_answer or "I'm not sure about that. Could you try rephrasing?"
        return answer, None, 'llm_direct'

    valid, reason = validate_sql(sql)
    if not valid:
        logger.warning('[VALIDATE_FAIL] %s | sql=%r', reason, sql[:200])
        return "I couldn't figure that out. Could you ask differently?", None, 'sql_blocked'

    emp_code = employee_info.get('emp_code', '')
    safe_sql, block_reason = enforce_employee_isolation(sql, employee_id, emp_code)
    if block_reason:
        logger.warning('[ISOLATION_FAIL] %s | sql=%r', block_reason, sql[:200])
        return "I couldn't figure that out. Could you ask differently?", None, 'sql_blocked'

    result, db_err = execute_safe_query(safe_sql)
    if db_err:
        logger.error('[DB_ERROR] %s | sql=%r', db_err, safe_sql[:200])
        err_source = 'db_timeout' if 'timeout' in db_err.lower() or 'canceling' in db_err.lower() else 'db_error'
        return "Something went wrong on my end. Try again or let IT know if it keeps happening.", None, err_source

    rows = result.get('rows', []) if result else []

    try:
        answer = format_result(msg, rows, employee_info)
    except Exception as exc:
        logger.exception('[FORMAT_ERROR] format_result: %s', exc)
        if rows:
            answer = f"Found {len(rows)} record(s) for you."
        else:
            answer = "I don't see matching records. Check with HR if that doesn't seem right."

    ttl = _CACHE_TTL_BY_INTENT.get(intent, _DEFAULT_CACHE_TTL)
    result_cache.set(cache_key, (answer, safe_sql, sql_source), ttl=ttl)

    return answer, safe_sql, sql_source