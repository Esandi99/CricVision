"""
storage/job_store.py — In-process job store for CricketLens.

Each uploaded video gets a unique job_id.  The job progresses through:
    PENDING → UPLOADING → PROCESSING → DONE | ERROR

Jobs are stored in memory (dict) and also persisted as JSON to disk
so they survive a server restart.
"""

import json
import logging
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_JOBS_FILE_NAME = "jobs.json"


class JobStatus(str, Enum):
    PENDING    = "pending"
    UPLOADING  = "uploading"
    PROCESSING = "processing"
    DONE       = "done"
    ERROR      = "error"


class Job:
    def __init__(self, job_id: str, filename: str, jobs_dir: Path):
        self.job_id    = job_id
        self.filename  = filename
        self.jobs_dir  = jobs_dir

        self.status    = JobStatus.PENDING
        self.progress  = 0.0        # 0.0 – 1.0
        self.message   = "Queued"
        self.error     = None
        self.created   = datetime.utcnow().isoformat()
        self.updated   = self.created

        # Output paths (set by processor)
        self.video_path    : Optional[str] = None
        self.phase1_csv    : Optional[str] = None
        self.phase2_csv    : Optional[str] = None
        self.final_csv     : Optional[str] = None
        self.commentary_csv: Optional[str] = None

        # Parsed result for API response
        self.events        : Optional[list] = None   # List[EventSchema]
        self.duration_sec  : float = 0.0             # video duration in seconds

    def to_dict(self) -> dict:
        events = self.events or []
        wicket_count = sum(1 for e in events if e.get("type") == "wicket")
        nm_count     = sum(1 for e in events if e.get("type") == "near_miss")
        return {
            "job_id"          : self.job_id,
            "filename"        : self.filename,
            "status"          : self.status.value,
            "progress"        : round(self.progress, 3),
            "message"         : self.message,
            "error"           : self.error,
            "created"         : self.created,
            "created_at"      : self.created,   # alias for frontend compat
            "updated"         : self.updated,
            "video_path"      : self.video_path,
            "phase1_csv"      : self.phase1_csv,
            "phase2_csv"      : self.phase2_csv,
            "final_csv"       : self.final_csv,
            "commentary_csv"  : self.commentary_csv,
            "duration_sec"    : self.duration_sec,
            "wicket_count"    : wicket_count,
            "nm_count"        : nm_count,
            "events"          : self.events,
        }

    @classmethod
    def from_dict(cls, d: dict, jobs_dir: Path) -> "Job":
        j = cls(d["job_id"], d["filename"], jobs_dir)
        j.status         = JobStatus(d.get("status", "pending"))
        j.progress       = d.get("progress", 0.0)
        j.message        = d.get("message", "")
        j.error          = d.get("error")
        j.created        = d.get("created", j.created)
        j.updated        = d.get("updated", j.updated)
        j.video_path     = d.get("video_path")
        j.phase1_csv     = d.get("phase1_csv")
        j.phase2_csv     = d.get("phase2_csv")
        j.final_csv      = d.get("final_csv")
        j.commentary_csv = d.get("commentary_csv")
        j.events         = d.get("events")
        j.duration_sec   = d.get("duration_sec", 0.0)
        return j


class JobStore:
    """Thread-safe in-memory + disk-backed job store."""

    def __init__(self, jobs_dir: Path):
        self._dir   = jobs_dir
        self._store : dict[str, Job] = {}
        self._lock  = threading.Lock()
        self._load_persisted()

    # ── Public API ─────────────────────────────────────────────────────────────

    def create(self, job_id: str, filename: str) -> Job:
        job = Job(job_id, filename, self._dir)
        with self._lock:
            self._store[job_id] = job
        self._persist()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._store.get(job_id)

    def all(self) -> list:
        with self._lock:
            return sorted(
                [j.to_dict() for j in self._store.values()],
                key=lambda j: j["created"],
                reverse=True,
            )

    def update(self, job: Job, **kwargs):
        """Update job fields and persist."""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(job, k):
                    # Convert string status to JobStatus enum if needed
                    if k == "status" and isinstance(v, str):
                        v = JobStatus(v)
                    setattr(job, k, v)
            job.updated = datetime.utcnow().isoformat()
        self._persist()

    def delete(self, job_id: str):
        with self._lock:
            self._store.pop(job_id, None)
        self._persist()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _persist(self):
        path = self._dir / _JOBS_FILE_NAME
        try:
            with self._lock:
                data = {jid: j.to_dict() for jid, j in self._store.items()}
            path.write_text(json.dumps(data, indent=2))
        except Exception as exc:
            log.warning("Could not persist jobs: %s", exc)

    def _load_persisted(self):
        path = self._dir / _JOBS_FILE_NAME
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for jid, d in data.items():
                job = Job.from_dict(d, self._dir)
                # Jobs that were PROCESSING when server died should show as ERROR
                if job.status == JobStatus.PROCESSING:
                    job.status  = JobStatus.ERROR
                    job.error   = "Server restarted during processing"
                    job.message = "Server restarted — please reprocess"
                self._store[jid] = job
            log.info("Loaded %d persisted jobs", len(self._store))
        except Exception as exc:
            log.warning("Could not load persisted jobs: %s", exc)
