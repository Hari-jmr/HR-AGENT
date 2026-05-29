"""
Chat Service — Orchestrates chat message handling with session memory.
"""

import re
import logging

from backend.schemas.chat import ChatResponse, ChatSection, ChatStructuredResponse
from backend.services.llm_helper import chat
from backend.services.session_memory import SessionMemoryManager
from backend.services.intent_classifier import HRIntent, classify_intent

logger = logging.getLogger(__name__)


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


def _get_topic_from_intent(intent: HRIntent) -> str:
    """Map intent to topic name."""
    topic_map = {
        HRIntent.LEAVE_BALANCE: 'leave_balance',
        HRIntent.LEAVE_HISTORY: 'leave_history',
        HRIntent.SALARY: 'salary',
        HRIntent.SALARY_PAYMENT: 'salary_payment',
        HRIntent.SALARY_COMPONENTS: 'salary_components',
        HRIntent.CTC: 'ctc',
        HRIntent.PAYSLIP: 'payslip',
        HRIntent.ATTENDANCE: 'attendance',
        HRIntent.PRESENCE_CHECK: 'attendance',
        HRIntent.WORKED_HOURS: 'attendance',
        HRIntent.PROFILE: 'profile',
        HRIntent.JOINING_DATE: 'joining_date',
        HRIntent.MANAGER: 'manager',
        HRIntent.DEPARTMENT: 'department',
        HRIntent.TIMESHEET: 'timesheet',
        HRIntent.PROJECT_HOURS: 'timesheet',
        HRIntent.EXPENSE: 'expenses',
        HRIntent.CLAIM: 'expenses',
        HRIntent.HELPDESK: 'helpdesk',
        HRIntent.TICKET: 'helpdesk',
        HRIntent.HOLIDAY: 'holidays',
        HRIntent.FESTIVAL: 'holidays',
        HRIntent.PROJECTS: 'projects',
        HRIntent.TEAM: 'team',
        HRIntent.BONUS: 'bonus',
        HRIntent.POLICY: 'policy',
    }
    return topic_map.get(intent, 'general')


def handle_chat_message(session: dict, user_message: str, employee: dict) -> dict:
    """
    Handle incoming chat message with session memory.
    
    Args:
        session: FastAPI session dictionary
        user_message: User's message text
        employee: Employee info dictionary
    
    Returns:
        ChatResponse dictionary
    """
    memory_manager = SessionMemoryManager(session)
    memory = memory_manager.get_or_create(employee)
    
    enhanced_message = memory_manager.enhance_message(user_message)
    
    intent = classify_intent(user_message)
    topic = _get_topic_from_intent(intent)
    
    memory_manager.add_user_message(user_message)
    
    history_for_llm = _sanitize_history_for_llm(memory.get_recent_messages(6))
    
    is_hr = session.get('is_hr', False)
    
    response_text, sql_used, data_source = chat(
        enhanced_message,
        history_for_llm,
        employee,
        is_hr,
    )
    
    entity = None
    if topic in ['leave_balance', 'salary', 'attendance']:
        entity = topic.replace('_', ' ')
    
    memory_manager.update_context(topic, intent.value, entity)
    
    structured = _build_structured_response(response_text)
    
    memory_manager.add_assistant_message(response_text)
    
    payload = ChatResponse(
        response=response_text,
        structured=structured,
        sql=None,
        data_source=data_source,
    )
    
    return payload.model_dump()


def clear_chat_history(session: dict):
    """Clear chat history and session memory."""
    memory_manager = SessionMemoryManager(session)
    memory_manager.clear()
    
    if 'user_id' in session:
        session['chat_history'] = []


def get_session_memory(session: dict) -> dict:
    """Get current session memory state for API response."""
    from backend.schemas.chat import ChatMemoryResponse
    
    memory_manager = SessionMemoryManager(session)
    memory = memory_manager.get_memory()
    
    if not memory:
        return ChatMemoryResponse(
            employee_id=0,
            employee_name='',
            message_count=0,
            last_topic=None,
            last_query_type=None,
            context_summary='No active session',
            session_duration_seconds=0.0
        ).model_dump()
    
    import time
    return ChatMemoryResponse(
        employee_id=memory.employee_id,
        employee_name=memory.employee_name,
        message_count=len(memory.conversation),
        last_topic=memory.last_topic,
        last_query_type=memory.last_query_type,
        context_summary=memory.get_context_summary(),
        session_duration_seconds=time.time() - memory.created_at
    ).model_dump()
