"""
config.py — CricketLens Backend Configuration
All paths, thresholds, and broadcaster parameters in one place.
"""

import os
from pathlib import Path

# ── Storage roots ──────────────────────────────────────────────────────────────
BASE_DIR     = Path(os.getenv("CRICKETLENS_DATA_DIR", "./data"))
UPLOADS_DIR  = BASE_DIR / "uploads"
JOBS_DIR     = BASE_DIR / "jobs"
MODELS_DIR   = Path(os.getenv("CRICKETLENS_MODELS_DIR", "./models"))

for d in [UPLOADS_DIR, JOBS_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── YOLO ───────────────────────────────────────────────────────────────────────
YOLO_MODEL_PATH = Path(os.getenv(
    "YOLO_MODEL_PATH",
    str(MODELS_DIR / "cricket_v3_yolov8s" / "weights" / "best.pt"),
))
YOLO_CONF_THRESHOLD = 0.35
YOLO_CLASSES = {
    0 : "boundary_graphic",
    1 : "bowler_box",
    2 : "broadcaster_logo",
    3 : "decision_graphic",
    4 : "delivery_region",
    5 : "dismissal_card",
    6 : "hawkeye_graphic",
    7 : "over_box",
    8 : "replay_indicator",
    9 : "score_box",
    10: "stats_overlay",
    11: "third_umpire_graphic",
    12: "umpire_notout_signal",
    13: "umpire_out_signal",
    14: "wicket_graphic",
}

# ── Broadcaster crop ratios — (x_start, x_end) as fraction of frame width ─────
# score: where the score "RUNS-WICKETS" lives horizontally in the score strip
# dots: where the delivery dot sequence lives horizontally
# bottom: what fraction from the bottom the score strip occupies
BROADCASTER_CROPS = {
    "star_sports": {"score": (0.35, 0.65), "dots": (0.68, 1.00), "bottom": 0.15},
    "ecb"        : {"score": (0.00, 0.35), "dots": (0.55, 1.00), "bottom": 0.12},
    "nzc"        : {"score": (0.05, 0.40), "dots": (0.65, 1.00), "bottom": 0.14},
    "talent_tv"  : {"score": (0.30, 0.60), "dots": (0.60, 0.90), "bottom": 0.15},
    "sporty_lk"  : {"score": (0.00, 0.45), "dots": (0.55, 0.85), "bottom": 0.15},
    "unknown"    : {"score": (0.25, 0.65), "dots": (0.65, 1.00), "bottom": 0.15},
}

# ── Card zone ratios — (top, bottom, left, right) as fractions of frame ────────
# CARD_ZONES: used during Phase 2 card scan (where to look for the card)
CARD_ZONES = {
    "sporty_lk"  : (0.55, 0.87, 0.05, 0.70),
    "talent_tv"  : (0.78, 0.97, 0.00, 1.00),
    "star_sports": (0.72, 0.92, 0.25, 0.78),
    "nzc"        : (0.65, 0.88, 0.20, 0.85),
    "ecb"        : (0.73, 0.89, 0.20, 0.78),
}

# CARD_ZONES_READ: used in Cell 13 to re-read the full card block for parsing
CARD_ZONES_READ = {
    "sporty_lk"  : (0.82, 1.00, 0.00, 1.00),
    "talent_tv"  : (0.78, 0.97, 0.00, 1.00),
    "star_sports": (0.68, 0.95, 0.20, 0.82),
    "nzc"        : (0.65, 0.88, 0.20, 0.85),
    "ecb"        : (0.72, 0.90, 0.18, 0.80),
}

# ── Phase 1 scan ───────────────────────────────────────────────────────────────
PHASE1_STRIDE_SEC = 2.0          # sample one frame every N seconds

# ── Phase 2 card search ────────────────────────────────────────────────────────
CARD_SAMPLE_INNER_SEC  = 1.0    # dense sampling in the inner window
CARD_SAMPLE_OUTER_SEC  = 3.0    # coarser sampling in the outer window
CARD_INNER_WINDOW_SEC  = 60     # seconds after event to search densely
CARD_MAX_WINDOW_SEC    = 300    # total card search window
CARD_SCORE_THRESHOLD   = 3      # loose threshold (scan phase)
CARD_EARLY_STOP_SCORE  = 6      # early-stop when very confident
CARD_MIN_FRAMES        = 2      # minimum frames to form a card window

# ── Commentary ─────────────────────────────────────────────────────────────────
WHISPER_MODEL       = os.getenv("WHISPER_MODEL", "small")   # "small" or "medium"
AUDIO_SAMPLE_RATE   = 16000
COMMENTARY_PRE_SEC  = 10        # seconds before delivery to capture
COMMENTARY_POST_SEC = 120       # seconds after delivery to capture

# ── HuggingFace ────────────────────────────────────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")

# ── API ────────────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES    = 10 * 1024 ** 3    # 10 GB
ALLOWED_VIDEO_EXTS  = {".mp4", ".mkv", ".avi", ".mov", ".ts"}
CORS_ORIGINS        = os.getenv("CORS_ORIGINS", "*").split(",")
