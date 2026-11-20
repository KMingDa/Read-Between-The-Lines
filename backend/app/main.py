from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analysis, auth, conversations
from app.core.config import CORS_ORIGINS, get_settings
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PayloadTooLargeError,
)

ERROR_STATUS_CODES: dict[type[AppError], int] = {
    InvalidInputError: 422,
    ConflictError: 409,
    AuthenticationError: 401,
    NotFoundError: 404,
    PayloadTooLargeError: 413,
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail at startup, not on the first request, when configuration is missing
    yield


app = FastAPI(
    title="Read Between the Lines API",
    description="API for the AI Conversation Intelligence Assistant",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, error: AppError) -> JSONResponse:
    status_code = ERROR_STATUS_CODES[type(error)]
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse({"detail": error.message}, status_code=status_code, headers=headers)


app.include_router(auth.router)
app.include_router(analysis.router)
app.include_router(conversations.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
