"""
routers/api.py — All CricketLens REST endpoints.

POST /api/upload               Upload a video file, create a job, start processing.
POST /api/import-local         Register a LOCAL file path — no upload needed.
GET  /api/jobs                 List all jobs.
GET  /api/jobs/{job_id}        Get job status + progress.
GET  /api/events/{job_id}      Get detected events when job is DONE.
GET  /api/stream/{job_id}      SSE stream of live progress updates.
POST /api/reprocess/{job_id}   Re-run pipeline on an existing upload.
DELETE /api/jobs/{job_id}      Delete a job and its output files.
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncGenerator

import aiofiles
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

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
    try:
        # ── Validate ──────────────────────────────────────────────────────────────
        suffix = Path(file.filename or "video.mp4").suffix.lower()
        if suffix not in ALLOWED_VIDEO_EXTS:
            raise HTTPException(
                400,
                f"Unsupported file type '{suffix}'. "
                f"Allowed: {sorted(ALLOWED_VIDEO_EXTS)}"
            )

        # Guard: only one pipeline runs at a time (YOLO+OCR+Whisper are GPU singletons)
        active = [j for j in _job_store.all() if j.get("status") == "processing"]
        if active:
            raise HTTPException(
                503,
                "Another job is already processing. "
                "Wait for it to finish or delete it first."
            )

        job_id   = str(uuid.uuid4())
        job_dir  = JOBS_DIR / job_id
        log.info("Creating job_dir: %s", job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        
        log.info("Creating job in store: %s", job_id)
        job      = _job_store.create(job_id, file.filename)

        # ── Save upload ───────────────────────────────────────────────────────────
        video_path  = job_dir / f"video{suffix}"
        total_bytes = 0

        log.info("Updating job to UPLOADING status")
        _job_store.update(job, status=JobStatus.UPLOADING, message="Uploading…")

        log.info("Opening file for writing: %s", video_path)
        async with aiofiles.open(video_path, "wb") as out:
            while True:
                chunk = await file.read(4 * 1024 * 1024)   # 4 MB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    await out.close()
                    video_path.unlink(missing_ok=True)
                    _job_store.delete(job_id)
                    raise HTTPException(413, "File exceeds maximum upload size (10 GB)")
                await out.write(chunk)

        log.info("Upload complete, updating job_store")
        _job_store.update(job, video_path=str(video_path), message="Upload complete")
        log.info("Uploaded %s  (%.1f MB)  job_id=%s",
                 file.filename, total_bytes / 1e6, job_id)

        # ── Launch background pipeline ────────────────────────────────────────────
        match_id = Path(file.filename or "match").stem
        log.info("Adding background task for job %s", job_id)
        background_tasks.add_task(
            _run_pipeline_task,
            job_id=job_id,
            video_path=str(video_path),
            job_dir=job_dir,
            match_id=match_id,
            run_commentary=run_commentary,
        )

        log.info("Returning response for job %s", job_id)
        return {
            "job_id"   : job_id,
            "filename" : file.filename,
            "status"   : JobStatus.PROCESSING.value,
            "stream_url": f"/api/stream/{job_id}",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error("Upload handler error: %s", str(e), exc_info=True)
        raise HTTPException(500, f"Upload failed: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Import local file  (no upload — backend reads directly from disk path)
# ─────────────────────────────────────────────────────────────────────────────

class ImportLocalRequest(BaseModel):
    file_path      : str
    run_commentary : bool = True


@router.post("/import-local", summary="Register a local file path and start processing")
async def import_local(
    body: ImportLocalRequest,
    background_tasks: BackgroundTasks,
):
    """
    Use a video file that already exists on the server's local filesystem.

    Pass the absolute path to the file — the backend reads it in-place
    without copying, so even 1.5 GB files start instantly.

    Returns the same job_id / stream_url as /upload.
    """
    file_path = Path(body.file_path)

    # ── Validate ──────────────────────────────────────────────────────────────
    if not file_path.exists():
        raise HTTPException(404, f"File not found: {file_path}")
    if not file_path.is_file():
        raise HTTPException(400, f"Path is not a file: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(
            400,
            f"Unsupported file type '{suffix}'. "
            f"Allowed: {sorted(ALLOWED_VIDEO_EXTS)}"
        )

    # Guard: one job at a time
    active = [j for j in _job_store.all() if j.get("status") == "processing"]
    if active:
        raise HTTPException(
            503,
            "Another job is already processing. "
            "Wait for it to finish or delete it first."
        )

    job_id  = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job = _job_store.create(job_id, file_path.name)
    # Point directly at the source file — no copy needed
    _job_store.update(
        job,
        video_path=str(file_path),
        status=JobStatus.PROCESSING,
        message="Starting pipeline…",
    )

    match_id = file_path.stem
    log.info("import-local: %s  job_id=%s", file_path, job_id)

    background_tasks.add_task(
        _run_pipeline_task,
        job_id=job_id,
        video_path=str(file_path),
        job_dir=job_dir,
        match_id=match_id,
        run_commentary=body.run_commentary,
    )

    return {
        "job_id"    : job_id,
        "filename"  : file_path.name,
        "status"    : JobStatus.PROCESSING.value,
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

    events = job.events or []
    wickets  = [e for e in events if e.get("type") == "wicket"]
    nms      = [e for e in events if e.get("type") == "near_miss"]
    # Prefer stored duration (from video metadata); fall back to last event end
    duration = job.duration_sec or 0.0
    if not duration and events:
        duration = max((e.get("ts_end_sec") or 0) for e in events)

    return {
        "job_id"      : job_id,
        "events"      : events,
        "duration_sec": duration,
        "wicket_count": len(wickets),
        "nm_count"    : len(nms),
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

    # Guard: same singleton model constraint as /upload
    active = [j for j in _job_store.all()
              if j.get("status") == "processing" and j.get("job_id") != job_id]
    if active:
        raise HTTPException(503, "Another job is already processing")

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


# ─────────────────────────────────────────────────────────────────────────────
# Video streaming  (supports HTTP Range for seeking)
# ─────────────────────────────────────────────────────────────────────────────

MIME_MAP = {
    ".mp4" : "video/mp4",
    ".mkv" : "video/x-matroska",
    ".avi" : "video/x-msvideo",
    ".mov" : "video/quicktime",
    ".ts"  : "video/mp2t",
}


@router.get("/video/{job_id}", summary="Stream the uploaded match video")
async def stream_video(job_id: str, request: Request):
    """
    Serve the uploaded video with HTTP Range support so the browser's
    <video> element can seek to arbitrary timestamps.

    The frontend uses a *relative* path (/api/video/{id}) which goes
    through the Vite proxy — the proxy injects the ngrok bypass header.
    """
    job = _job_store.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    if not job.video_path or not Path(job.video_path).exists():
        raise HTTPException(404, "Video file not found on server")

    vpath     = Path(job.video_path)
    file_size = vpath.stat().st_size
    mime      = MIME_MAP.get(vpath.suffix.lower(), "video/mp4")

    # Parse Range header (e.g. "bytes=0-1048575")
    range_header = request.headers.get("range")
    if range_header:
        try:
            range_spec = range_header.replace("bytes=", "")
            start_str, end_str = range_spec.split("-", 1)
            start = int(start_str) if start_str else 0
            end   = int(end_str)   if end_str   else file_size - 1
        except Exception:
            start, end = 0, file_size - 1
    else:
        start, end = 0, file_size - 1

    # Clamp
    start = max(0, min(start, file_size - 1))
    end   = max(start, min(end, file_size - 1))
    chunk_size = end - start + 1

    async def _gen():
        async with aiofiles.open(vpath, "rb") as f:
            await f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                to_read = min(524_288, remaining)   # 512 KB chunks
                data    = await f.read(to_read)
                if not data:
                    break
                remaining -= len(data)
                yield data

    status  = 206 if range_header else 200
    headers = {
        "Content-Range"              : f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges"              : "bytes",
        "Content-Length"             : str(chunk_size),
        "Content-Type"               : mime,
        "Cache-Control"              : "no-cache",
        "Access-Control-Allow-Origin": "*",
    }
    return StreamingResponse(_gen(), status_code=status,
                             headers=headers, media_type=mime)


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

        is_done   = job.status == JobStatus.DONE
        events    = job.events or []
        wkt_count = sum(1 for e in events if e.get("type") == "wicket")
        nm_count  = sum(1 for e in events if e.get("type") == "near_miss")

        payload = json.dumps({
            "job_id"      : job_id,
            "status"      : job.status.value,
            "progress"    : job.progress,
            "message"     : job.message,
            "error"       : job.error,
            # Full event payload on completion — frontend uses these directly
            "events"      : events    if is_done else None,
            "duration_sec": job.duration_sec if is_done else None,
            "wicket_count": wkt_count if is_done else None,
            "nm_count"    : nm_count  if is_done else None,
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
