import logging
from typing import Optional

from backend.services.intent_classifier import HRIntent
from backend.services import rule_engine
from backend.services import llm_engine

logger = logging.getLogger(__name__)


_LOCATION_TO_CALENDAR: dict[str, str] = {
    # India offices -> state calendars
    'bangalore': 'Karnataka',
    'hyderabad': 'Karnataka',
    'gurgaon': 'Karnataka',
    'noida': 'Karnataka',
    'calicut': 'Kerala',
    'chennai': 'Tamil Nadu',
    'mumbai': 'Mumbai',
    'pune': 'Maharashtra',
    # UAE offices -> UAE calendar
    'dubai': 'UAE',
    'sharjah': 'UAE',
    # Africa -> South Africa calendar
    'capetown': 'South Africa',
    # Australia -> Australia calendar
    'sydney': 'Australia',
}


def _resolve_location(work_location: str | None) -> str:
    if not work_location:
        return 'Karnataka'
    return _LOCATION_TO_CALENDAR.get(work_location.strip().lower(), 'Karnataka')


def generate(
    intent: HRIntent,
    user_message: str,
    employee_info: dict,
    history: list[dict] | None = None,
) -> tuple[str | None, str | None, str]:
    if rule_engine.can_handle(intent):
        holiday_location = _resolve_location(employee_info.get('work_location'))
        sql = rule_engine.generate_sql(intent, employee_info['employee_id'], holiday_location)
        if sql:
            logger.info('[SQL_GEN] deterministic rule matched intent=%s', intent.value)
            return sql, None, 'rule_engine'

    sql, direct_answer = llm_engine.generate_sql(user_message, employee_info, history)
    source = 'rule_engine' if sql and rule_engine.can_handle(intent) else 'llm_engine'
    if sql:
        logger.info('[SQL_GEN] LLM generated SQL source=%s', source)
    return sql, direct_answer, source
