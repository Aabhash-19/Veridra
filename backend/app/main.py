import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.errors import ApiError, build_error_response
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.migrations import run_migrations
from app.db.session import get_engine, session_scope
from app.prompts.registry import ensure_prompts_persisted
from app.schemas.common import FieldError, new_id
from app.workers.runner import shutdown_active_runs

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.langsmith_tracing and settings.langsmith_api_key.strip():
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key.strip())
        os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    if settings.app_env != "production":
        # In development/test, ensure local schema is migrated cleanly
        run_migrations(settings.database_url)
    try:
        with session_scope() as db:
            ensure_prompts_persisted(db)
    except Exception:
        logger.warning("Prompt seeding skipped at startup (migrations may need to run first).")
    yield
    await shutdown_active_runs()


def create_app() -> FastAPI:
    settings = get_settings()
    is_dev = settings.app_env in {"development", "test"}

    app = FastAPI(
        title="Veridra API",
        version="1.0.0",
        docs_url="/docs" if is_dev else None,
        redoc_url="/redoc" if is_dev else None,
        openapi_url="/openapi.json" if is_dev else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        req_id = request.headers.get("X-Request-ID") or new_id("req")
        request.state.request_id = req_id
        token = request_id_ctx.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token)

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request=request,
            field_errors=exc.field_errors,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = [
            FieldError(
                field=".".join(str(part) for part in err.get("loc", []) if part != "body"),
                message=str(err.get("msg", "Invalid value")),
            )
            for err in exc.errors()
        ]
        return build_error_response(
            status_code=422,
            code="INVALID_REQUEST",
            message="Request validation failed.",
            request=request,
            field_errors=field_errors,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled API exception", extra={"extra_data": {"error_type": type(exc).__name__}}
        )
        return build_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            request=request,
        )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    app.include_router(api_v1_router)
    return app


app = create_app()
