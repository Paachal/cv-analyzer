"""
FastAPI application entry point.

Wires together the extraction, Gemini-analysis, and MongoDB-storage
modules behind a small set of HTTP routes, and serves the frontend.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings, validate_settings
from app import database
from app.routers import analyze, history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cv_analyzer")

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(history.router)


@app.on_event("startup")
async def on_startup():
    for warning in validate_settings():
        logger.warning(warning)

    await database.ensure_indexes()

    if await database.ping():
        logger.info("Connected to MongoDB at %s", settings.MONGO_URI)
    else:
        logger.error(
            "Could not reach MongoDB at %s — is it running?", settings.MONGO_URI
        )


@app.get("/api/health")
async def health():
    mongo_ok = await database.ping()
    return {
        "status": "ok" if mongo_ok else "degraded",
        "mongo_connected": mongo_ok,
        "gemini_model": settings.GEMINI_MODEL,
    }


# --- Serve the single-file frontend ---
# frontend/index.html lives one directory up from backend/
from pathlib import Path
FRONTEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "frontend")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def serve_frontend():
    return FileResponse(f"{FRONTEND_DIR}/index.html")
