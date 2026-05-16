# ══════════════════════════════════════════════════════════════════════════════
# CricketLens — Local Backend Startup Script (Windows PowerShell)
# ══════════════════════════════════════════════════════════════════════════════
#
# Usage (from any PowerShell window):
#   cd d:\Projects\CricVision\cricketlens-backend
#   .\start_local.ps1
#
# The backend starts at http://localhost:8000
# The frontend (in a separate terminal) at http://localhost:5173
# ──────────────────────────────────────────────────────────────────────────────

# ─── 1. Configure paths ───────────────────────────────────────────────────────
# Google Drive for Desktop typically mounts at one of these locations on Windows.
# Find yours by opening File Explorer and looking for "Google Drive" or "My Drive".
# Common paths:
#   G:\My Drive\...
#   C:\Users\nadil\Google Drive\...
#   C:\Users\nadil\My Drive\...

# ── Local paths (Drive folders downloaded to d:\Projects\CricVision) ──────────
$PROJECT_ROOT  = "d:\Projects\CricVision"

$YOLO_MODEL    = "$PROJECT_ROOT\Dataset\yolo_region_detection\models\cricket_v3_yolov8s\weights\best.pt"
$DATA_DIR      = "$PROJECT_ROOT\cricketlens_jobs"      # local jobs folder
# Alternatively keep jobs in your user profile:
# $DATA_DIR   = "$env:USERPROFILE\cricketlens_jobs"

$WHISPER_SIZE  = "small"   # "small" (faster) or "medium" (more accurate)
$HF_TOKEN      = ""        # HuggingFace token — needed only for PaliGemma VLM
                           # Get one free at https://huggingface.co/settings/tokens

# ─── 2. Validate YOLO model path ─────────────────────────────────────────────
if (-not (Test-Path $YOLO_MODEL)) {
    Write-Host ""
    Write-Host "  ERROR: YOLO model not found at:" -ForegroundColor Red
    Write-Host "    $YOLO_MODEL" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Edit the `$YOLO_MODEL path at the top of this script." -ForegroundColor Cyan
    Write-Host "  Make sure Google Drive for Desktop is running and synced." -ForegroundColor Cyan
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}

# ─── 3. Set environment variables ────────────────────────────────────────────
$env:YOLO_MODEL_PATH      = $YOLO_MODEL
$env:CRICKETLENS_DATA_DIR = $DATA_DIR
$env:WHISPER_MODEL        = $WHISPER_SIZE
if ($HF_TOKEN) { $env:HF_TOKEN = $HF_TOKEN }

# Create data dir if missing
if (-not (Test-Path $DATA_DIR)) {
    New-Item -ItemType Directory -Force -Path $DATA_DIR | Out-Null
    Write-Host "  Created data directory: $DATA_DIR" -ForegroundColor Green
}

# ─── 4. Print startup banner ──────────────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║         CricketLens  —  Local Backend            ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  YOLO model : $YOLO_MODEL" -ForegroundColor White
Write-Host "  Data dir   : $DATA_DIR"   -ForegroundColor White
Write-Host "  Whisper    : $WHISPER_SIZE" -ForegroundColor White
Write-Host ""
Write-Host "  API        : http://localhost:8000"      -ForegroundColor Green
Write-Host "  Docs       : http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "  Start the frontend separately:"           -ForegroundColor Yellow
Write-Host "    cd d:\Projects\CricVision\cricketlens-frontend" -ForegroundColor Yellow
Write-Host "    npm run dev"                            -ForegroundColor Yellow
Write-Host ""
Write-Host "  Then open  http://localhost:5173  in your browser." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the server." -ForegroundColor DarkGray
Write-Host ""

# ─── 5. Start uvicorn ─────────────────────────────────────────────────────────
# --workers 1 is mandatory — models are singletons, job store is in-memory
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --reload
