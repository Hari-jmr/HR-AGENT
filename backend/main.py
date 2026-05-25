from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from backend.api.router import api_router
from backend.core.settings import settings
from backend.schemas.common import ErrorDetail, ErrorResponse, StatusResponse


def _format_validation_loc(location: tuple[object, ...]) -> str | None:
    parts = [str(part) for part in location if part != 'body']
    return '.'.join(parts) if parts else None


def _build_validation_details(errors: list[dict]) -> list[ErrorDetail]:
    return [
        ErrorDetail(
            field=_format_validation_loc(error.get('loc', ())),
            message=error.get('msg', 'Invalid value'),
        )
        for error in errors
    ]


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url='/docs',
        redoc_url='/redoc',
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        same_site='lax',
        https_only=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else 'Request failed.'
        details = _build_validation_details(exc.detail) if isinstance(exc.detail, list) else []
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error=message, details=details).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error='Validation error.',
                details=_build_validation_details(exc.errors()),
            ).model_dump(),
        )

    @app.get('/health', response_model=StatusResponse)
    def healthcheck() -> StatusResponse:
        return StatusResponse(status='ok')

    app.include_router(api_router, prefix='/api')
    return app


app = create_app()