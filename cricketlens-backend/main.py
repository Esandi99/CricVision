"""
main.py — CricketLens Backend API entry point.

Start with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

Workers MUST be 1 — the YOLO / OCR models are loaded once into the
process and the job store is in-memory.  If you need multiple workers
use an external Redis-backed job queue instead.

Environment variables (all optional):
    CRICKETLENS_DATA_DIR     Where to store uploads + job outputs  (default: ./data)
    CRICKETLENS_MODELS_DIR   Where to find the YOLO .pt file      (default: ./models)
    YOLO_MODEL_PATH          Override full path to YOLO weights
    WHISPER_MODEL            "small" (default) or "medium"
    HF_TOKEN                 HuggingFace token — required for PaliGemma VLM
    CORS_ORIGINS             Comma-separated origins  (default: *)
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import JOBS_DIR, CORS_ORIGINS
from storage.job_store import JobStore
from routers.api import router as api_router, init_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CricketLens API",
    description=(
        "Automated cricket event detection from broadcast video.\n\n"
        "Upload a match video and receive timestamped wicket + near-miss events "
        "for use in a video player timeline."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Job store (singleton) ─────────────────────────────────────────────────────
job_store = JobStore(JOBS_DIR)
init_router(job_store)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ── Global exception handler ──────────────────────────────────────────────────
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}", "type": exc.__class__.__name__},
    )


# ── Startup / shutdown hooks ──────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    log.info("CricketLens API starting up")
    log.info("  Jobs dir : %s", JOBS_DIR)
    log.info("  Existing jobs: %d", len(job_store.all()))


@app.on_event("shutdown")
async def on_shutdown():
    log.info("CricketLens API shutting down")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    busy = any(
        j.get("status") == "processing"
        for j in job_store.all()
    )
    return {
        "status"  : "ok",
        "busy"    : busy,
        "jobs"    : len(job_store.all()),
        "platform": "standalone",
    }


@app.get("/", tags=["system"])
def root():
    return {
        "name"   : "CricketLens API",
        "version": "1.0.0",
        "docs"   : "/docs",
    }
