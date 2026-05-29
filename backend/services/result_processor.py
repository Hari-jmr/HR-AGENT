import logging

from langchain_core.messages import SystemMessage, HumanMessage

from backend.services.prompt_builder import get_format_system_prompt
from backend.services.llm_engine import _get_llm

logger = logging.getLogger(__name__)


def format_result(
    user_message: str,
    rows: list[dict],
    employee_info: dict,
) -> str:
    human = f'Question: {user_message}\nData: {rows[:25]}'
    messages = [
        SystemMessage(content=get_format_system_prompt()),
        HumanMessage(content=human),
    ]

    try:
        return _get_llm().invoke(messages).content.strip()
    except Exception as exc:
        logger.exception('[RESULT_PROCESSOR_ERROR] format_result: %s', exc)
        if rows:
            return f'Found {len(rows)} records.'
        return 'I do not have that information available. Please contact HR for assistance.'