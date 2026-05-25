from fastapi import APIRouter

from backend.api.routes import auth, chat


api_router = APIRouter()
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(chat.router, tags=['chat'])
