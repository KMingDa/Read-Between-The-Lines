from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, auth
from app.core.config import CORS_ORIGINS

app = FastAPI(
    title="Read Between the Lines API",
    description="API for the AI Conversation Intelligence Assistant",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analysis.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
