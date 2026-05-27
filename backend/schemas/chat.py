from typing import Literal

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