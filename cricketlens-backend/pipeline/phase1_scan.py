"""
pipeline/phase1_scan.py — Phase 1: YOLO-first frame scan.

Iterates the video at PHASE1_STRIDE_SEC intervals.
For each sampled frame:
  1. YOLO detects broadcast overlay regions.
  2. PaddleOCR / EasyOCR reads score strip (runs, wickets, over).
  3. Delivery dots are parsed for W markers (circle or text display).
  4. Event-label text ("LAST WICKET") is parsed.
  5. YOLO signal flags are recorded.

Output: a pandas DataFrame saved to phase1_scorestrip.csv.
"""

import logging
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

from config import PHASE1_STRIDE_SEC
from pipeline.models import get_yolo, get_easyocr, get_paddleocr
from pipeline.helpers import (
    detect_regions,
    is_valid_gameplay_frame,
    yolo_crop_score,
    yolo_crop_over,
    yolo_crop_delivery,
    ocr_paddle,
    ocr_easyocr,
    parse_score_robust,
    score_text_is_suspicious,
    parse_over_ball_robust,
    extract_delivery_sequence,
    parse_event_text,
    seconds_to_hhmmss,
    detect_innings_boundary,
    build_ball_change_index,
)

log = logging.getLogger(__name__)


def run_phase1(
    video_path: str,
    output_csv: str,
    broadcaster: str,
    fps: float,
    total_frames: int,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Run Phase 1 scan on *video_path*.

    If *output_csv* already exists it is loaded directly (idempotent).

    Args:
        video_path:    Absolute path to the input video.
        output_csv:    Where to persist the scan results.
        broadcaster:   Broadcaster ID (e.g. "star_sports").
        fps:           Video frame-rate.
        total_frames:  Total frame count.
        progress_cb:   Optional callback(fraction_done, message).

    Returns:
        df_p1 with "innings" and "wickets_filled" columns populated.
    """
    csv_path = Path(output_csv)

    if csv_path.exists():
        log.info("Phase 1 CSV exists — loading %s", csv_path)
        df_p1 = pd.read_csv(csv_path)
        df_p1 = _assign_innings(df_p1)
        return df_p1

    yolo_model = get_yolo()
    reader     = get_easyocr()
    paddle     = get_paddleocr()

    stride  = max(1, int(fps * PHASE1_STRIDE_SEC))
    indices = list(range(0, total_frames, stride))
    total_n = len(indices)
    log.info("Phase 1: scanning %d frames (every %.1fs) …", total_n, PHASE1_STRIDE_SEC)

    rows = []
    cap  = cv2.VideoCapture(video_path)

    for i, fidx in enumerate(tqdm(indices, desc="Phase 1 scan", unit="frame")):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            continue

        ts = fidx / fps

        # ── YOLO ──────────────────────────────────────────────────────────────
        detections  = detect_regions(frame, yolo_model)
        is_gameplay = is_valid_gameplay_frame(detections)

        # ── Score OCR ─────────────────────────────────────────────────────────
        score_crop = yolo_crop_score(frame, detections, broadcaster)
        score_text = ocr_paddle(score_crop, paddle) or ocr_easyocr(score_crop, reader)
        runs, wickets = parse_score_robust(score_text)

        # ── Over number ───────────────────────────────────────────────────────
        over_n, ball_n = None, None
        over_crop = yolo_crop_over(frame, detections)
        if over_crop is not None:
            over_text      = ocr_paddle(over_crop, paddle) or ocr_easyocr(over_crop, reader)
            over_n, ball_n = parse_over_ball_robust(over_text)
        if over_n is None:
            over_n, ball_n = parse_over_ball_robust(score_text)

        # ── Delivery dots ─────────────────────────────────────────────────────
        dots_crop  = yolo_crop_delivery(frame, detections, broadcaster)
        delivery   = extract_delivery_sequence("", dots_crop_bgr=dots_crop, reader=reader)
        dots_text  = ocr_easyocr(dots_crop, reader) if dots_crop is not None else ""

        # ── Event label ───────────────────────────────────────────────────────
        combined_text = score_text + " " + dots_text
        parsed        = parse_event_text(combined_text)

        # ── YOLO event signals ────────────────────────────────────────────────
        rows.append({
            "frame_idx"           : fidx,
            "timestamp_sec"       : round(ts, 3),
            "timestamp_str"       : seconds_to_hhmmss(ts),
            "strip_text"          : combined_text,
            "score_text"          : score_text,
            "dots_text"           : dots_text,
            "runs"                : runs,
            "wickets"             : wickets,
            "over_num"            : over_n,
            "ball_num"            : ball_n,
            "delivery_seq"        : str(delivery["sequence"]),
            "delivery_type"       : delivery.get("display_type", ""),
            "has_w_marker"        : delivery["has_w_marker"],
            "wicket_ball_in_over" : delivery["wicket_ball"],
            "n_circles"           : delivery["n_circles"],
            "has_event"           : parsed is not None,
            "is_gameplay"         : is_gameplay,
            "yolo_wicket"         : "wicket_graphic"       in detections,
            "yolo_boundary"       : "boundary_graphic"     in detections,
            "yolo_card"           : "dismissal_card"       in detections,
            "yolo_replay"         : "replay_indicator"     in detections,
            "yolo_review"         : "third_umpire_graphic" in detections,
            "yolo_classes"        : str(list(detections.keys())),
        })

        if progress_cb and i % 50 == 0:
            progress_cb(i / total_n, f"Phase 1: {i}/{total_n} frames scanned")

    cap.release()

    df_p1 = pd.DataFrame(rows)
    df_p1.to_csv(csv_path, index=False)

    log.info("Phase 1 complete: %d frames, %d readable, %d YOLO wicket signals",
             len(df_p1),
             df_p1["wickets"].notna().sum(),
             df_p1["yolo_wicket"].sum())

    df_p1 = _assign_innings(df_p1)

    if progress_cb:
        progress_cb(1.0, "Phase 1 complete")

    return df_p1


def _assign_innings(df_p1: pd.DataFrame) -> pd.DataFrame:
    """Detect innings boundary and tag every row with innings=1 or 2."""
    df_p1 = df_p1.copy()
    df_p1["wickets_filled"] = df_p1["wickets"].ffill().fillna(0).astype(float)
    df_p1["innings"] = 1

    split_idx = detect_innings_boundary(df_p1)
    if split_idx is not None:
        df_p1.loc[df_p1.index >= split_idx, "innings"] = 2
        log.info("Innings boundary detected at row %d  (%s)",
                 split_idx,
                 df_p1.iloc[split_idx]["timestamp_str"] if "timestamp_str" in df_p1.columns else "")

    return df_p1
