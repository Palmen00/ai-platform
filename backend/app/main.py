from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, connectors, conversations, documents, logs, system
from app.config import settings
from app.services.logging_service import setup_logging

app = FastAPI(title=settings.app_name)
setup_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(connectors.router)
app.include_router(conversations.router)
app.include_router(documents.router)
app.include_router(logs.router)
