from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, connectors, conversations, documents, logs, system
from app.config import settings
from app.services.activity import activity_service
from app.services.logging_service import setup_logging
from app.services.maintenance import maintenance_service
from app.services.starter_knowledge import StarterKnowledgeService

app = FastAPI(title=settings.app_name)
setup_logging()
starter_knowledge_service = StarterKnowledgeService()

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


@app.middleware("http")
async def track_request_activity(request: Request, call_next):
    ignored_paths = {"/health", "/docs", "/openapi.json", "/redoc"}
    if request.url.path not in ignored_paths:
        activity_service.touch_user_activity(request.url.path)
    return await call_next(request)


@app.on_event("startup")
def ensure_starter_knowledge() -> None:
    starter_knowledge_service.ensure_seeded()
    maintenance_service.start_idle_worker()


@app.on_event("shutdown")
def stop_idle_maintenance() -> None:
    maintenance_service.stop_idle_worker()
