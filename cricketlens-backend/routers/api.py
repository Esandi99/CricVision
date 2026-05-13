"""
routers/api.py — All CricketLens REST endpoints.

POST /api/upload          Upload a video, create a job, start processing.
GET  /api/jobs            List all jobs.
GET  /api/jobs/{job_id}   Get job status + progress.
GET  /api/events/{job_id} Get detected events when job is DONE.
GET  /api/stream/{job_id} SSE stream of live progress updates.
POST /api/reprocess/{job_id} Re-run pipeline on an existing upload.
DELETE /api/jobs/{job_id} Delete a job and its output files.
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncGenerator

import aiofiles
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse

from config import (
    UPLOADS_DIR,
    JOBS_DIR,
    MAX_UPLOAD_BYTES,
    ALLOWED_VIDEO_EXTS,
)
from storage.job_store import JobStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Injected by main.py
_job_store = None


def init_router(job_store):
    global _job_store
    _job_store = job_store


# ─────────────────────────────────────────────────────────────────────────────
# Upload + trigger pipeline
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload", summary="Upload a match video and start processing")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    run_commentary: bool = Query(True,  description="Run Whisper commentary analysis"),
):
    """
    Accept a video upload, save it to disk, and kick off the full pipeline
    in a background thread.

    Returns immediately with a job_id — poll /api/jobs/{job_id} for status,
    or open /api/stream/{job_id} for a Server-Sent Events progress stream.
    """
    # ── Validate ──────────────────────────────────────────────────────────────
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(
            400,
            f"Unsupported file type '{suffix}'. "
            f"Allowed: {sorted(ALLOWED_VIDEO_EXTS)}"
        )

    job_id   = str(uuid.uuid4())
    job_dir  = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    job      = _job_store.create(job_id, file.filename)

    # ── Save upload ───────────────────────────────────────────────────────────
    video_path  = job_dir / f"video{suffix}"
    total_bytes = 0

    _job_store.update(job, status=JobStatus.UPLOADING, message="Uploading…")

    async with aiofiles.open(video_path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)   # 1 MB chunks
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                await out.close()
                video_path.unlink(missing_ok=True)
                _job_store.delete(job_id)
                raise HTTPException(413, "File exceeds maximum upload size (10 GB)")
            await out.write(chunk)

    _job_store.update(job, video_path=str(video_path), message="Upload complete")
    log.info("Uploaded %s  (%.1f MB)  job_id=%s",
             file.filename, total_bytes / 1e6, job_id)

    # ── Launch background pipeline ────────────────────────────────────────────
    match_id = Path(file.filename or "match").stem
    background_tasks.add_task(
        _run_pipeline_task,
        job_id=job_id,
        video_path=str(video_path),
        job_dir=job_dir,
        match_id=match_id,
        run_commentary=run_commentary,
    )

    return {
        "job_id"   : job_id,
        "filename" : file.filename,
        "status"   : JobStatus.PROCESSING.value,
        "stream_url": f"/api/stream/{job_id}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Job management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs", summary="List all jobs")
def list_jobs():
    return _job_store.all()


@router.get("/jobs/{job_id}", summary="Get job status and progress")
def get_job(job_id: str):
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job.to_dict()


@router.get("/events/{job_id}", summary="Get detected events (job must be DONE)")
def get_events(job_id: str):
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(
            409,
            f"Job is '{job.status.value}' — events are only available when DONE"
        )
    return {
        "job_id" : job_id,
        "events" : job.events or [],
        "count"  : len(job.events or []),
    }


@router.post("/reprocess/{job_id}", summary="Re-run pipeline on existing upload")
async def reprocess_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    run_commentary: bool = Query(True),
):
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    if job.video_path is None or not Path(job.video_path).exists():
        raise HTTPException(400, "Original video file not found — re-upload required")

    # Clear cached CSVs so the pipeline re-runs from scratch
    for csv_attr in ["phase1_csv", "phase2_csv", "final_csv", "commentary_csv"]:
        csv_path = getattr(job, csv_attr, None)
        if csv_path and Path(csv_path).exists():
            Path(csv_path).unlink(missing_ok=True)

    _job_store.update(
        job,
        status=JobStatus.PENDING,
        progress=0.0,
        message="Queued for reprocessing",
        events=None,
        error=None,
    )

    match_id = Path(job.filename or "match").stem
    job_dir  = JOBS_DIR / job_id

    background_tasks.add_task(
        _run_pipeline_task,
        job_id=job_id,
        video_path=job.video_path,
        job_dir=job_dir,
        match_id=match_id,
        run_commentary=run_commentary,
    )

    return {"job_id": job_id, "status": "reprocessing"}


@router.delete("/jobs/{job_id}", summary="Delete a job and its output files")
def delete_job(job_id: str):
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    import shutil
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

    _job_store.delete(job_id)
    return {"deleted": job_id}


# ─────────────────────────────────────────────────────────────────────────────
# Server-Sent Events stream
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stream/{job_id}", summary="SSE live progress stream")
async def stream_progress(job_id: str):
    """
    Returns a text/event-stream that emits progress events until the job
    reaches DONE or ERROR.  The frontend can use an EventSource to receive
    these and update a progress bar / status display.

    Each event is a JSON object:
        { "job_id", "status", "progress", "message", "events"? }
    """
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    return StreamingResponse(
        _sse_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control"      : "no-cache",
            "X-Accel-Buffering"  : "no",
        },
    )


async def _sse_generator(job_id: str) -> AsyncGenerator[str, None]:
    terminal = {JobStatus.DONE, JobStatus.ERROR}
    while True:
        job = _job_store.get(job_id)
        if job is None:
            payload = json.dumps({"job_id": job_id, "status": "not_found"})
            yield f"data: {payload}\n\n"
            break

        payload = json.dumps({
            "job_id"  : job_id,
            "status"  : job.status.value,
            "progress": job.progress,
            "message" : job.message,
            "events"  : job.events if job.status == JobStatus.DONE else None,
        })
        yield f"data: {payload}\n\n"

        if job.status in terminal:
            break
        await asyncio.sleep(1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Background task wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline_task(job_id: str, video_path: str,
                       job_dir: Path, match_id: str,
                       run_commentary: bool):
    """Runs the full pipeline synchronously inside a thread-pool worker."""
    from pipeline.orchestrator import run_full_pipeline
    job = _job_store.get(job_id)
    if job is None:
        log.error("Background task: job %s not found", job_id)
        return
    run_full_pipeline(
        job=job,
        job_store=_job_store,
        video_path=video_path,
        job_dir=Path(job_dir),
        match_id=match_id,
        run_commentary=run_commentary,
    )
