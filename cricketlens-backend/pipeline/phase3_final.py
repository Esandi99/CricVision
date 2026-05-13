"""
pipeline/phase3_final.py — Build the final wickets CSV (Cell 13 logic).

Re-reads the best card frame with strict OCR, merges VLM output (if
available), corrects names, and writes final_wickets.csv.
"""

import logging
import re
from pathlib import Path
from typing import Optional, Callable

import cv2
import pandas as pd

from config import CARD_ZONES_READ
from pipeline.models import get_easyocr, get_paddleocr
from pipeline.helpers import (
    clean_ocr_text,
    _CARD_METADATA_RE,
    _EXCL_RE,
    classify_dismissal_mode,
    extract_names_from_dismissal,
    extract_clean_suffix,
    correct_player_name,
    fuzzy_correct_name,
    is_garbled,
    load_name_dict,
    crop_zone,
    preprocess_card_crop,
    ocr_ensemble,
    ocr_easyocr,
    seconds_to_hhmmss,
    DISMISSAL_PATTERNS,
)
from rapidfuzz import fuzz, process as rfprocess

log = logging.getLogger(__name__)

# Non-name tokens that sometimes slip into the roster from OCR noise
_KNOWN_NON_NAMES = re.compile(
    r"^(TOSS|CAREER|STRIKE|RATE|ISTRIKE|RATIE|SECOND|CURRENT"
    r"|MATCH|SERIES|LIVE|FROM|WICKET|ECONOMY|AVERAGE)$",
    re.IGNORECASE,
)


