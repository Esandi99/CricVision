"""
pipeline/orchestrator.py — Full CricketLens pipeline runner.

Called from the background task in the API layer.
Runs Phase 1 → Event Extraction → Phase 2 → Phase 3 → Commentary,
updating the Job object with live progress along the way.

Returns a list of EventSchema-compatible dicts for the frontend.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

import cv2

from config import AUDIO_SAMPLE_RATE
from storage.job_store import JobStatus
from pipeline.phase1_scan import run_phase1
from pipeline.events import extract_wicket_events
from pipeline.phase2_cards import run_phase2
from pipeline.phase3_final import run_phase3
from pipeline.commentary import run_commentary_analysis
from pipeline.models import get_easyocr
from pipeline.helpers import auto_detect_broadcaster

log = logging.getLogger(__name__)


def run_full_pipeline(
    job,
    job_store,
    video_path: str,
    job_dir: Path,
    match_id: str,
    run_commentary: bool = True,
    name_dict_path: Optional[str] = None,
):
    """
    Run the full CricketLens pipeline for a single video.

    Updates *job* status / progress throughout.  On completion, sets
    job.events to a list of event dicts ready for the frontend.

    This function is designed to run inside a background thread or
    asyncio thread-pool executor.
    """

    def _progress(fraction: float, message: str):
        job_store.update(job, progress=fraction, message=message)
        log.info("[%s] %.0f%%  %s", match_id, fraction * 100, message)

    try:
        job_store.update(job, status=JobStatus.PROCESSING, message="Initialising…")

        # ── 0. Video metadata ──────────────────────────────────────────────────
        _progress(0.01, "Reading video metadata…")
        cap          = cv2.VideoCapture(video_path)
        fps          = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        if fps <= 0 or total_frames <= 0:
            raise ValueError(f"Cannot read video metadata from {video_path}")

        duration_sec = total_frames / fps
        log.info("Video: fps=%.2f  frames=%d  duration=%.0fs",
                 fps, total_frames, duration_sec)

        # Store duration immediately so SSE stream has it
        job_store.update(job, duration_sec=duration_sec)

        # ── 1. Broadcaster detection ───────────────────────────────────────────
        _progress(0.03, "Detecting broadcaster layout…")
        reader       = get_easyocr()
        broadcaster  = auto_detect_broadcaster(video_path, reader, total_frames, fps)
        log.info("Broadcaster: %s", broadcaster)

        # ── 2. Phase 1 — frame scan ────────────────────────────────────────────
        phase1_csv = str(job_dir / f"{match_id}_phase1_scorestrip.csv")
        job_store.update(job, phase1_csv=phase1_csv)

        def _p1_cb(f, msg):
            _progress(0.03 + f * 0.32, msg)   # 3% – 35%

        df_p1 = run_phase1(
            video_path, phase1_csv, broadcaster, fps, total_frames,
            progress_cb=_p1_cb,
        )

        # ── 3. Wicket event extraction ─────────────────────────────────────────
        _progress(0.36, "Extracting wicket events…")
        df_wickets = extract_wicket_events(df_p1, phase1_csv)
        log.info("Wickets: %d total", len(df_wickets))

        # ── 4. Phase 2 — card search ───────────────────────────────────────────
        phase2_csv = str(job_dir / f"{match_id}_phase2_cards.csv")
        job_store.update(job, phase2_csv=phase2_csv)

        def _p2_cb(f, msg):
            _progress(0.38 + f * 0.22, msg)   # 38% – 60%

        df_phase2 = run_phase2(
            video_path, phase2_csv, df_wickets, df_p1, fps, broadcaster,
            progress_cb=_p2_cb,
        )

        # ── 5. Phase 3 — final CSV ─────────────────────────────────────────────
        final_csv = str(job_dir / f"{match_id}_final_wickets.csv")
        job_store.update(job, final_csv=final_csv)

        def _p3_cb(f, msg):
            _progress(0.62 + f * 0.13, msg)   # 62% – 75%

        df_final = run_phase3(
            video_path, final_csv, df_wickets, df_phase2,
            name_dict_path, broadcaster, match_id,
            progress_cb=_p3_cb,
        )

        # ── 6. Commentary analysis (optional) ─────────────────────────────────
        comm_csv = str(job_dir / f"{match_id}_wicket_commentary.csv")
        job_store.update(job, commentary_csv=comm_csv)

        df_comm = None
        if run_commentary:
            audio_dir = str(job_dir / "audio_clips")

            def _comm_cb(f, msg):
                _progress(0.76 + f * 0.20, msg)   # 76% – 96%

            try:
                df_comm = run_commentary_analysis(
                    video_path, comm_csv, df_final, df_p1,
                    audio_dir, progress_cb=_comm_cb,
                )
                # Merge commentary consensus into df_final where mode was missing
                if df_comm is not None and len(df_comm):
                    df_final = _apply_commentary_fallback(df_final, df_comm)
                    df_final.to_csv(final_csv, index=False)
            except Exception as exc:
                log.warning("Commentary analysis failed (non-fatal): %s", exc)

        # ── 7. Build frontend event list ───────────────────────────────────────
        _progress(0.97, "Building event timeline…")
        # Near-miss CSV path (produced by commentary stage when it runs)
        nm_csv = str(job_dir / f"{match_id}_near_miss_commentary.csv")
        events = _build_event_list(df_final, df_phase2, nm_csv, duration_sec)

        job_store.update(
            job,
            status=JobStatus.DONE,
            progress=1.0,
            message=f"Done — {len(events)} events detected",
            events=events,
            duration_sec=duration_sec,
        )
        log.info("[%s] Pipeline complete.  %d events.", match_id, len(events))

    except Exception as exc:
        log.exception("[%s] Pipeline failed: %s", match_id, exc)
        job_store.update(
            job,
            status=JobStatus.ERROR,
            message=f"Pipeline failed: {exc}",
            error=str(exc),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_commentary_fallback(df_final, df_comm):
    """Fill missing dismissal_mode from commentary consensus."""
    import pandas as pd
    df_final = df_final.copy()
    for _, c_row in df_comm.iterrows():
        wkt_num  = int(c_row["wicket_number"])
        cons     = str(c_row.get("consensus", "")).strip()
        if not cons or cons in ("", "nan", "None"):
            continue
        mask = df_final["wicket_number"] == wkt_num
        if not mask.any():
            continue
        idx = df_final[mask].index[0]
        if not df_final.loc[idx, "dismissal_mode"]:
            df_final.loc[idx, "dismissal_mode"]  = cons
            df_final.loc[idx, "mode_confidence"] = 0.7
            df_final.loc[idx, "extraction_method"] = (
                str(df_final.loc[idx, "extraction_method"]) + "_comm"
            )
    return df_final


def _build_event_list(df_final, df_phase2,
                      nm_csv: str = "",
                      duration_sec: float = 0.0) -> list:
    """
    Convert the final wickets DataFrame + optional near-miss CSV into a list
    of event dicts ready for the frontend.

    Field names follow what the React frontend expects:
        ts_sec          float  — when the delivery was bowled
        ts_end_sec      float  — approx end of the replay window (ts+70s)
        event_id        str
        type            "wicket" | "near_miss"
        innings         int
        innings_wicket  int
        score           "72-3" style string
        over            "15.4" style string or ""
        batsman         str
        runs            int | null
        balls           int | null
        dismissal_mode  str
        bowler          str
        fielder         str
        card_found      bool
        extraction_method str
        confidence      float  0-1
    """
    import pandas as pd
    events = []

    # ── Wicket events ─────────────────────────────────────────────────────────
    for _, row in df_final.iterrows():
        wkt_num = int(row["wicket_number"])
        p2      = df_phase2[df_phase2["wicket_number"] == wkt_num]
        card_ts = None
        if not p2.empty and pd.notna(p2.iloc[0].get("card_ts_sec")):
            card_ts = float(p2.iloc[0]["card_ts_sec"])

        innings        = int(row["innings"])
        innings_wicket = int(row["innings_wicket"])
        ts_sec         = float(row["delivery_ts_sec"])

        events.append({
            "type"             : "wicket",
            "event_id"         : f"W{innings}-{innings_wicket}",
            "wicket_number"    : wkt_num,
            "innings"          : innings,
            "innings_wicket"   : innings_wicket,
            "score"            : str(row.get("score", "")),
            "over"             : str(row.get("over", "")),
            # ── frontend expects ts_sec / ts_end_sec ──
            "ts_sec"           : ts_sec,
            "ts_end_sec"       : min(ts_sec + 70.0,
                                     duration_sec if duration_sec > 0 else ts_sec + 70.0),
            "card_ts_sec"      : card_ts,
            "batsman"          : str(row.get("batsman", "")) or "",
            "runs"             : (int(row["runs"])
                                  if pd.notna(row.get("runs")) else None),
            "balls"            : (int(row["balls"])
                                  if pd.notna(row.get("balls")) else None),
            "dismissal_mode"   : str(row.get("dismissal_mode", "")) or "",
            "bowler"           : str(row.get("bowler", "")) or "",
            "fielder"          : str(row.get("fielder", "")) or "",
            "card_found"       : bool(row.get("card_found", False)),
            "extraction_method": str(row.get("extraction_method", "")),
            "confidence"       : float(row.get("mode_confidence", 0)),
        })

    # ── Near-miss events (from commentary NM CSV if it exists) ────────────────
    import os, re as _re
    if nm_csv and os.path.exists(nm_csv):
        try:
            df_nm = pd.read_csv(nm_csv)
            for i, row in df_nm.iterrows():
                lbl = str(row.get("label", f"NM{i+1}"))
                inn = 2 if lbl.startswith("Inn2") else 1
                nm_n = i + 1
                m = _re.search(r"NM(\d+)", lbl)
                if m:
                    nm_n = int(m.group(1))

                def _ts(v):
                    try:
                        p = [float(x) for x in str(v).strip().split(":")]
                        if len(p) == 3: return p[0]*3600 + p[1]*60 + p[2]
                        if len(p) == 2: return p[0]*60 + p[1]
                        return float(p[0])
                    except:
                        return 0.0

                ts0 = max(0.0, _ts(row.get("event_start", "0:00")) - 5)
                ts1 = _ts(row.get("event_end",   "0:00"))
                if ts1 <= ts0:
                    ts1 = ts0 + 30.0

                events.append({
                    "type"             : "near_miss",
                    "event_id"         : f"NM{inn}_{nm_n}",
                    "innings"          : inn,
                    "nm_number"        : nm_n,
                    "label"            : lbl,
                    "ts_sec"           : ts0,
                    "ts_end_sec"       : ts1 + 10.0,
                    "nm_type"          : str(row.get("med_consensus", "")),
                    "fielding_position": str(row.get("fielding_position", "")),
                    "has_appeal"       : bool(row.get("has_appeal", False)),
                    "has_not_out"      : bool(row.get("has_not_out", False)),
                    "confidence"       : float(row.get("med_zs_conf", 0.0)),
                    "transcript"       : str(row.get("med_transcript", ""))[:300],
                })
        except Exception as exc:
            log.warning("Could not load near-miss CSV (%s): %s", nm_csv, exc)

    events.sort(key=lambda e: e["ts_sec"])
    return events
