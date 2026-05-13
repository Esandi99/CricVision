"""
pipeline/commentary.py — Commentary transcription and classification.

For each wicket window, extracts audio, transcribes with Whisper,
then classifies using regex + zero-shot NLI.  Also detects near-miss
events in the full video using the same classifier.

Output:
    wicket_commentary.csv  — one row per wicket with dismissal classification
    near_miss_commentary.csv — near-miss events (future: signal-driven)
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable

import pandas as pd

from config import (
    AUDIO_SAMPLE_RATE,
    COMMENTARY_PRE_SEC,
    COMMENTARY_POST_SEC,
    WHISPER_MODEL,
)
from pipeline.models import get_whisper, get_zero_shot, get_translators
from pipeline.helpers import (
    seconds_to_hhmmss,
    is_valid_commentary,
    classify_commentary,
    ensure_english,
    detect_language,
)

log = logging.getLogger(__name__)


def run_commentary_analysis(
    video_path: str,
    wicket_output_csv: str,
    df_final: pd.DataFrame,
    df_p1: pd.DataFrame,
    audio_dir: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Transcribe + classify commentary for every wicket.

    Args:
        video_path:        Input video.
        wicket_output_csv: Where to save wicket commentary CSV.
        df_final:          Final wickets DataFrame (from phase3_final).
        df_p1:             Phase 1 scan DataFrame (for YOLO wicket timestamps).
        audio_dir:         Directory for temporary .wav files.
        progress_cb:       Optional progress callback.

    Returns:
        DataFrame with one row per wicket, containing transcript +
        regex/zs/consensus classification and fielding position.
    """
    csv_path = Path(wicket_output_csv)
    if csv_path.exists():
        log.info("Wicket commentary CSV exists — loading %s", csv_path)
        return pd.read_csv(csv_path)

    Path(audio_dir).mkdir(parents=True, exist_ok=True)

    whisper_model = get_whisper(WHISPER_MODEL)
    zero_shot     = get_zero_shot()
    si_tr, hi_tr  = get_translators()

    # Build cricket-specific prompt from known player names
    player_names = _collect_player_names(df_final)
    prompt       = _build_cricket_prompt(player_names)

    total   = len(df_final)
    w_rows  = []

    for i, (_, row) in enumerate(df_final.iterrows()):
        inn     = int(row["innings"])
        inn_wkt = int(row["innings_wicket"])
        del_ts  = float(row["delivery_ts_sec"])
        bat     = str(row.get("batsman", "?"))
        if bat in ("nan", "None", ""):
            bat = "?"

        ts, te = _get_commentary_window(row, df_p1)
        lbl    = f"w{int(row['wicket_number'])}"

        log.info("Inn%d W%d — %s  window [%s → %s]",
                 inn, inn_wkt, bat,
                 seconds_to_hhmmss(ts), seconds_to_hhmmss(te))

        text, elapsed = _transcribe(
            whisper_model, video_path, ts, te, lbl, audio_dir, prompt
        )
        eng_text, lang = ensure_english(text, si_tr, hi_tr)

        result = classify_commentary(eng_text, "wicket", zero_shot)

        # If non-English / invalid, try a second window further along
        if not is_valid_commentary(eng_text, player_names):
            ts2, te2 = del_ts + 90, del_ts + 150
            text2, _ = _transcribe(
                whisper_model, video_path, ts2, te2, lbl + "_retry",
                audio_dir, prompt,
            )
            eng2, lang2 = ensure_english(text2, si_tr, hi_tr)
            if is_valid_commentary(eng2, player_names):
                text, eng_text, lang = text2, eng2, lang2
                result = classify_commentary(eng_text, "wicket", zero_shot)

        w_rows.append({
            "wicket_number"    : int(row["wicket_number"]),
            "innings"          : inn,
            "innings_wicket"   : inn_wkt,
            "card_mode"        : str(row.get("dismissal_mode", "")) or "",
            "transcript"       : text[:400],
            "source_language"  : lang,
            "regex_type"       : result["regex_type"]    or "",
            "zs_type"          : result["zs_type"]       or "",
            "zs_conf"          : float(result["zs_conf"]),
            "consensus"        : result["consensus_type"] or "",
            "has_appeal"       : result["has_appeal"],
            "has_not_out"      : result["has_not_out"],
            "fielding_position": result["fielding_position"] or "",
            "elapsed_sec"      : round(elapsed, 1),
        })

        if progress_cb:
            progress_cb(i / total, f"Commentary: {i + 1}/{total} wickets")

    df_comm = pd.DataFrame(w_rows)
    df_comm.to_csv(csv_path, index=False)
    log.info("Wicket commentary saved → %s", csv_path)

    if progress_cb:
        progress_cb(1.0, "Commentary analysis complete")

    return df_comm


# ─────────────────────────────────────────────────────────────────────────────
# Near-miss detection (placeholder — extends to signal-driven pipeline)
# ─────────────────────────────────────────────────────────────────────────────

