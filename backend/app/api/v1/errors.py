from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import request_id_ctx
from app.schemas.common import ErrorDetail, ErrorResponse, FieldError


class ApiError(Exception):
    """Structured API error mapped directly to the Veridra error envelope."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        field_errors: list[FieldError] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or []


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request | None = None,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    req_id = (
        (getattr(request.state, "request_id", None) if request else None)
        or request_id_ctx.get()
        or "req_unknown"
    )
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=req_id,
            field_errors=field_errors or [],
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())
