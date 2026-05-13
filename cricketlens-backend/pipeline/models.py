"""
pipeline/models.py — Lazy singleton model loading for CricketLens.

All heavy models (YOLO, EasyOCR, PaddleOCR, Whisper, Zero-shot NLI,
PaliGemma) are loaded at most once per process and then reused.

Call load_phase1_models() before Phase 1 scans.
Call load_commentary_models() before commentary analysis.
Call load_vlm_models() if you want PaliGemma VLM extraction.
"""

import logging
import threading
from typing import Optional

import torch

from config import (
    YOLO_MODEL_PATH,
    YOLO_CONF_THRESHOLD,
    WHISPER_MODEL,
    HF_TOKEN,
)

log = logging.getLogger(__name__)

# ── Thread-safety ──────────────────────────────────────────────────────────────
_lock = threading.Lock()

# ── Model state ───────────────────────────────────────────────────────────────
_models: dict = {}


def _gpu() -> bool:
    return torch.cuda.is_available()


def _device() -> str:
    return "cuda" if _gpu() else "cpu"


# ─────────────────────────────────────────────────────────────────────────────
# YOLO region detector
# ─────────────────────────────────────────────────────────────────────────────

def get_yolo():
    """Return the YOLO region-detection model (loaded once)."""
    with _lock:
        if "yolo" not in _models:
            from ultralytics import YOLO
            log.info("Loading YOLO region detector from %s", YOLO_MODEL_PATH)
            if not YOLO_MODEL_PATH.exists():
                raise FileNotFoundError(
                    f"YOLO model not found at {YOLO_MODEL_PATH}. "
                    "Set YOLO_MODEL_PATH env var or place weights at the default path."
                )
            _models["yolo"] = YOLO(str(YOLO_MODEL_PATH))
            log.info("YOLO loaded ✅  conf-threshold=%.2f", YOLO_CONF_THRESHOLD)
    return _models["yolo"]


# ─────────────────────────────────────────────────────────────────────────────
# OCR
# ─────────────────────────────────────────────────────────────────────────────

def get_easyocr():
    """Return the EasyOCR reader (English, loaded once)."""
    with _lock:
        if "easyocr" not in _models:
            import easyocr
            log.info("Loading EasyOCR (en) on %s …", _device())
            _models["easyocr"] = easyocr.Reader(["en"], gpu=_gpu())
            log.info("EasyOCR loaded ✅")
    return _models["easyocr"]


def get_paddleocr() -> Optional[object]:
    """Return PaddleOCR instance, or None if unavailable."""
    with _lock:
        if "paddleocr" not in _models:
            try:
                from paddleocr import PaddleOCR
                log.info("Loading PaddleOCR …")
                _models["paddleocr"] = PaddleOCR(
                    use_angle_cls=False,
                    lang="en",
                    use_gpu=_gpu(),
                    show_log=False,
                    rec_algorithm="SVTR_LCNet",
                )
                log.info("PaddleOCR loaded ✅")
            except Exception as exc:
                log.warning("PaddleOCR unavailable (%s) — falling back to EasyOCR", exc)
                _models["paddleocr"] = None
    return _models["paddleocr"]


# ─────────────────────────────────────────────────────────────────────────────
# Whisper
# ─────────────────────────────────────────────────────────────────────────────

def get_whisper(size: Optional[str] = None):
    """Return a Whisper model.  Uses WHISPER_MODEL from config by default."""
    size = size or WHISPER_MODEL
    key  = f"whisper_{size}"
    with _lock:
        if key not in _models:
            import whisper
            log.info("Loading Whisper %s …", size)
            _models[key] = whisper.load_model(size)
            log.info("Whisper %s loaded ✅", size)
    return _models[key]


# ─────────────────────────────────────────────────────────────────────────────
# Zero-shot NLI (commentary classification)
# ─────────────────────────────────────────────────────────────────────────────

def get_zero_shot():
    """Return the zero-shot classification pipeline (bart-large-mnli)."""
    with _lock:
        if "zero_shot" not in _models:
            from transformers import pipeline as hf_pipeline
            log.info("Loading zero-shot classifier (facebook/bart-large-mnli) …")
            _models["zero_shot"] = hf_pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=0 if _gpu() else -1,
            )
            log.info("Zero-shot classifier loaded ✅")
    return _models["zero_shot"]


# ─────────────────────────────────────────────────────────────────────────────
# Language translation (Sinhala / Hindi → English)
# ─────────────────────────────────────────────────────────────────────────────

def get_translators() -> tuple:
    """Return (si_translator, hi_translator).  Either may be None."""
    with _lock:
        if "translators" not in _models:
            from transformers import pipeline as hf_pipeline
            si_tr = hi_tr = None
            try:
                log.info("Loading Sinhala→English translator …")
                si_tr = hf_pipeline(
                    "translation",
                    model="Helsinki-NLP/opus-mt-si-en",
                    device=0 if _gpu() else -1,
                )
                log.info("Loading Hindi→English translator …")
                hi_tr = hf_pipeline(
                    "translation",
                    model="Helsinki-NLP/opus-mt-hi-en",
                    device=0 if _gpu() else -1,
                )
                log.info("Translation models loaded ✅")
            except Exception as exc:
                log.warning("Translation unavailable: %s", exc)
            _models["translators"] = (si_tr, hi_tr)
    return _models["translators"]


# ─────────────────────────────────────────────────────────────────────────────
# PaliGemma VLM (optional — only loaded when explicitly requested)
# ─────────────────────────────────────────────────────────────────────────────

def get_vlm() -> tuple:
    """Return (processor, model) for PaliGemma 3B, or (None, None)."""
    with _lock:
        if "vlm" not in _models:
            if not HF_TOKEN:
                log.warning("HF_TOKEN not set — VLM unavailable")
                _models["vlm"] = (None, None)
            else:
                try:
                    from huggingface_hub import login
                    from transformers import (
                        AutoProcessor,
                        PaliGemmaForConditionalGeneration,
                    )
                    login(token=HF_TOKEN, add_to_git_credential=False)
                    MODEL_ID = "google/paligemma-3b-mix-448"
                    log.info("Loading PaliGemma 3B (%s) …", MODEL_ID)
                    processor = AutoProcessor.from_pretrained(MODEL_ID)
                    model = PaliGemmaForConditionalGeneration.from_pretrained(
                        MODEL_ID,
                        torch_dtype=torch.bfloat16 if _gpu() else torch.float32,
                        device_map="cuda" if _gpu() else "cpu",
                    ).eval()
                    _models["vlm"] = (processor, model)
                    log.info("PaliGemma loaded ✅")
                except Exception as exc:
                    log.warning("PaliGemma unavailable: %s", exc)
                    _models["vlm"] = (None, None)
    return _models["vlm"]


# ─────────────────────────────────────────────────────────────────────────────
# Convenience bundles
# ─────────────────────────────────────────────────────────────────────────────

def load_phase1_models():
    """Pre-load every model needed for Phase 1 + Phase 2 scanning."""
    get_yolo()
    get_easyocr()
    get_paddleocr()


def load_commentary_models():
    """Pre-load models needed for commentary analysis."""
    get_easyocr()
    get_whisper()
    get_zero_shot()
    get_translators()


def load_vlm_models():
    """Pre-load PaliGemma for VLM card extraction."""
    get_vlm()
