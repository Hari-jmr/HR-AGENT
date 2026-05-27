import re

from backend.schemas.chat import ChatResponse, ChatSection, ChatStructuredResponse
from backend.services.llm_helper import chat


def _sanitize_history_for_llm(history: list[dict]) -> list[dict]:
    sanitized = []
    for message in history:
        role = message.get('role')
        content = message.get('content')
        if role in {'user', 'assistant'} and isinstance(content, str):
            sanitized.append({'role': role, 'content': content})
    return sanitized


def _clean_line_prefix(value: str) -> str:
    return re.sub(r'^(?:[-*+]|\d+\.)\s*', '', value).strip()


def _build_structured_response(response_text: str) -> ChatStructuredResponse:
    lines = [_clean_line_prefix(line) for line in response_text.splitlines() if line.strip()]
    if not lines:
        return ChatStructuredResponse(summary='')

    if len(lines) == 1:
        return ChatStructuredResponse(summary=lines[0])

    summary = lines[0].rstrip(':') if lines[0].endswith(':') else lines[0]
    sections: list[ChatSection] = []
    list_items: list[str] = []
    paragraphs: list[str] = []

    for line in lines[1:]:
        idx = line.find(': ')
        # List item: has "Key: value" where the key is at most 4 words (not a sentence)
        if idx > 0 and len(line[:idx].split()) <= 4:
            list_items.append(line)
        else:
            paragraphs.append(line)

    if list_items:
        sections.append(ChatSection(kind='list', items=list_items))

    for paragraph in paragraphs:
        sections.append(ChatSection(kind='paragraph', content=paragraph))

    if not sections:
        sections.append(ChatSection(kind='paragraph', content=' '.join(lines[1:])))

    return ChatStructuredResponse(summary=summary, sections=sections)


def handle_chat_message(session: dict, user_message: str, employee: dict):
    history = session.get('chat_history', [])
    is_hr = session.get('is_hr', False)

    response_text, sql_used, data_source = chat(
        user_message,
        _sanitize_history_for_llm(history),
        employee,
        is_hr,
    )
    structured = _build_structured_response(response_text)
    payload = ChatResponse(
        response=response_text,
        structured=structured,
        sql=sql_used,
        data_source=data_source,
    )

    history.append({'role': 'user', 'content': user_message})
    history.append({
        'role': 'assistant',
        'content': payload.response,
        'structured': payload.structured.model_dump(),
    })
    session['chat_history'] = history[-20:]

    return payload.model_dump()


def clear_chat_history(session: dict):
    if 'user_id' in session:
        session['chat_history'] = []