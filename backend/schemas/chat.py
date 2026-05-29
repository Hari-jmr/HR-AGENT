from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str


class ChatSection(BaseModel):
    kind: Literal['paragraph', 'list']
    title: str | None = None
    content: str | None = None
    items: list[str] = Field(default_factory=list)


class ChatStructuredResponse(BaseModel):
    summary: str
    sections: list[ChatSection] = Field(default_factory=list)


class ChatHistoryEntry(BaseModel):
    role: Literal['user', 'assistant']
    content: str
    structured: ChatStructuredResponse | None = None


class ChatResponse(BaseModel):
    response: str
    structured: ChatStructuredResponse
    sql: str | None = None
    data_source: str | None = None
    
    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data.pop('sql', None)
        return data


class ChatMemoryResponse(BaseModel):
    """Session memory state."""
    employee_id: int
    employee_name: str
    message_count: int
    last_topic: str | None = None
    last_query_type: str | None = None
    context_summary: str
    session_duration_seconds: float