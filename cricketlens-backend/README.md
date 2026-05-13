# CricketLens Backend

Automated cricket event detection from broadcast video — FastAPI backend for the CricketLens web application.

---

## What it does

1. Accepts a video upload via REST API  
2. Runs the full detection pipeline in the background:
   - **Phase 1** — YOLO region detection + OCR score-strip scan (every 2 s)  
   - **Event extraction** — 5-signal wicket detection (event labels, score jumps, YOLO graphics, W-markers, innings-end inference)  
   - **Phase 2** — Dismissal card search with loose → strict OCR scoring  
   - **Phase 3** — Name/mode/bowler/fielder extraction with VLM fallback  
   - **Commentary** — Whisper transcription + regex / zero-shot NLI classification  
3. Returns a JSON event list with precise timestamps for every wicket (and near-miss) to power a video-player timeline

---

## Project structure

```
cricketlens-backend/
├── main.py                  FastAPI app + startup
├── config.py                All thresholds, paths, broadcaster ratios
├── requirements.txt
├── pipeline/
│   ├── models.py            Lazy singleton model loading (YOLO, OCR, Whisper, VLM)
│   ├── helpers.py           Pure helper functions (image/OCR/parsing/scoring)
│   ├── phase1_scan.py       Phase 1: YOLO + OCR frame scan → phase1_scorestrip.csv
│   ├── events.py            Wicket event extraction (5 signals)
│   ├── phase2_cards.py      Phase 2: Dismissal card search → phase2_cards.csv
│   ├── phase3_final.py      Phase 3: Final CSV with name/mode extraction
│   ├── commentary.py        Whisper commentary → wicket/near-miss classification
│   └── orchestrator.py      Full pipeline runner (called from background task)
├── routers/
│   └── api.py               All REST endpoints
└── storage/
    └── job_store.py         In-memory + disk-backed job state
```

---

## Setup

### 1. Install system dependencies

```bash
sudo apt-get install -y ffmpeg
```

### 2. Install PyTorch (with the correct CUDA version for your GPU)

```bash
# CUDA 12.1 example
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Place your YOLO weights

```
models/
└── cricket_v3_yolov8s/
    └── weights/
        └── best.pt        ← your trained YOLOv8s weights
```

Or set `YOLO_MODEL_PATH` environment variable to the full path.

### 5. (Optional) Set environment variables

| Variable | Default | Notes |
|---|---|---|
| `CRICKETLENS_DATA_DIR` | `./data` | Uploads + job outputs |
| `CRICKETLENS_MODELS_DIR` | `./models` | YOLO weights |
| `YOLO_MODEL_PATH` | `{MODELS_DIR}/cricket_v3_yolov8s/weights/best.pt` | Full override |
| `WHISPER_MODEL` | `small` | `small` or `medium` |
| `HF_TOKEN` | _(empty)_ | Required for PaliGemma VLM |
| `CORS_ORIGINS` | `*` | Comma-separated frontend origins |

---

## Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

> **Important:** use `--workers 1`. The model singletons and in-memory job store are not multi-process safe.

API docs available at `http://localhost:8000/docs`.

---

## API reference

### Upload and start processing

```
POST /api/upload
Content-Type: multipart/form-data

file            (required) Video file (.mp4 / .mkv / .avi / .mov / .ts)
run_commentary  (optional, default true)  Run Whisper commentary analysis
```

**Response:**
```json
{
  "job_id": "3fa85f64-...",
  "filename": "SL_PAK_2025_T20I3.mp4",
  "status": "processing",
  "stream_url": "/api/stream/3fa85f64-..."
}
```

---

### Poll job status

```
GET /api/jobs/{job_id}
```

**Response:**
```json
{
  "job_id"   : "3fa85f64-...",
  "status"   : "processing",
  "progress" : 0.42,
  "message"  : "Phase 2: 5/8 wickets processed"
}
```

Possible `status` values: `pending`, `uploading`, `processing`, `done`, `error`

---

### Live progress stream (SSE)

```
GET /api/stream/{job_id}
```

Connect with `EventSource` on the frontend. Each message is a JSON string:

```json
{ "job_id": "...", "status": "processing", "progress": 0.63, "message": "Phase 3: 6/8 wickets" }
```

Final message when done:
```json
{ "status": "done", "progress": 1.0, "events": [ ... ] }
```

---

### Get events (after job completes)

```
GET /api/events/{job_id}
```

**Response:**
```json
{
  "job_id": "3fa85f64-...",
  "count": 16,
  "events": [
    {
      "type"           : "wicket",
      "event_id"       : "W1",
      "wicket_number"  : 1,
      "innings"        : 1,
      "innings_wicket" : 1,
      "score"          : "42-1",
      "over"           : "8.3",
      "delivery_ts_sec": 1823.4,
      "card_ts_sec"    : 1851.2,
      "batsman"        : "KARUNARATNE",
      "runs"           : 28,
      "balls"          : 34,
      "dismissal_mode" : "caught",
      "bowler"         : "SHAHEEN",
      "fielder"        : "BABAR",
      "card_found"     : true,
      "extraction_method": "ocr",
      "confidence"     : 1.0
    },
    ...
  ]
}
```

---

### Other endpoints

| Method | Path | Description |
|---|---|---|
| `GET`    | `/api/jobs`              | List all jobs |
| `POST`   | `/api/reprocess/{job_id}`| Re-run pipeline on existing upload |
| `DELETE` | `/api/jobs/{job_id}`     | Delete job + files |
| `GET`    | `/health`                | Health check |

---

## Frontend integration

The events list gives your video player everything it needs:

- `delivery_ts_sec` — the exact moment the ball was bowled → place the **wicket marker** on the timeline  
- `card_ts_sec` — when the dismissal card appeared → optionally show a secondary marker  
- All metadata (batsman, mode, bowler, fielder, score) → populate the info panel  

Use the SSE stream (`/api/stream/{job_id}`) to show a live progress bar while the video is being processed.
