from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.deps import get_session_employee
from backend.schemas.chat import ChatRequest, ChatResponse, ChatMemoryResponse
from backend.schemas.common import ErrorResponse, StatusResponse
from backend.services.chat_service import clear_chat_history, handle_chat_message, get_session_memory


router = APIRouter()

CHAT_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {'model': ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {'model': ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {'model': ErrorResponse},
}


@router.post('/chat', response_model=ChatResponse, responses=CHAT_ERROR_RESPONSES)
def chat(payload: ChatRequest, request: Request, employee: dict = Depends(get_session_employee)):
    if not payload.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Empty message')
    return handle_chat_message(request.session, payload.message.strip(), employee)


@router.get('/memory', response_model=ChatMemoryResponse)
def get_memory(request: Request, employee: dict = Depends(get_session_employee)):
    """Get current session memory and context."""
    return get_session_memory(request.session)


@router.post('/clear', response_model=StatusResponse)
def clear_chat(request: Request):
    clear_chat_history(request.session)
    return StatusResponse(status='ok')