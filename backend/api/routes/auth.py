from fastapi import APIRouter, HTTPException, Request, status

from backend.schemas.auth import AuthResponse, LoginRequest
from backend.schemas.common import ErrorResponse, StatusResponse
from backend.services.auth_service import build_auth_payload, login_user, logout_user


router = APIRouter()

AUTH_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {'model': ErrorResponse},
    status.HTTP_401_UNAUTHORIZED: {'model': ErrorResponse},
    status.HTTP_422_UNPROCESSABLE_ENTITY: {'model': ErrorResponse},
}


@router.post('/login', response_model=AuthResponse, responses=AUTH_ERROR_RESPONSES)
def login(payload: LoginRequest, request: Request):
    session_data, error = login_user(request.session, payload.username, payload.password)
    if error:
        error_status = status.HTTP_401_UNAUTHORIZED if error == 'Invalid username or password.' else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=error_status, detail=error)
    return build_auth_payload(session_data)


@router.get('/me', response_model=AuthResponse)
def me(request: Request):
    if 'user_id' not in request.session:
        return AuthResponse(authenticated=False)
    return build_auth_payload(request.session, include_history=True)


@router.post('/logout', response_model=StatusResponse)
def logout(request: Request):
    logout_user(request.session)
    return StatusResponse(status='ok')