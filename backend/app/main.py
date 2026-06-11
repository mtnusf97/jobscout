from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import schemas
from .api import (
    credentials_api,
    documents,
    jobs_api,
    onboarding,
    packets_api,
    preferences_api,
    profiles,
    telegram_api,
)
from .config import BACKEND_DIR, settings
from .db import get_db
from .engine.pipeline import recover_interrupted_runs
from .ingest.service import recover_interrupted

APP_VERSION = "0.8.0"


def run_migrations() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.db_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    recover_interrupted()
    recover_interrupted_runs()
    try:
        from .telegram.service import start_all

        start_all()
    except Exception:  # noqa: BLE001 - Telegram trouble must never block startup
        pass
    try:
        from . import scheduler

        scheduler.start()
    except Exception:  # noqa: BLE001 - scheduler trouble must never block startup
        pass
    yield


app = FastAPI(title="JobScout", version=APP_VERSION, lifespan=lifespan)

app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(credentials_api.router, prefix="/api/credentials", tags=["credentials"])
app.include_router(
    documents.router, prefix="/api/profiles/{profile_id}/documents", tags=["documents"]
)
app.include_router(onboarding.router, prefix="/api/profiles/{profile_id}", tags=["onboarding"])
app.include_router(
    preferences_api.router, prefix="/api/profiles/{profile_id}", tags=["preferences"]
)
app.include_router(jobs_api.router, prefix="/api/profiles/{profile_id}", tags=["jobs"])
app.include_router(packets_api.router, prefix="/api/profiles/{profile_id}", tags=["packets"])
app.include_router(telegram_api.router, prefix="/api/profiles/{profile_id}", tags=["telegram"])


@app.get("/api/health", response_model=schemas.HealthOut, tags=["health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return schemas.HealthOut(status="ok", app="jobscout", version=APP_VERSION)


# Single-process mode: serve the built frontend when frontend/dist exists.
# Catch-all (registered after the API routers, so /api always wins) gives SPA
# deep links like /profiles/{id} the index.html they need.
_dist = BACKEND_DIR.parent / "frontend" / "dist"
if _dist.exists():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = _dist / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
