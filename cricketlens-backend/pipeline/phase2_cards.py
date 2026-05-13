"""
pipeline/phase2_cards.py — Phase 2: Find and read dismissal cards.

For each detected wicket event, searches a time window around the event
for frames containing a dismissal card overlay, scores candidate frames,
and stores the best OCR text per wicket.

Output: phase2_cards.csv with one row per wicket.
"""

import logging
from pathlib import Path
from typing import Optional, Callable

import cv2
import pandas as pd

from config import (
    CARD_SAMPLE_INNER_SEC,
    CARD_SAMPLE_OUTER_SEC,
    CARD_INNER_WINDOW_SEC,
    CARD_MAX_WINDOW_SEC,
    CARD_SCORE_THRESHOLD,
    CARD_EARLY_STOP_SCORE,
    CARD_MIN_FRAMES,
)
from pipeline.models import get_yolo, get_easyocr, get_paddleocr
from pipeline.helpers import (
    detect_regions,
    get_card_window,
    get_candidate_regions,
    group_into_windows,
    select_best_card_result,
    score_card_for_scan,
    seconds_to_hhmmss,
    build_ball_change_index,
    detect_innings_boundary,
)

log = logging.getLogger(__name__)


def run_phase2(
    video_path: str,
    output_csv: str,
    df_wickets: pd.DataFrame,
    df_p1: pd.DataFrame,
    fps: float,
    broadcaster: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Search for dismissal-card frames for every event in *df_wickets*.

    If *output_csv* already exists it is loaded directly (idempotent).
    """
    csv_path = Path(output_csv)
    if csv_path.exists():
        log.info("Phase 2 CSV exists — loading %s", csv_path)
        return pd.read_csv(csv_path)

    yolo_model = get_yolo()
    reader     = get_easyocr()
    paddle     = get_paddleocr()

    # Build ball-change index for card-window derivation
    ball_index = build_ball_change_index(df_p1)

    total_events = len(df_wickets)
    phase2_rows  = []

    for i, (_, ev) in enumerate(df_wickets.iterrows()):
        inn          = int(ev["innings"])
        expected_wkt = int(ev["innings_wicket"])

        cap     = cv2.VideoCapture(video_path)
        total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        t_in_s, t_in_e, t_out_e, method = get_card_window(
            ev, df_p1, ball_index, cap, fps
        )

        log.info("Inn%d W%d  [%s]  window [%s→%s|%s]",
                 inn, expected_wkt, method,
                 seconds_to_hhmmss(t_in_s),
                 seconds_to_hhmmss(t_in_e),
                 seconds_to_hhmmss(t_out_e))

        candidates, stopped = _scan_window(
            cap, fps, total_f, t_in_s, t_in_e,
            CARD_SAMPLE_INNER_SEC, broadcaster, yolo_model, reader, paddle,
        )
        if not candidates and t_out_e > t_in_e:
            outer_cands, _ = _scan_window(
                cap, fps, total_f, t_in_e, t_out_e,
                CARD_SAMPLE_OUTER_SEC, broadcaster, yolo_model, reader, paddle,
            )
            candidates.extend(outer_cands)

        cap.release()

        card_windows = group_into_windows(
            candidates, gap_sec=4.0, min_frames=CARD_MIN_FRAMES
        )
        best_lines, best_score, best_fidx, best_source = select_best_card_result(card_windows)

        found   = best_fidx is not None and len(card_windows) > 0
        card_ts = best_fidx / fps if best_fidx else float(ev["last_wicket_ts_sec"])
        lines_str = "|||".join([
            best_lines.get("name_score", ""),
            best_lines.get("dismissal", ""),
            best_lines.get("extra", ""),
        ])

        log.info("  %s  score=%.1f  windows=%d  source=%s",
                 "✅" if found else "⚠️", best_score,
                 len(card_windows), best_source[:30])

        phase2_rows.append({
            "wicket_number"    : int(ev["wicket_number"]),
            "innings"          : inn,
            "innings_wicket"   : expected_wkt,
            "card_ts_sec"      : round(card_ts, 3),
            "card_ts_str"      : seconds_to_hhmmss(card_ts),
            "card_time"        : seconds_to_hhmmss(card_ts),
            "card_frame_idx"   : best_fidx,
            "raw_ocr_text"     : " | ".join(best_lines.values()),
            "card_lines"       : lines_str,
            "ocr_confidence"   : round(min(1.0, best_score / 8.0), 4),
            "scan_zone"        : best_source,
            "struct_score"     : best_score,
            "card_found"       : found,
            "card_found_ocr"   : found,
            "card_found_vlm"   : False,
            "n_card_windows"   : len(card_windows),
            "timing_method"    : method,
            "used_yolo"        : "yolo" in best_source,
            "early_stop"       : stopped,
            "extraction_method": "ocr_regex",
            "vlm_batsman"      : "",
            "vlm_runs"         : None,
            "vlm_balls"        : None,
            "vlm_mode"         : "",
            "vlm_bowler"       : "",
            "vlm_fielder"      : "",
            "vlm_confidence"   : "",
        })

        if progress_cb:
            progress_cb(i / total_events,
                        f"Phase 2: {i + 1}/{total_events} wickets processed")

    df_phase2 = pd.DataFrame(phase2_rows)
    df_phase2.to_csv(csv_path, index=False)

    found_n = df_phase2["card_found"].sum()
    log.info("Phase 2 complete: %d/%d cards found → %s",
             found_n, len(df_phase2), csv_path)

    if progress_cb:
        progress_cb(1.0, f"Phase 2 complete: {found_n}/{len(df_phase2)} cards found")

    return df_phase2


def _scan_window(cap, fps: float, total_f: int,
                 t_start: float, t_end: float,
                 sample_sec: float,
                 broadcaster: str,
                 yolo_model, reader, paddle) -> tuple:
    """Scan a time window, collecting candidate card frames."""
    stride          = max(1, int(fps * sample_sec))
    candidates      = []
    consecutive_hit = 0
    stopped_early   = False

    overlay_cls = {"dismissal_card", "stats_overlay",
                   "hawkeye_graphic", "third_umpire_graphic"}

    for fidx in range(int(t_start * fps),
                      min(total_f, int(t_end * fps)), stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            continue

        detections    = detect_regions(frame, yolo_model)
        yolo_overlay  = bool(overlay_cls & set(detections.keys()))
        frame_hit     = False

        for cand in get_candidate_regions(
                frame, detections, broadcaster, yolo_overlay, reader, paddle):
            s = score_card_for_scan(
                cand["lines"].get("name_score", ""),
                cand["lines"].get("dismissal", ""),
                cand["lines"].get("extra", ""),
            )
            if s >= CARD_SCORE_THRESHOLD:
                candidates.append({
                    "ts"    : fidx / fps,
                    "fidx"  : fidx,
                    "source": cand["source"],
                    "lines" : cand["lines"],
                    "score" : s,
                    "conf"  : cand["conf"],
                })
                if s >= CARD_EARLY_STOP_SCORE:
                    frame_hit = True

        if frame_hit:
            consecutive_hit += 1
            if consecutive_hit >= 2:
                stopped_early = True
                break
        else:
            consecutive_hit = 0

    return candidates, stopped_early