def run_near_miss_analysis(
    video_path: str,
    output_csv: str,
    events: list,           # list of {"label", "start_sec", "end_sec"}
    audio_dir: str,
    player_names: list = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Classify audio around near-miss events.
    *events* is a list of dicts with label / start_sec / end_sec.
    """
    csv_path = Path(output_csv)
    if csv_path.exists():
        return pd.read_csv(csv_path)

    Path(audio_dir).mkdir(parents=True, exist_ok=True)

    whisper_model = get_whisper(WHISPER_MODEL)
    zero_shot     = get_zero_shot()
    si_tr, hi_tr  = get_translators()

    prompt = _build_cricket_prompt(player_names or [])
    total  = len(events)
    rows   = []

    for i, ev in enumerate(events):
        label   = ev.get("label", f"event_{i}")
        t_start = max(0.0, float(ev["start_sec"]) - 3)
        t_end   = float(ev["end_sec"]) + 40
        lbl     = re.sub(r"[^a-z0-9]", "_", label.lower())[:20]

        text, elapsed = _transcribe(
            whisper_model, video_path, t_start, t_end, lbl, audio_dir, prompt)
        eng_text, lang = ensure_english(text, si_tr, hi_tr)
        result         = classify_commentary(eng_text, "near_miss", zero_shot)

        rows.append({
            "label"            : label,
            "start_sec"        : ev["start_sec"],
            "end_sec"          : ev["end_sec"],
            "transcript"       : text[:400],
            "source_language"  : lang,
            "regex_type"       : result["regex_type"]    or "",
            "zs_type"          : result["zs_type"]       or "",
            "zs_conf"          : float(result["zs_conf"]),
            "consensus"        : result["consensus_type"] or "",
            "has_appeal"       : result["has_appeal"],
            "has_not_out"      : result["has_not_out"],
            "fielding_position": result["fielding_position"] or "",
        })

        if progress_cb:
            progress_cb(i / total, f"Near-miss: {i + 1}/{total}")

    df_nm = pd.DataFrame(rows)
    df_nm.to_csv(csv_path, index=False)
    return df_nm


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_commentary_window(ev, df_p1: pd.DataFrame) -> tuple:
    """Derive best commentary window using YOLO wicket_graphic signal."""
    score_ts = float(ev["delivery_ts_sec"])
    inn      = int(ev["innings"])
    if "yolo_wicket" in df_p1.columns:
        wkt_frames = df_p1[
            (df_p1["timestamp_sec"] >= score_ts - 180) &
            (df_p1["timestamp_sec"] <= score_ts + 5)   &
            (df_p1["yolo_wicket"] == True)              &
            (df_p1["innings"] == inn)
        ]
        if not wkt_frames.empty:
            actual_ts = float(wkt_frames.iloc[0]["timestamp_sec"])
            return max(0.0, actual_ts - COMMENTARY_PRE_SEC), actual_ts + COMMENTARY_POST_SEC
    return max(0.0, score_ts - COMMENTARY_PRE_SEC), score_ts + COMMENTARY_POST_SEC


def _extract_audio(video_path: str, t_start: float, t_end: float,
                   label: str, audio_dir: str) -> Optional[str]:
    out_path = os.path.join(audio_dir, f"{label}_{int(t_start)}.wav")
    if os.path.exists(out_path):
        return out_path
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0, t_start)),
        "-to", str(t_end),
        "-i", video_path,
        "-vn", "-ar", str(AUDIO_SAMPLE_RATE), "-ac", "1", "-f", "wav",
        out_path,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path if r.returncode == 0 else None


def _transcribe(whisper_model, video_path: str,
                t_start: float, t_end: float,
                label: str, audio_dir: str,
                prompt: str) -> tuple:
    wav = _extract_audio(video_path, t_start, t_end, label, audio_dir)
    if not wav:
        return "", 0.0
    t0  = time.time()
    try:
        res = whisper_model.transcribe(
            wav, initial_prompt=prompt, language="en", temperature=0.0)
        return res["text"].strip(), time.time() - t0
    except Exception as exc:
        log.warning("Whisper transcription failed: %s", exc)
        return "", time.time() - t0


def _collect_player_names(df_final: pd.DataFrame,
                           max_names: int = 25) -> list:
    _NON_NAME_RE = re.compile(
        r"HFC|VGO|TEL|TPI|NATIOH|SERIES|MOBILE|NATIONAL|MATCH|\d{4}",
        re.IGNORECASE,
    )
    names = []
    for col in ["batsman", "bowler", "fielder"]:
        if col not in df_final.columns:
            continue
        for n in df_final[col].dropna():
            n = str(n).strip()
            if n in ("", "nan", "—", "None"):
                continue
            if _NON_NAME_RE.search(n):
                continue
            for part in n.split():
                if len(part) >= 4 and part.isalpha():
                    names.append(part.upper())
    seen, clean = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            clean.append(n)
    return clean[:max_names]


def _build_cricket_prompt(player_names: list) -> str:
    base = (
        "Cricket match commentary. "
        + (f"Players: {', '.join(player_names)}. " if player_names else "")
        + "Terms: LBW, DRS, no ball, caught behind, stumped, run out, bowled, "
        "caught at slip, gully, mid-wicket, fine leg, third man, cover, point, "
        "square leg, long on, long off, outside edge, inside edge, appeal, "
        "not out, umpire's call, pitching outside leg, hitting leg stump, "
        "review retained, review overturned, direct hit, short of his ground, "
        "chipped back, simple catch, through the gate, clean bowled."
    )
    return base