def run_phase3(
    video_path: str,
    output_csv: str,
    df_wickets: pd.DataFrame,
    df_phase2: pd.DataFrame,
    name_dict_path: Optional[str],
    broadcaster: str,
    match_id: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Build final_wickets.csv.

    If *output_csv* exists it is loaded directly (idempotent).
    """
    csv_path = Path(output_csv)
    if csv_path.exists():
        log.info("Final CSV exists — loading %s", csv_path)
        return pd.read_csv(csv_path)

    reader = get_easyocr()
    paddle = get_paddleocr()

    name_dict = load_name_dict(name_dict_path) if name_dict_path else {}
    roster    = _build_filtered_roster(df_phase2, name_dict)
    log.info("Roster: %d names", len(roster))

    total = len(df_wickets)
    final_rows = []

    for i, (_, ev) in enumerate(df_wickets.iterrows()):
        p2 = df_phase2[df_phase2["wicket_number"] == ev["wicket_number"]]

        card_found = bool(p2.iloc[0]["card_found"])   if not p2.empty else False
        card_time  = str(p2.iloc[0]["card_time"])     if not p2.empty else ""
        card_ts    = (float(p2.iloc[0]["card_ts_sec"])
                      if not p2.empty and pd.notna(p2.iloc[0]["card_ts_sec"])
                      else None)

        # ── VLM result (if PaliGemma was run) ─────────────────────────────────
        parsed_vlm: dict = {}
        if not p2.empty and p2.iloc[0].get("card_found_vlm", False):
            parsed_vlm = {
                "batsman"        : str(p2.iloc[0].get("vlm_batsman", "")).strip(),
                "runs"           : p2.iloc[0].get("vlm_runs"),
                "balls"          : p2.iloc[0].get("vlm_balls"),
                "dismissal_mode" : str(p2.iloc[0].get("vlm_mode", "")).strip(),
                "bowler"         : str(p2.iloc[0].get("vlm_bowler", "")).strip(),
                "fielder"        : str(p2.iloc[0].get("vlm_fielder", "")).strip(),
                "mode_confidence": 0.95,
            }
            for k in ["batsman", "bowler", "fielder", "dismissal_mode"]:
                if str(parsed_vlm[k]) in ("None", "nan", "null", ""):
                    parsed_vlm[k] = ""
            for k in ["runs", "balls"]:
                try:
                    parsed_vlm[k] = int(parsed_vlm[k]) if pd.notna(parsed_vlm[k]) else None
                except (ValueError, TypeError):
                    parsed_vlm[k] = None

        # ── OCR re-read from best card frame ───────────────────────────────────
        parsed_ocr: dict = {}
        if card_found and not p2.empty:
            fidx     = p2.iloc[0].get("card_frame_idx")
            scan_zone = str(p2.iloc[0].get("scan_zone", broadcaster))
            zone_key  = scan_zone.replace("zone_", "").replace("yolo_", "")
            if zone_key not in CARD_ZONES_READ:
                zone_key = broadcaster if broadcaster in CARD_ZONES_READ else "sporty_lk"

            full_text = ""
            if fidx is not None and not pd.isna(fidx):
                cap     = cv2.VideoCapture(video_path)
                total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fidx_i  = int(float(fidx))
                if fidx_i < total_f:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, fidx_i)
                    ret, frame = cap.read()
                    if ret:
                        zone  = CARD_ZONES_READ[zone_key]
                        crop  = crop_zone(frame, zone)
                        if crop is not None and crop.size > 0:
                            crop      = preprocess_card_crop(crop)
                            full_text = ocr_ensemble(crop, reader, paddle)
                cap.release()

            if full_text.strip():
                parsed_ocr = _parse_card_full_text(full_text, name_dict, roster)
            else:
                # Fallback: use stored card_lines
                lines_str  = str(p2.iloc[0].get("card_lines", ""))
                stored     = " ".join(lines_str.split("|||"))
                parsed_ocr = _parse_card_full_text(stored, name_dict, roster)

        # ── Merge batsman name ─────────────────────────────────────────────────
        ocr_l1_raw = ""
        if card_found and not p2.empty:
            parts      = str(p2.iloc[0].get("card_lines", "")).split("|||")
            ocr_l1_raw = parts[0] if parts else ""

        batsman = _pick_batsman(
            parsed_ocr, parsed_vlm, ocr_l1_raw, roster, name_dict
        )

        # ── Merge runs / balls ─────────────────────────────────────────────────
        runs  = parsed_vlm.get("runs")  if parsed_vlm.get("runs")  is not None \
                else parsed_ocr.get("runs")
        balls = parsed_vlm.get("balls") if parsed_vlm.get("balls") is not None \
                else parsed_ocr.get("balls")
        if pd.notna(ev.get("runs")):  runs  = ev["runs"]
        if pd.notna(ev.get("balls")): balls = ev["balls"]

        # ── Merge dismissal mode ───────────────────────────────────────────────
        ocr_mode  = parsed_ocr.get("dismissal_mode", "")
        ocr_mconf = float(parsed_ocr.get("mode_confidence", 0))
        vlm_mode  = parsed_vlm.get("dismissal_mode", "")

        if ocr_mode and ocr_mconf >= 1.0:
            dismissal_mode  = ocr_mode
            mode_confidence = ocr_mconf
        elif vlm_mode:
            dismissal_mode  = vlm_mode
            mode_confidence = float(parsed_vlm.get("mode_confidence", 0.8))
        elif ocr_mode:
            dismissal_mode  = ocr_mode
            mode_confidence = ocr_mconf
        else:
            dismissal_mode  = ""
            mode_confidence = 0.0

        bowler  = parsed_ocr.get("bowler",  "") or parsed_vlm.get("bowler",  "")
        fielder = parsed_ocr.get("fielder", "") or parsed_vlm.get("fielder", "")

        # ── Extraction-method tag ──────────────────────────────────────────────
        has_vlm = bool(parsed_vlm)
        has_ocr = bool(parsed_ocr)
        if has_vlm and has_ocr:   final_source = "hybrid"
        elif has_vlm:             final_source = "vlm"
        elif has_ocr:             final_source = "ocr"
        else:                     final_source = "none"

        over_str = ""
        if pd.notna(ev.get("over_num")) and ev["over_num"] is not None:
            over_str = (f"{ev['over_num']}.{ev['ball_num']}"
                        if pd.notna(ev.get("ball_num")) else str(ev["over_num"]))

        final_rows.append({
            "match_id"           : match_id,
            "wicket_number"      : int(ev["wicket_number"]),
            "innings"            : int(ev["innings"]),
            "innings_wicket"     : int(ev["innings_wicket"]),
            "score"              : ev["score"],
            "over"               : over_str,
            "wicket_ball_in_over": ev.get("wicket_ball_in_over"),
            "delivery_ts"        : ev["delivery_ts_str"],
            "delivery_ts_sec"    : float(ev["delivery_ts_sec"]),
            "card_ts"            : card_time,
            "card_ts_sec"        : card_ts,
            "batsman"            : batsman,
            "runs"               : runs,
            "balls"              : balls,
            "dismissal_mode"     : dismissal_mode,
            "mode_confidence"    : round(mode_confidence, 3),
            "bowler"             : bowler,
            "fielder"            : fielder,
            "card_found"         : card_found,
            "card_zone"          : p2.iloc[0]["scan_zone"] if not p2.empty else "",
            "strip_source"       : ev["source"],
            "extraction_method"  : final_source,
            "vlm_mode"           : parsed_vlm.get("dismissal_mode", ""),
            "vlm_batsman"        : parsed_vlm.get("batsman", ""),
            "ocr_mode"           : parsed_ocr.get("dismissal_mode", ""),
            "ocr_batsman"        : parsed_ocr.get("batsman", ""),
        })

        if progress_cb:
            progress_cb(i / total, f"Phase 3: {i + 1}/{total} wickets")

    df_final = pd.DataFrame(final_rows)
    df_final.to_csv(csv_path, index=False)

    log.info("Final CSV: %d wickets → %s", len(df_final), csv_path)
    if progress_cb:
        progress_cb(1.0, f"Phase 3 complete: {len(df_final)} wickets")

    return df_final


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_filtered_roster(df_phase2: pd.DataFrame,
                            name_dict: dict) -> list:
    """Extract player names from high-confidence card OCR text."""
    if df_phase2 is None or df_phase2.empty:
        return []
    df_high = df_phase2[df_phase2["card_found"] == True]
    if df_high.empty:
        return []

    from collections import Counter
    word_card_count: dict = {}
    for _, row in df_high.iterrows():
        lines     = str(row.get("card_lines", "")).split("|||")
        card_text = clean_ocr_text(" ".join(lines))
        card_words = set()
        for w in re.findall(r"\b[A-Za-z]{4,}\b", card_text):
            card_words.add(w.upper())
        for w in card_words:
            word_card_count[w] = word_card_count.get(w, 0) + 1

    names = []
    for _, row in df_high.iterrows():
        lines = str(row.get("card_lines", "")).split("|||")
        if not lines:
            continue
        l1    = clean_ocr_text(lines[0]).strip()
        words = l1.split()
        if len(words) > 3:
            continue
        for w in words:
            w_clean = re.sub(r"[^A-Za-z]", "", w).upper()
            if (len(w_clean) >= 4 and w_clean.isalpha()
                    and word_card_count.get(w_clean, 0) >= 1):
                names.append(w_clean)

    counts = Counter(names)
    roster = [w for w, _ in counts.most_common()]
    roster = [w for w in roster
              if not is_garbled(w) and len(w) >= 4
              and not _KNOWN_NON_NAMES.match(w)]
    return roster


def _parse_card_full_text(full_text: str, name_dict: dict,
                          roster: list) -> dict:
    """
    Parse a full card text block into batsman/runs/balls/mode/bowler/fielder.
    Strict parsing (Cell 13 logic).
    """
    result = {
        "dismissal_mode": "", "batsman": "", "bowler": "", "fielder": "",
        "runs": None, "balls": None, "mode_confidence": 0.0,
    }
    text = clean_ocr_text(str(full_text))
    if not text:
        return result

    clean = extract_clean_suffix(text)
    mode, conf = classify_dismissal_mode(clean)
    result["dismissal_mode"]  = mode
    result["mode_confidence"] = conf

    # ECB "Balls Faced X  Y" format (balls first, then runs)
    m_ecb = re.search(r"Balls\s*Faced\s*(\d{1,3})\s+(\d{1,3})",
                      text, re.IGNORECASE)
    if m_ecb:
        result["balls"] = int(m_ecb.group(1))
        result["runs"]  = int(m_ecb.group(2))
    else:
        m = re.search(r"\b(\d{1,3})\s*[\(\[]\s*(\d{1,3})\s*[\)\]]", text)
        if m:
            result["runs"], result["balls"] = int(m.group(1)), int(m.group(2))
        else:
            for m in re.finditer(r"\b(\d{1,3})\s+(\d{1,3})\b", text):
                r_v, b_v = int(m.group(1)), int(m.group(2))
                if 0 <= r_v <= 300 and 1 <= b_v <= 300 and b_v <= r_v * 3 + 10:
                    result["runs"], result["balls"] = r_v, b_v
                    break

    # Candidate name spans before the dismissal suffix
    suffix_start  = text.find(clean) if (clean and clean != text) else len(text)
    pre_dismissal = text[:suffix_start].strip()
    pre_dismissal = re.sub(r"\s*\d[\d\s]*$", "", pre_dismissal).strip()

    def _score_name(name: str) -> float:
        if not name or len(name) < 4:
            return 0
        if is_garbled(name):
            return 0
        dm, dc = classify_dismissal_mode(name)
        if dc >= 1.0:
            return 0
        rs = 0
        if roster:
            r = rfprocess.extractOne(
                name.upper(), roster,
                scorer=fuzz.token_sort_ratio, score_cutoff=0)
            rs = r[1] if r else 0
        return rs + min(len(name) / 20.0, 1.0) * 20

    words      = pre_dismissal.split() if pre_dismissal else text.split()[:6]
    candidates = []
    for start in range(len(words)):
        for length in range(1, 4):
            end = start + length
            if end > len(words):
                break
            span = " ".join(words[start:end])
            span_clean = clean_ocr_text(span).strip()
            span_words = span_clean.split()
            if not span_words:
                continue
            if not all(re.match(r"^[A-Za-z]{3,}$", w) for w in span_words):
                continue
            if re.search(r"\b(lbw|c&b|run|out|stumped)\b", span_clean, re.I):
                continue
            if re.match(r"^[cCbBsS]\s", span_clean):
                continue
            s = _score_name(span_clean)
            if s > 0:
                candidates.append((s, span_clean))

    if candidates:
        candidates.sort(reverse=True)
        best_name = candidates[0][1]
        result["batsman"] = fuzzy_correct_name(
            correct_player_name(best_name, name_dict),
            roster=roster, threshold=65,
        )

    bowler, fielder = extract_names_from_dismissal(clean, mode)
    if mode == "run out" and not fielder:
        m_ro = re.search(
            r"run\s*out\s*[\(\[]?\s*([A-Z][A-Za-z\s]{2,20}?)\s*[\)\]]?",
            text, re.IGNORECASE)
        if m_ro:
            fielder = m_ro.group(1).strip()

    result["bowler"]  = fuzzy_correct_name(
        correct_player_name(bowler,  name_dict), roster=roster, threshold=65)
    result["fielder"] = fuzzy_correct_name(
        correct_player_name(fielder, name_dict), roster=roster, threshold=65)

    return result


def _pick_batsman(parsed_ocr: dict, parsed_vlm: dict,
                  ocr_l1_raw: str, roster: list, name_dict: dict) -> str:
    """Choose the best batsman name from OCR and VLM candidates."""
    ocr_name = parsed_ocr.get("batsman", "")
    vlm_name = parsed_vlm.get("batsman", "")

    if not ocr_name or is_garbled(ocr_name):
        # OCR garbled — prefer VLM if available
        if vlm_name and not is_garbled(vlm_name):
            return fuzzy_correct_name(
                correct_player_name(vlm_name, name_dict), roster=roster, threshold=65)
        # Both garbled — try raw line 1
        raw = re.sub(r"\s*\d.*$", "", clean_ocr_text(str(ocr_l1_raw))).strip()
        if raw and not is_garbled(raw):
            return fuzzy_correct_name(
                correct_player_name(raw, name_dict), roster=roster, threshold=65)
        return ocr_name or ""

    if not vlm_name or is_garbled(vlm_name):
        return ocr_name

    # Both valid — pick the one with the better roster score
    def _roster_score(name: str) -> int:
        if not name or not roster:
            return 0
        r = rfprocess.extractOne(
            name.upper(), roster, scorer=fuzz.token_sort_ratio, score_cutoff=0)
        return r[1] if r else 0

    chosen = ocr_name if _roster_score(ocr_name) >= _roster_score(vlm_name) else vlm_name
    return fuzzy_correct_name(
        correct_player_name(chosen, name_dict), roster=roster, threshold=65)
