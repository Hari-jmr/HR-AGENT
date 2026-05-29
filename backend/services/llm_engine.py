import re
import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage

from backend.core.config import Config
from backend.services.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)


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


def generate_sql(
    user_message: str,
    employee_info: dict,
    history: list[dict] | None = None,
) -> tuple[str | None, str | None]:
    system = build_system_prompt(employee_info)

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
        logger.exception('[LLM_ENGINE_ERROR] generate_sql: %s', exc)
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