"""
pipeline/helpers.py — CricketLens pure helper functions.

Every function here is stateless (no model references).  Models are
injected via the `reader`, `paddle`, `region_model` parameters where
needed, or fetched from pipeline.models inside the callers.

Sections:
  1. Time / string utilities
  2. Image pre-processing
  3. OCR wrappers (EasyOCR, PaddleOCR, ensemble)
  4. Broadcaster detection
  5. Frame-crop helpers
  6. Score / over / delivery-dots parsing
  7. Innings-boundary detection
  8. YOLO region filtering
  9. Dismissal card scoring & parsing
 10. Name correction / fuzzy matching
 11. Card window helpers
 12. VLM card extraction
 13. Commentary helpers
"""

import re
import json
import logging
from datetime import timedelta
from typing import Optional

import cv2
import numpy as np
from rapidfuzz import fuzz, process

from config import (
    BROADCASTER_CROPS,
    CARD_ZONES,
    CARD_ZONES_READ,
    YOLO_CLASSES,
    YOLO_CONF_THRESHOLD,
)

log = logging.getLogger(__name__)


# =============================================================================
# 1. Time / string utilities
# =============================================================================

def seconds_to_hhmmss(sec: float) -> str:
    return str(timedelta(seconds=float(sec)))


def hhmmss_to_seconds(s: str) -> float:
    parts = s.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(s)


# =============================================================================
# 2. Image pre-processing
# =============================================================================

def preprocess_for_ocr(img_bgr: np.ndarray, target_width: int = 800) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    if w < target_width:
        scale   = target_width / w
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)),
                             interpolation=cv2.INTER_CUBIC)
    kernel    = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharpened = cv2.filter2D(img_bgr, -1, kernel)
    lab       = cv2.cvtColor(sharpened, cv2.COLOR_BGR2LAB)
    l, a, b   = cv2.split(lab)
    l         = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def preprocess_card_crop(img_bgr: np.ndarray) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    if h < 80:
        scale   = 80 / h
        img_bgr = cv2.resize(img_bgr, (int(w * scale), 80),
                             interpolation=cv2.INTER_LANCZOS4)
    img_bgr = cv2.fastNlMeansDenoisingColored(img_bgr, None, 5, 5, 7, 15)
    lab     = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l       = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(l)
    img_bgr = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    blur    = cv2.GaussianBlur(img_bgr, (0, 0), 1.5)
    return cv2.addWeighted(img_bgr, 1.4, blur, -0.4, 0)


def frame_diff_score(frame1: Optional[np.ndarray],
                     frame2: Optional[np.ndarray],
                     resize_to: tuple = (160, 90)) -> float:
    if frame1 is None or frame2 is None:
        return 255.0
    f1   = cv2.resize(frame1, resize_to)
    f2   = cv2.resize(frame2, resize_to)
    diff = cv2.absdiff(cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY),
                       cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY))
    return float(diff.mean())


# =============================================================================
# 3. OCR wrappers
# =============================================================================

def ocr_easyocr(img_bgr: np.ndarray, reader, **kwargs) -> str:
    if img_bgr is None or img_bgr.size == 0:
        return ""
    try:
        return " ".join(reader.readtext(
            cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB), detail=0, **kwargs))
    except Exception:
        return ""


def ocr_paddle(img_bgr: np.ndarray, paddle_instance) -> str:
    if img_bgr is None or img_bgr.size == 0:
        return ""
    if paddle_instance is None:
        return ""
    try:
        r = paddle_instance.ocr(img_bgr, cls=False)
        if not r or not r[0]:
            return ""
        return " ".join(line[1][0] for line in r[0] if line[1][1] > 0.3)
    except Exception:
        return ""


def ocr_ensemble(img_bgr: np.ndarray, reader, paddle_instance, **kwargs) -> str:
    if img_bgr is None or img_bgr.size == 0:
        return ""
    easy   = ocr_easyocr(img_bgr, reader, **kwargs)
    paddle = ocr_paddle(img_bgr, paddle_instance)
    # prefer whichever produced more alpha characters
    return (easy if len(re.sub(r"[^A-Za-z]", "", paddle)) <=
            len(re.sub(r"[^A-Za-z]", "", easy)) else paddle)


# =============================================================================
# 4. Broadcaster detection
# =============================================================================

_SCORE_RE = re.compile(r"\b(\d{1,3})\s*[-:.,|\/]\s*(\d{1,2})\b"
                       r"|\b(\d{1,3})\s+(\d{1,2})\b")

def count_circles_in_region(img_bgr: np.ndarray,
                             min_circularity: float = 0.65) -> int:
    if img_bgr is None or img_bgr.size == 0:
        return 0
    try:
        gray      = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        blur      = cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        img_area = img_bgr.shape[0] * img_bgr.shape[1]
        count    = 0
        for cnt in contours:
            a = cv2.contourArea(cnt)
            if not (img_area * 0.003 < a < img_area * 0.20):
                continue
            p = cv2.arcLength(cnt, True)
            if p == 0:
                continue
            if 4 * np.pi * a / (p * p) >= min_circularity:
                count += 1
        return count
    except Exception:
        return 0


def detect_broadcaster_from_frame(frame_bgr: np.ndarray, reader) -> str:
    """
    Identify broadcaster by reading corner logos + score strip layout.
    Returns one of: star_sports, ecb, nzc, talent_tv, sporty_lk, unknown.
    """
    h, w = frame_bgr.shape[:2]
    corners = {
        "top_left" : frame_bgr[0:int(h * 0.12), 0:int(w * 0.20)],
        "top_right": frame_bgr[0:int(h * 0.12), int(w * 0.80):w],
        "bot_left" : frame_bgr[int(h * 0.85):h,  0:int(w * 0.15)],
    }
    for crop in corners.values():
        if crop.size == 0:
            continue
        try:
            text = " ".join(reader.readtext(
                cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), detail=0)).upper()
            if re.search(r"SPORTY",                text): return "sporty_lk"
            if re.search(r"\bECB\b|ECB\.CO\.UK",   text): return "ecb"
            if re.search(r"\bNZC\b|SPARK\s*SPORT",  text): return "nzc"
            if re.search(r"STAR\s*SPORTS",           text): return "star_sports"
            if re.search(r"TALENT|SRI\s*LANKA\s*CRICKET", text): return "talent_tv"
        except Exception:
            pass

    # Fallback: score strip position analysis
    full_strip = frame_bgr[int(h * 0.85):h, 0:w]
    strip_h, strip_w = full_strip.shape[:2]

    SCORE_RE   = re.compile(r"\b(\d{1,3})\s*[-\/]\s*(\d{1,2})\b")
    thirds     = {
        "left"  : full_strip[:, :strip_w // 3, :],
        "centre": full_strip[:, strip_w // 3:2 * strip_w // 3, :],
        "right" : full_strip[:, 2 * strip_w // 3:, :],
    }
    score_positions = {}
    for pos, crop in thirds.items():
        if crop.size == 0:
            continue
        try:
            text = " ".join(reader.readtext(
                cv2.cvtColor(crop, cv2.COLOR_BGR2RGB), detail=0))
            m = SCORE_RE.search(text)
            if m:
                r_v, wk = int(m.group(1)), int(m.group(2))
                if wk <= 10 and r_v <= 500 and not (wk == 0 and r_v <= 5):
                    score_positions[pos] = (r_v, wk)
        except Exception:
            pass

    right_third       = full_strip[:, 2 * strip_w // 3:, :]
    right_has_circles = count_circles_in_region(right_third) >= 2
    try:
        rt_text = " ".join(reader.readtext(
            cv2.cvtColor(right_third, cv2.COLOR_BGR2RGB), detail=0))
    except Exception:
        rt_text = ""

    has_text_delivery = bool(re.search(r"[Tt]his\s+[Oo]ver|THIS\s+OVER", rt_text))
    has_over_fraction = bool(re.search(r"\d{1,2}[\.\\/]\d", rt_text))

    if score_positions.get("left") and has_text_delivery: return "ecb"
    if score_positions.get("left") and has_over_fraction: return "ecb"
    if score_positions.get("left") and right_has_circles: return "nzc"
    if score_positions.get("left"):                       return "ecb"
    if score_positions.get("centre"):                     return "star_sports"

    return "unknown"


def auto_detect_broadcaster(video_path: str, reader,
                             total_frames: int, fps: float) -> str:
    """Majority-vote broadcaster detection using frames at 10%–70% of video."""
    from collections import Counter
    votes  = []
    cap    = cv2.VideoCapture(video_path)
    for pct in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * pct))
        ret, frame = cap.read()
        if not ret:
            continue
        if cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean() < 25:
            continue
        votes.append(detect_broadcaster_from_frame(frame, reader))
        if len(votes) >= 5:
            break
    cap.release()
    if not votes:
        return "star_sports"
    counts      = Counter(votes)
    broadcaster = counts.most_common(1)[0][0]
    if broadcaster == "unknown" and len(counts) > 1:
        for bc, _ in counts.most_common():
            if bc != "unknown":
                return bc
    return broadcaster


# =============================================================================
# 5. Frame-crop helpers
# =============================================================================

def crop_score_strip(frame_bgr: np.ndarray, broadcaster: str) -> np.ndarray:
    cfg  = BROADCASTER_CROPS.get(broadcaster, BROADCASTER_CROPS["unknown"])
    h, w = frame_bgr.shape[:2]
    y1   = int(h * (1.0 - cfg["bottom"]))
    x1, x2 = int(w * cfg["score"][0]), int(w * cfg["score"][1])
    return frame_bgr[y1:h, x1:x2]


def crop_delivery_dots(frame_bgr: np.ndarray, broadcaster: str) -> np.ndarray:
    cfg  = BROADCASTER_CROPS.get(broadcaster, BROADCASTER_CROPS["unknown"])
    h, w = frame_bgr.shape[:2]
    y1   = int(h * (1.0 - cfg["bottom"]))
    x1, x2 = int(w * cfg["dots"][0]), int(w * cfg["dots"][1])
    return frame_bgr[y1:h, x1:x2]


def crop_full_bottom_strip(frame_bgr: np.ndarray, broadcaster: str) -> np.ndarray:
    cfg  = BROADCASTER_CROPS.get(broadcaster, BROADCASTER_CROPS["unknown"])
    h, w = frame_bgr.shape[:2]
    y1   = int(h * (1.0 - cfg["bottom"]))
    return frame_bgr[y1:h, 0:w]


def crop_zone(frame: np.ndarray, ratios: tuple) -> np.ndarray:
    """Crop using (top, bottom, left, right) as fractions."""
    t, b, l, r = ratios
    h, w = frame.shape[:2]
    return frame[int(h * t):int(h * b), int(w * l):int(w * r)]


def crop_from_bbox(frame_bgr: np.ndarray, bbox: list, pad_px: int = 4) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    x1 = max(0, int(bbox[0]) - pad_px)
    y1 = max(0, int(bbox[1]) - pad_px)
    x2 = min(w, int(bbox[2]) + pad_px)
    y2 = min(h, int(bbox[3]) + pad_px)
    return frame_bgr[y1:y2, x1:x2]


def is_strip_zone_bbox(bbox: list, frame_h: int, strip_threshold: float = 0.82) -> bool:
    y_center = (bbox[1] + bbox[3]) / 2
    return y_center > frame_h * strip_threshold


# =============================================================================
# 6. Score / over / delivery-dots parsing
# =============================================================================

_SCORE_FUZZY_RE = re.compile(
    r"\b(\d{1,3})\s*[-:.,|\/]\s*(\d{1,2})\b"
    r"|\b(\d{1,3})\s+(\d{1,2})\b"
)
_SUSPICIOUS_SCORE_RE = re.compile(
    r"\bRATE\b|\bBOUNDARIES\b|\bFOURS\b|\bSIXES\b|\bKPH\b"
    r"|\bNEED\b|\bTARGET\b|\bMORE\b|\bBALLS\b|\bRUN\s*RATE\b"
    r"|\bSECOND\s*T20\b|\bLIVE\s*FROM\b",
    re.IGNORECASE,
)

def score_text_is_suspicious(text: str) -> bool:
    return bool(_SUSPICIOUS_SCORE_RE.search(str(text)))


def parse_score_robust(text: str) -> tuple:
    """Return (runs, wickets) or (None, None)."""
    text    = str(text)
    matches = _SCORE_FUZZY_RE.findall(text)
    valid   = []
    for g1, g2, g3, g4 in matches:
        r = int(g1 or g3)
        w = int(g2 or g4)
        if w > 10 or r > 500:
            continue
        if 0 < r <= 5 and w == 0:
            continue
        valid.append((r, w))
    if not valid:
        return None, None
    return max(valid, key=lambda x: x[0])


def _normalise_over_text(text: str) -> str:
    t = str(text)
    t = re.sub(r"\bP[z12]\b\s*", "", t)
    t = re.sub(r"(?<=\d)O(?=\d)", "0", t)
    t = re.sub(r"(?<=\d)O(?=\s)", "0", t)
    t = re.sub(r"(?<=\s)O(?=\d)", "0", t)
    t = re.sub(r"(\d)l(\d)", r"\1/\2", t)
    return t


def parse_over_ball_robust(text: str) -> tuple:
    """Return (over_num, ball_num) or (None, None)."""
    text = _normalise_over_text(str(text))
    m = re.search(r"(?<!\d)(\d{1,2})\.([0-6])(?:\s*[\/\\]\s*\d+)?(?!\d)", text)
    if m:
        o, b = int(m.group(1)), int(m.group(2))
        if 0 <= o <= 50 and 0 <= b <= 6:
            return o, b
    m = re.search(r"(?<!\d)(\d{1,2}),([0-6])(?!\d)", text)
    if m:
        o, b = int(m.group(1)), int(m.group(2))
        if 0 <= o <= 50 and 0 <= b <= 6:
            return o, b
    return None, None


_DOT_MAP = {
    "w": "W", "(w)": "W", "o": ".", "○": ".", "q": ".", "0": ".", "•": ".",
    "4": "4", "6": "6",
    "lb": "Lb", "nb": "Nb", "wd": "Wd", "b": "B",
}
_SKIP_WORDS = {
    "this", "over", "kph", "rate", "run", "second", "t20", "t20i",
    "live", "from", "that", "the", "and", "p1", "p2", "p3", "s",
    "innings", "first", "third", "powerplay", "pp", "last", "super",
}


def parse_text_delivery_sequence(text: str) -> tuple:
    tokens   = str(text).split()
    sequence = []
    wkt_ball = None
    in_seq   = False
    for tok in tokens:
        tc = tok.lower().strip("()[].")
        if tc in _SKIP_WORDS:
            continue
        if tc in {"0", "1", "2", "3", "4", "5", "6"}:
            sequence.append("." if tc == "0" else tc)
            in_seq = True
        elif tc == "w":
            sequence.append("W")
            if wkt_ball is None:
                wkt_ball = len(sequence)
            in_seq = True
        elif tc in {"lb", "nb", "wd", "b"}:
            sequence.append(tc.capitalize())
            in_seq = True
        elif in_seq and len(tc) > 4:
            break
    return sequence, wkt_ball


def detect_delivery_circles(dots_crop_bgr: np.ndarray) -> dict:
    """
    Count and classify coloured circles in the delivery dots region.
    Returns a rich dict with sequence, wicket_ball, n_circles, etc.
    """
    empty = {
        "sequence": [], "wicket_ball": None, "has_w_marker": False,
        "n_circles": 0, "_candidates": [], "_scale": 1.0,
        "_y_start": 0, "_x_end": 0,
    }
    if dots_crop_bgr is None or dots_crop_bgr.size == 0:
        return empty
    h, w        = dots_crop_bgr.shape[:2]
    y_start     = int(h * 0.30)
    x_end       = int(w * 0.75)
    search_reg  = dots_crop_bgr[y_start:h, :x_end, :]
    cr_h, cr_w  = search_reg.shape[:2]
    scale       = max(1.0, 400 / max(cr_w, 1))
    img         = cv2.resize(search_reg, (int(cr_w * scale), int(cr_h * scale)),
                             interpolation=cv2.INTER_CUBIC)
    gray        = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur        = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh   = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area    = img.shape[0] * img.shape[1]
    candidates  = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.01 or area > img_area * 0.20:
            continue
        perim = cv2.arcLength(cnt, True)
        if perim == 0:
            continue
        if 4 * np.pi * area / (perim * perim) < 0.72:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(cnt)
        candidates.append({"cx": cx, "cy": cy, "radius": radius, "area": area,
                            "circularity": 4 * np.pi * area / (perim * perim)})
    if len(candidates) > 1:
        med_r      = sorted(c["radius"] for c in candidates)[len(candidates) // 2]
        candidates = [c for c in candidates if 0.4 * med_r <= c["radius"] <= 2.5 * med_r]
    candidates.sort(key=lambda c: c["cx"])
    merged = []
    for c in candidates:
        if merged and abs(c["cx"] - merged[-1]["cx"]) < c["radius"] * 1.5:
            if c["circularity"] > merged[-1]["circularity"]:
                merged[-1] = c
        else:
            merged.append(c)
    sequence = []
    wkt_ball = None
    for i, c in enumerate(merged):
        cx, cy, r = int(c["cx"]), int(c["cy"]), int(c["radius"])
        mask      = np.zeros(gray.shape, dtype=np.uint8)
        cv2.circle(mask, (cx, cy), max(1, r - 3), 255, -1)
        mean_gray  = cv2.mean(gray, mask=mask)[0]
        mean_color = cv2.mean(img,  mask=mask)[:3]
        is_red     = mean_color[2] > 120 and mean_color[2] > mean_color[0] * 1.3
        if is_red:
            sequence.append("W")
            wkt_ball = i + 1
        elif mean_gray < 100:
            sequence.append("x")
        elif mean_gray > 155:
            sequence.append(".")
        else:
            sequence.append("?")
    return {
        "sequence": sequence, "wicket_ball": wkt_ball,
        "has_w_marker": wkt_ball is not None,
        "n_circles": len(merged), "_candidates": merged,
        "_scale": scale, "_y_start": y_start, "_x_end": x_end,
    }


def extract_delivery_sequence(dots_text: str,
                               dots_crop_bgr: Optional[np.ndarray] = None,
                               reader=None) -> dict:
    ocr_text = str(dots_text)
    if dots_crop_bgr is not None and reader is not None:
        try:
            ocr_text = ocr_easyocr(dots_crop_bgr, reader)
        except Exception:
            pass

    display_type = "text"
    if dots_crop_bgr is not None:
        cr = detect_delivery_circles(dots_crop_bgr)
        if cr["n_circles"] >= 1:
            display_type = "circles"

    if display_type == "circles":
        result = detect_delivery_circles(dots_crop_bgr)
        return {
            "sequence":     result["sequence"],
            "wicket_ball":  result["wicket_ball"],
            "has_w_marker": result["has_w_marker"],
            "n_circles":    result["n_circles"],
            "display_type": "circles",
            "_candidates":  result["_candidates"],
            "_scale":       result["_scale"],
            "_y_start":     result["_y_start"],
            "_x_end":       result["_x_end"],
        }
    sequence, wkt_ball = parse_text_delivery_sequence(ocr_text)
    return {
        "sequence":     sequence,
        "wicket_ball":  wkt_ball,
        "has_w_marker": wkt_ball is not None,
        "n_circles":    0,
        "display_type": "text",
        "_candidates":  [],
        "_scale":       1.0,
        "_y_start":     0,
        "_x_end":       0,
    }


# =============================================================================
# 7. Innings-boundary detection
# =============================================================================

def detect_innings_boundary(df) -> Optional[int]:
    """
    Return the row index at which innings 2 starts, or None for single-innings.
    Uses (in priority order):
      1. "CHASE" / "TARGET" keyword in strip text
      2. Wicket count drop from ≥5 → ≤1
      3. Score reset (runs drop heavily with low wicket count)
      4. Over number reset
      5. Long blank strip (>3 min)
    """
    import pandas as pd
    df   = df.copy()
    df["wf"] = df["wickets"].ffill().fillna(0).astype(int)
    df["rf"] = df["runs"].ffill().fillna(0).astype(float)
    mid  = len(df) // 2

    CHASE_RE = re.compile(
        r"\bTARGET\b|\bNEED\s+\d|\bREQUIRED\s+RUN|\bCHASING\b"
        r"|\bTO\s+WIN\b|\bRUN\s+RATE\s+REQUIRED\b",
        re.IGNORECASE,
    )
    for i in range(mid, len(df)):
        if CHASE_RE.search(str(df.iloc[i]["strip_text"])):
            j = i
            while j > mid and CHASE_RE.search(str(df.iloc[j - 1]["strip_text"])):
                j -= 1
            # Find the actual wicket-reset point
            for k in range(j, max(j - 3000, mid), -1):
                curr_wf = int(df.iloc[k]["wf"])
                prev_wf = int(df.iloc[k - 1]["wf"]) if k > 0 else 0
                if curr_wf <= 1 and prev_wf >= 3:
                    return k
            return j

    for i in range(mid + 1, len(df)):
        if int(df.iloc[i]["wf"]) <= 1 and int(df.iloc[i - 1]["wf"]) >= 5:
            return i

    for i in range(mid + 1, len(df)):
        curr_r = float(df.iloc[i]["rf"])
        prev_r = float(df.iloc[i - 1]["rf"])
        curr_w = int(df.iloc[i]["wf"])
        if curr_r <= 5 and prev_r >= 50 and curr_w <= 2:
            return i

    if "over_num" in df.columns:
        df["of"] = df["over_num"].ffill().fillna(0).astype(float)
        for i in range(mid + 1, len(df)):
            if float(df.iloc[i]["of"]) <= 1.0 and float(df.iloc[i - 1]["of"]) >= 15.0:
                return i

    df["blank"] = df["strip_text"].isna() | (df["strip_text"].str.len() < 5)
    blank_start = None
    for i in range(mid, len(df)):
        if df.iloc[i]["blank"]:
            if blank_start is None:
                blank_start = i
        else:
            if blank_start is not None:
                dur = (df.iloc[i]["timestamp_sec"] -
                       df.iloc[blank_start]["timestamp_sec"])
                if dur > 180:
                    return i
                blank_start = None

    return None


def build_ball_change_index(df_p1):
    """Build a table of delivery timestamps derived from over.ball changes."""
    import pandas as pd
    df = df_p1.dropna(subset=["over_num", "ball_num"]).copy()
    df = df.sort_values("timestamp_sec").reset_index(drop=True)
    df["over_ball_float"] = df["over_num"] + df["ball_num"] / 10.0
    df["prev_ob"]         = df["over_ball_float"].shift(1)
    df["ob_diff"]         = df["over_ball_float"] - df["prev_ob"]
    deliveries = df[
        (df["ob_diff"] > 0.05) &
        (df["ob_diff"] < 1.0)  &
        (df["innings"] == df["innings"].shift(1))
    ].copy()
    deliveries = deliveries.rename(columns={"timestamp_sec": "delivery_end_sec"})
    return deliveries[
        ["delivery_end_sec", "over_num", "ball_num", "over_ball_float", "innings"]
    ].reset_index(drop=True)


# =============================================================================
# 8. YOLO region filtering
# =============================================================================

def detect_regions(frame_bgr: np.ndarray, yolo_model,
                   conf: Optional[float] = None) -> dict:
    """
    Run YOLO on a frame.  Returns {class_name: {bbox, conf}}.
    Applies post-processing filters for known false positives.
    """
    threshold = conf or YOLO_CONF_THRESHOLD
    h, w      = frame_bgr.shape[:2]
    results   = yolo_model(frame_bgr, conf=threshold, verbose=False)[0]
    detections: dict = {}
    for box in results.boxes:
        cls_name = YOLO_CLASSES.get(int(box.cls), "unknown")
        bbox     = box.xyxy[0].tolist()
        score    = float(box.conf)
        if cls_name not in detections or score > detections[cls_name]["conf"]:
            detections[cls_name] = {"bbox": bbox, "conf": score}

    # Filter 1: dismissal_card in bottom 20% = ad banner
    if "dismissal_card" in detections:
        y_center = (detections["dismissal_card"]["bbox"][1] +
                    detections["dismissal_card"]["bbox"][3]) / 2
        if y_center > h * 0.80:
            del detections["dismissal_card"]

    # Filter 2: score_box on the right = bowler stats panel
    if "score_box" in detections:
        x_center = (detections["score_box"]["bbox"][0] +
                    detections["score_box"]["bbox"][2]) / 2
        if x_center > w * 0.60:
            del detections["score_box"]

    return detections


def is_valid_gameplay_frame(detections: dict) -> bool:
    classes      = set(detections.keys())
    has_logo     = "broadcaster_logo" in classes
    has_gameplay = bool(classes & {
        "score_box", "over_box", "delivery_region",
        "wicket_graphic", "boundary_graphic",
        "dismissal_card", "bowler_box",
    })
    if has_logo and not has_gameplay and len(classes) <= 2:
        return False
    return True


def yolo_crop_score(frame_bgr: np.ndarray, detections: dict,
                    broadcaster: str) -> np.ndarray:
    if "score_box" in detections:
        return crop_from_bbox(frame_bgr, detections["score_box"]["bbox"])
    return crop_score_strip(frame_bgr, broadcaster)


def yolo_crop_over(frame_bgr: np.ndarray,
                   detections: dict) -> Optional[np.ndarray]:
    if "over_box" in detections:
        return crop_from_bbox(frame_bgr, detections["over_box"]["bbox"])
    return None


def yolo_crop_delivery(frame_bgr: np.ndarray, detections: dict,
                       broadcaster: str) -> np.ndarray:
    if "delivery_region" in detections:
        return crop_from_bbox(frame_bgr, detections["delivery_region"]["bbox"])
    return crop_delivery_dots(frame_bgr, broadcaster)


# =============================================================================
# 9. Dismissal card scoring & parsing
# =============================================================================

_WATERMARK_RE = re.compile(
    r"\bww+[a-z0-9\._\-]{2,}\b"
    r"|\b\w{3,}\.(lk|com|net|org|tv|co)\b"
    r"|©\s*\S*"
    r"|\bcopyright\b"
    r"|\.\s*(lk|com|net|org|tv)\b",
    re.IGNORECASE,
)
_LOGO_RE = re.compile(
    r"\b(sporty|1xbet|melbat|hotstar|starsports|willow)\b",
    re.IGNORECASE,
)
_CARD_METADATA_RE = re.compile(
    r"\bSTRIKE\s*RATE\b|\bECONOMY\b|\b\d{2,3}\s*KPH\b|\bRUN\s*RATE\b"
    r"|\bCURRENT\b|\bTHIS\s+OVER\b|\bT20I?\b|\bODI\b|\bTEST\b"
    r"|\bCAREER\b|\bMATCHES\b|\bWICKETS\b|\bAVERAGE\b|\bSECOND\b"
    r"|\bFALL\s+OF\s+WICKET\b|\bBALLS\s+FACED\b",
    re.IGNORECASE,
)
_DRS_RE = re.compile(
    r"\bDRS\s*TIMER\b|\bREVIEWS?\s+REMAINING\b"
    r"|\bOVERS?\s+REMAINING\b|\bDRS\s+\d\b",
    re.IGNORECASE,
)
_EXCL_RE = re.compile(
    r"LAST\s+WICKET|FALL\s+OF\s+WICKET|CAREER|AVERAGE|ECONOMY|STATISTICS"
    r"|RUN\s*RATE\s*[\d\.]|PARTNERSHIP|PROJECTED|REPLACES\s+[A-Z]"
    r"|LIVE\s*FROM|REQUIRED\s+RUN|DECISION|THIS\s*OVER|RPO\s+\d|REQ\s*RATE",
    re.IGNORECASE,
)

DISMISSAL_PATTERNS = [
    ("caught & bowled",
     re.compile(r"c\s*[&+]\s*b\b|caught\s*[&+]\s*bowl", re.I)),
    ("stumped",
     re.compile(r"\bst\.?\s+[A-Z]|\bstump", re.I)),
    ("run out",
     re.compile(r"run\s*out|\bro\b", re.I)),
    ("lbw",
     re.compile(r"\blbw\b|\bl\.b\.w|\blb\s*w\b", re.I)),
    ("hit wicket",
     re.compile(r"hit\s*wick", re.I)),
    ("retired hurt",
     re.compile(r"retir", re.I)),
    ("caught",
     re.compile(r"\bc\s+[A-Z][a-z]|\bcaught\b", re.I)),
    ("bowled",
     re.compile(r"(?<!\w)b\s+[A-Z][A-Za-z]{2,}", re.I)),
]
DISMISSAL_VOCABULARY = [m[0] for m in DISMISSAL_PATTERNS]


def clean_ocr_text(text: str) -> str:
    t = str(text)
    t = _WATERMARK_RE.sub(" ", t)
    t = _LOGO_RE.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def classify_dismissal_mode(raw_text: str) -> tuple:
    text = str(raw_text)
    for mode, pattern in DISMISSAL_PATTERNS:
        if pattern.search(text):
            return mode, 1.0
    letters = re.sub(r"[^A-Za-z\s]", " ", text)
    letters = re.sub(r"\s+", " ", letters).strip()
    if len(letters) < 4:
        return "", 0.0
    result = process.extractOne(
        letters, DISMISSAL_VOCABULARY,
        scorer=fuzz.partial_ratio, score_cutoff=60,
    )
    if result:
        return result[0], result[1] / 100.0
    return "", 0.0


def score_card_for_scan(line1: str, line2: str, line3: str = "") -> int:
    """Loose scoring used during Phase 2 scan to find candidate frames."""
    l1       = clean_ocr_text(line1)
    l2       = clean_ocr_text(line2)
    l3       = clean_ocr_text(line3)
    all_text = f"{l1} {l2} {l3}"
    if _DRS_RE.search(all_text):
        return 0
    if len(re.findall(r"\b\d{1,3}-\d{1,2}\b", all_text)) >= 2:
        return 0
    if sum(1 for _, p in DISMISSAL_PATTERNS if p.search(all_text)) >= 3:
        return 0
    score      = 0
    name_words = [w for w in l1.split() if len(w) >= 4 and w[0].isupper() and w.isalpha()]
    if 1 <= len(name_words) <= 4:
        score += 2
    if re.search(r"\b\d{1,3}\s*[\(\[]\s*\d{1,3}\s*[\)\]]", all_text):
        score += 3
    elif re.search(r"\b\d{1,3}\s+\d{1,3}\b", all_text):
        score += 2
    mode, conf = classify_dismissal_mode(all_text)
    if mode:
        score += max(1, int(conf * 2))
    return score


def score_card_weighted(line1: str, line2: str, line3: str = "") -> int:
    """
    Strict scoring used in Phase 2 ranking.
    Returns 0 if both dismissal mode AND score are absent.
    """
    l1       = clean_ocr_text(line1)
    l2       = clean_ocr_text(line2)
    l3       = clean_ocr_text(line3)
    all_text = f"{l1} {l2} {l3}"
    if _DRS_RE.search(all_text):
        return 0
    if len(re.findall(r"\b\d{1,3}-\d{1,2}\b", all_text)) >= 2:
        return 0
    l1_words = [w for w in l1.split() if len(w) >= 3 and w[0].isupper()]
    if len(l1_words) > 4:
        return 0
    mode, conf     = classify_dismissal_mode(all_text)
    has_dismissal  = bool(mode)
    has_score      = bool(
        re.search(r"\b\d{1,3}\s*[\(\[]\s*\d{1,3}\s*[\)\]]", all_text) or
        re.search(r"\b\d{1,3}\s+\d{1,3}\b", all_text)
    )
    if not has_dismissal or not has_score:
        return 0
    score = 0
    if re.search(r"\b\d{1,3}\s*[\(\[]\s*\d{1,3}\s*[\)\]]", all_text):
        score += 3
    elif re.search(r"Balls\s*Faced\s*\d+", all_text, re.IGNORECASE) or \
         re.search(r"Fall\s+of\s+Wicket", all_text, re.IGNORECASE):
        score += 3
    else:
        score += 2
    if mode:
        score += max(1, int(conf * 3))
    names = re.findall(r"\b[A-Z][A-Za-z]{2,}\b", all_text)
    if len(names) >= 1:
        score += 1
    if len(names) >= 2:
        score += 1
    return score


def extract_clean_suffix(line2: str) -> str:
    """Find where the dismissal phrase starts, strip garbled prefix + metadata."""
    m_meta = _CARD_METADATA_RE.search(line2)
    if m_meta:
        line2 = line2[:m_meta.start()].strip()
    patterns = [
        r"\bc\s*&\s*b\b", r"\bc\s+[A-Z][a-z]",
        r"\bb\s+[A-Z][A-Za-z]{2,}", r"\blbw\b",
        r"run\s*out", r"\bst\.?\s+[A-Z]",
    ]
    earliest = len(line2)
    for pat in patterns:
        m = re.search(pat, line2, re.IGNORECASE)
        if m and m.start() < earliest:
            earliest = m.start()
    return line2[earliest:] if earliest < len(line2) else line2


def extract_names_from_dismissal(line2: str, mode: str) -> tuple:
    """Return (bowler, fielder) from the dismissal line."""
    line2 = clean_ocr_text(str(line2))
    m_meta = _CARD_METADATA_RE.search(line2)
    if m_meta:
        line2 = line2[:m_meta.start()].strip()
    if mode == "caught & bowled":
        m = re.search(r"c\s*[&+]\s*b\s+([A-Z][A-Za-z\s\-]{2,25})", line2, re.I)
        if m:
            return m.group(1).strip(), ""
    elif mode == "caught":
        m = re.search(
            r"c\s+([A-Z][A-Za-z\s\-]{2,20}?)\s+b\s+([A-Z][A-Za-z\s\-]{2,20})",
            line2, re.I)
        if m:
            return m.group(2).strip(), m.group(1).strip()
        m = re.search(r"\bb\s+([A-Z][A-Za-z\s\-]{2,20})", line2, re.I)
        if m:
            return m.group(1).strip(), ""
    elif mode == "stumped":
        m = re.search(
            r"st\.?\s+([A-Z][A-Za-z\s\-]{2,20}?)\s+b\s+([A-Z][A-Za-z\s\-]{2,20})",
            line2, re.I)
        if m:
            return m.group(2).strip(), m.group(1).strip()
    elif mode in ("lbw", "bowled"):
        m = re.search(r"\bb\s+([A-Z][A-Za-z\s\-]{2,20})", line2, re.I)
        if m:
            return m.group(1).strip(), ""
    elif mode == "run out":
        m = re.search(
            r"run\s*out\s*[\(\[]?\s*([A-Z][A-Za-z\s\-]{2,20}?)\s*[\)\]]?",
            line2, re.I)
        if m:
            return "", m.group(1).strip()
    return "", ""


# =============================================================================
# 10. Name correction / fuzzy matching
# =============================================================================

def is_garbled(name: str) -> bool:
    if not name or len(name) < 3:
        return True
    clean = re.sub(r"[^A-Za-z]", "", name)
    if len(clean) < 3:
        return True
    vowels = sum(1 for c in clean.lower() if c in "aeiou")
    if vowels / len(clean) < 0.15:
        return True
    if re.search(r"[^aeiouAEIOU\s]{5,}", clean):
        return True
    return False


def fuzzy_correct_name(raw_name: str, roster: Optional[list] = None,
                       threshold: int = 72) -> str:
    if not raw_name or len(raw_name.strip()) < 3:
        return raw_name or ""
    name = clean_ocr_text(raw_name).strip().upper()
    if not name or len(name) < 3:
        return ""
    for digit, letter in [("4", "A"), ("1", "I"), ("0", "O"),
                           ("3", "E"), ("5", "S"), ("8", "B"), ("6", "G")]:
        name = re.sub(rf"(?<=[A-Z]){digit}(?=[A-Z])", letter, name)
        name = re.sub(rf"^{digit}(?=[A-Z]{{2,}})", letter, name)
    if roster:
        result = process.extractOne(
            name, roster, scorer=fuzz.token_sort_ratio, score_cutoff=threshold)
        if result:
            return result[0]
    return name


def correct_player_name(raw_name: str, name_dict: dict) -> str:
    if not raw_name:
        return ""
    name = clean_ocr_text(raw_name).strip().upper()
    for wrong, right in name_dict.items():
        if wrong.upper() in name:
            name = name.replace(wrong.upper(), right.upper())
    return fuzzy_correct_name(name)


def load_name_dict(path: str) -> dict:
    import json
    if path and __import__("os").path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_name_dict(d: dict, path: str) -> None:
    import json
    with open(path, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)


# =============================================================================
# 11. Card window helpers (Phase 2)
# =============================================================================

def find_event_sequence_end(score_ts: float, df_p1, inn: int,
                             cap, fps: float) -> tuple:
    """Estimate when the dismissal-replay sequence ended."""
    import pandas as pd
    if "yolo_replay" in df_p1.columns:
        f = df_p1[
            (df_p1["timestamp_sec"] >= score_ts - 180) &
            (df_p1["timestamp_sec"] <= score_ts + 10) &
            (df_p1["yolo_replay"] == True) &
            (df_p1["innings"] == inn)
        ]
        if not f.empty:
            return float(f.iloc[-1]["timestamp_sec"]), "replay_end"
    if "yolo_wicket" in df_p1.columns:
        f = df_p1[
            (df_p1["timestamp_sec"] >= score_ts - 180) &
            (df_p1["timestamp_sec"] <= score_ts + 10) &
            (df_p1["yolo_wicket"] == True) &
            (df_p1["innings"] == inn)
        ]
        if not f.empty:
            return float(f.iloc[-1]["timestamp_sec"]), "wicket_graphic_end"
    # frame-diff fallback
    window_start = max(0.0, score_ts - 180)
    total_f      = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    diffs        = []
    prev_frame   = None
    for t in np.arange(window_start, score_ts, 2.0):
        fidx = int(t * fps)
        if fidx >= total_f:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
        ret, frame = cap.read()
        if not ret:
            prev_frame = None
            continue
        d = frame_diff_score(prev_frame, frame) if prev_frame is not None else 255.0
        diffs.append((t, d))
        prev_frame = frame
    if len(diffs) >= 4:
        in_replay    = False
        replay_end_t = None
        for t, d in diffs:
            if d < 8.0 and not in_replay:
                in_replay = True
            elif d > 15.0 and in_replay:
                replay_end_t = t
                in_replay    = False
        if replay_end_t:
            return replay_end_t, "frame_diff"
    return max(0.0, score_ts - 60), "fallback"


def get_card_window(ev, df_p1, ball_index, cap, fps: float) -> tuple:
    """
    Derive the (inner_start, inner_end, outer_end, method) search window
    for finding a dismissal card.
    """
    import pandas as pd
    inn      = int(ev["innings"])
    score_ts = float(ev["last_wicket_ts_sec"])

    is_reviewed = False
    if "yolo_review" in df_p1.columns:
        f = df_p1[
            (df_p1["timestamp_sec"] >= score_ts - 240) &
            (df_p1["timestamp_sec"] <= score_ts + 30) &
            (df_p1["yolo_review"] == True) &
            (df_p1["innings"] == inn)
        ]
        is_reviewed = not f.empty

    seq_end, method = find_event_sequence_end(score_ts, df_p1, inn, cap, fps)
    t_inner_start   = max(0.0, seq_end - 3)
    t_inner_end     = t_inner_start + (180 if is_reviewed else 60)
    if is_reviewed:
        method = method + "_reviewed"

    if ball_index is not None and len(ball_index):
        inn_balls  = ball_index[ball_index["innings"] == inn]
        next_balls = inn_balls[inn_balls["delivery_end_sec"] > score_ts + 20]
        t_outer_end = (
            min(float(next_balls.iloc[0]["delivery_end_sec"]) - 2,
                t_inner_start + 300)
            if not next_balls.empty else t_inner_start + 300
        )
    else:
        t_outer_end = t_inner_start + 300

    return t_inner_start, t_inner_end, t_outer_end, method


def get_candidate_regions(frame_bgr: np.ndarray, detections: dict,
                          broadcaster: str, yolo_found_overlay: bool,
                          reader, paddle) -> list:
    h, w = frame_bgr.shape[:2]
    candidates = []
    for cls_name in ["dismissal_card", "stats_overlay",
                     "hawkeye_graphic", "third_umpire_graphic"]:
        if cls_name not in detections:
            continue
        bbox = detections[cls_name]["bbox"]
        if is_strip_zone_bbox(bbox, h, 0.82):
            continue
        if (bbox[3] - bbox[1]) < h * 0.05:
            continue
        card_crop = crop_from_bbox(frame_bgr, bbox)
        card_crop = preprocess_card_crop(card_crop)
        cc_h      = card_crop.shape[0]
        lines     = {}
        for i, label in enumerate(["name_score", "dismissal", "extra"]):
            b1    = int(cc_h * i / 3)
            b2    = int(cc_h * (i + 1) / 3)
            band  = preprocess_card_crop(card_crop[b1:b2, :])
            if label == "dismissal":
                lines[label] = ocr_ensemble(band, reader, paddle)
            else:
                lines[label] = ocr_easyocr(band, reader)
        full_text = " ".join(lines.values())
        candidates.append({
            "source": f"yolo_{cls_name}",
            "lines":  lines,
            "text":   full_text,
            "conf":   detections[cls_name]["conf"],
        })

    zone_order = []
    if broadcaster in CARD_ZONES:
        zone_order.append((broadcaster, CARD_ZONES[broadcaster]))
    for zone_name, ratios in CARD_ZONES.items():
        if zone_name != broadcaster:
            zone_order.append((zone_name, ratios))

    zones_to_scan = zone_order if yolo_found_overlay else zone_order[:2]

    for zone_name, ratios in zones_to_scan:
        crop = crop_zone(frame_bgr, ratios)
        if crop is None or crop.size == 0:
            continue
        t_r, b_r, l_r, r_r = ratios
        h_z    = b_r - t_r
        band_h = h_z / 3
        lines  = {}
        for i, label in enumerate(["name_score", "dismissal", "extra"]):
            band_ratios = (t_r + i * band_h,
                           min(1.0, t_r + (i + 1) * band_h),
                           l_r, r_r)
            band_crop   = crop_zone(frame_bgr, band_ratios)
            if band_crop is None or band_crop.size == 0:
                lines[label] = ""
                continue
            band_crop = preprocess_card_crop(band_crop)
            if label == "dismissal":
                lines[label] = ocr_ensemble(band_crop, reader, paddle)
            else:
                lines[label] = ocr_easyocr(band_crop, reader)
        full_text = " ".join(lines.values())
        if full_text.strip():
            candidates.append({
                "source": f"zone_{zone_name}",
                "lines":  lines,
                "text":   full_text,
                "conf":   0.6,
            })
    return candidates


def merge_card_lines(frame_line_list: list) -> dict:
    merged = {"name_score": "", "dismissal": "", "extra": ""}
    for label in ["name_score", "dismissal", "extra"]:
        cands = [f.get(label, "") for f in frame_line_list if f.get(label, "").strip()]
        if cands:
            merged[label] = max(
                cands,
                key=lambda t: len(re.sub(r"[^A-Za-z]", "", clean_ocr_text(t))),
            )
    return merged


def group_into_windows(candidates: list, gap_sec: float = 4.0,
                       min_frames: int = 2) -> list:
    if not candidates:
        return []
    candidates.sort(key=lambda x: x["ts"])
    windows   = []
    cur_group = [candidates[0]]
    for cand in candidates[1:]:
        if cand["ts"] - cur_group[-1]["ts"] <= gap_sec:
            cur_group.append(cand)
        else:
            if len(cur_group) >= min_frames:
                windows.append(cur_group)
            cur_group = [cand]
    if len(cur_group) >= min_frames:
        windows.append(cur_group)
    return windows


def select_best_card_result(card_windows: list) -> tuple:
    if not card_windows:
        return {}, 0, None, ""
    best_window = max(
        card_windows,
        key=lambda g: sum(c["score"] for c in g) / len(g),
    )
    merged    = merge_card_lines([c["lines"] for c in best_window])
    avg_score = sum(c["score"] for c in best_window) / len(best_window)
    return merged, avg_score, best_window[0]["fidx"], best_window[0]["source"]


# =============================================================================
# 12. VLM card extraction (PaliGemma)
# =============================================================================

_VLM_CARD_PROMPT = (
    "<image> "
    "This image shows a cricket broadcast screen. "
    "Look for a dismissal card showing one batsman's name, runs scored, "
    "balls faced, and how they got out. "
    "Extract ONLY as JSON with no other text:\n"
    '{"is_dismissal_card": true or false, '
    '"batsman": "NAME or empty", '
    '"runs": number or null, '
    '"balls": number or null, '
    '"dismissal_mode": "bowled or caught or lbw or run out or stumped or caught & bowled or empty", '
    '"bowler": "NAME or empty", '
    '"fielder": "NAME or empty"}'
)


def extract_card_vlm(frame_bgr: np.ndarray, vlm_processor, vlm_model,
                     zone_ratios: Optional[tuple] = None) -> Optional[dict]:
    """Extract dismissal card using PaliGemma.  Returns dict or None."""
    if vlm_processor is None or vlm_model is None:
        return None
    import torch
    from PIL import Image as PILImage
    try:
        if zone_ratios:
            crop = crop_zone(frame_bgr, zone_ratios)
            img  = crop if crop.size > 0 else frame_bgr
        else:
            img  = frame_bgr
        pil_img = PILImage.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        gpu     = torch.cuda.is_available()
        inputs  = vlm_processor(
            text=_VLM_CARD_PROMPT, images=pil_img, return_tensors="pt",
        ).to("cuda" if gpu else "cpu",
             torch.bfloat16 if gpu else torch.float32)
        with torch.no_grad():
            output = vlm_model.generate(**inputs, max_new_tokens=150, do_sample=False)
        generated = vlm_processor.decode(
            output[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        ).strip()
        m = re.search(r"\{[^{}]*\}", generated, re.DOTALL)
        if not m:
            m = re.search(r"\{.*\}", generated, re.DOTALL)
        if not m:
            return None
        parsed = json.loads(m.group())
        if not parsed.get("is_dismissal_card", False):
            return None
        if not parsed.get("batsman") and not parsed.get("dismissal_mode"):
            return None
        for k in ["batsman", "bowler", "fielder", "dismissal_mode"]:
            if str(parsed.get(k, "")) in ("None", "null", "null,", ""):
                parsed[k] = ""
        parsed["confidence"] = "high"
        return parsed
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


# =============================================================================
# 13. Commentary helpers (Cell 14)
# =============================================================================

_SINHALA_RE    = re.compile(r"[\u0D80-\u0DFF]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def detect_language(text: str) -> str:
    if _SINHALA_RE.search(text):    return "sinhala"
    if _DEVANAGARI_RE.search(text): return "hindi"
    return "english"


def ensure_english(text: str, si_translator=None, hi_translator=None) -> tuple:
    """Translate to English if needed.  Returns (text, language)."""
    lang = detect_language(text)
    if lang == "english" or (si_translator is None and hi_translator is None):
        return text, lang
    try:
        tr  = si_translator if lang == "sinhala" else hi_translator
        out = tr(text[:512])[0]["translation_text"]
        return out, lang
    except Exception:
        return text, lang


COMMENTARY_DISMISSAL_PATTERNS = [
    ("caught & bowled", re.compile(
        r"caught\s+and\s+bowled|c\s*&\s*b\b|catches?\s+(?:his|her)\s+own"
        r"|chipped?\s+(?:it\s+)?back|(?:return|straight)\s+catch"
        r"|(?:bowler|bowling)\s+(?:takes?|took|caught|holds?)", re.I)),
    ("stumped", re.compile(
        r"(?:he\'?s?|(?:is|was|gets?|got|been))\s+stumped"
        r"|stumped\s+(?:down|by|off|behind)"
        r"|stumping\s+(?:chance|opportunity)", re.I)),
    ("run out", re.compile(
        r"run\s+out|short\s+of\s+(?:his\s+)?ground|direct\s+hit", re.I)),
    ("lbw", re.compile(
        r"\blbw\b|leg\s+before"
        r"|umpire(?:\'?s?)?\s+(?:remains?|remained|gives?|given|raises?)"
        r"\s*(?:unmoved|finger|out)?"
        r"|pitching\s+(?:in\s+line|on\s+(?:leg|middle|off))"
        r"|hitting\s+(?:leg|middle|off)\s+stump"
        r"|umpire\'?s?\s+call|boot\s+before\s+bat"
        r"|given\s+out.*(?:lbw|leg\s+before)", re.I)),
    ("hit wicket", re.compile(r"hit\s+(?:his\s+own\s+)?wicket", re.I)),
    ("caught", re.compile(
        r"(?:he\'?s?|(?:is|was|gets?|got|been))\s+caught"
        r"|taken\s+(?:at|by)\b"
        r"|(?:great|brilliant|good|fine|sharp|wonderful|stunning)\s+catch"
        r"|takes?\s+(?:the|a)\s+catch"
        r"|(?:outside|thick|thin|top|bottom|feather|inside)\s+edge"
        r"|(?:edges?|snicks?)\s+(?:to|it|and|behind|through)"
        r"|caught\s+(?:behind|at|by)|taken\s+by\s+the\s+keeper", re.I)),
    ("bowled", re.compile(
        r"(?:he\'?s?|(?:is|was|gets?|got|been))\s+bowled"
        r"|clean\s+bowled|through\s+(?:the\s+)?(?:gate|defence)"
        r"|knocked?\s+(?:back\s+)?(?:the\s+)?stump"
        r"|(?:middle|leg|off)\s+stump\s+(?:is\s+)?"
        r"(?:out\s+of\s+ground|cartwheel|flatten|gone)", re.I)),
]

NEAR_MISS_PATTERNS = [
    ("near_miss_caught", re.compile(
        r"drops?\b|dropped\s+(?:the\s+)?catch|put\s+down"
        r"|(?:almost|nearly|just)\s+(?:a\s+)?catch"
        r"|(?:chance|opportunity)\s+(?:missed|goes\s+down|dropped)"
        r"|(?:he\'?s?\s+)?(?:spill|spilled|grassed)\s+(?:it|the\s+catch)"
        r"|(?:didn\'?t|could\s+not|couldn\'?t)\s+hold", re.I)),
    ("near_miss_lbw", re.compile(
        r"(?:big|huge|massive)\s+(?:appeal|shout|call)"
        r"|umpire(?:\'?s?)?\s+(?:remains?|remained|stays?)\s+unmoved"
        r"|(?:that|this)\s+(?:is|was|looks?)\s+(?:very\s+)?close"
        r"|umpire\'?s?\s+call|pitching\s+outside\s+leg"
        r"|(?:just\s+)?(?:missing|missed)\s+(?:leg|off|middle)\s+stump", re.I)),
    ("near_miss_runout", re.compile(
        r"(?:close|narrow(?:ly)?)\s+run\s*out"
        r"|(?:just\s+)?(?:made|make|in|home)\s+(?:his\s+)?ground"
        r"|(?:hurry|hurrying).*(?:throw|ground|crease)"
        r"|(?:throw|direct\s+hit).*(?:miss|missed|not\s+accurate)"
        r"|opportunity\s+missed", re.I)),
    ("near_miss_edge", re.compile(
        r"(?:off\s+the\s+)?(?:bottom|top|toe|edge)\s+of\s+(?:the\s+)?bat"
        r"|beaten\s+(?:outside|for|all\s+ends\s+up)"
        r"|(?:just\s+)?(?:narrowly|only\s+just)\s+(?:missed|avoided|beat)"
        r"|oh\s+dear.*(?:bat|edge|miss)", re.I)),
    ("near_miss_stumping", re.compile(
        r"(?:nearly|almost|just)\s+stumped|out\s+of\s+(?:his\s+)?crease\b"
        r"|keeper\s+(?:just\s+)?(?:misses?|missed|fumbles?)", re.I)),
]

_CRICKET_VALIDITY_RE = re.compile(
    r"\b(over|wicket|runs?|ball|caught|bowled|lbw|stumped|run\s*out"
    r"|appeal|not\s*out|boundary|six|four|delivery|batsman"
    r"|umpire|review|crease|stump|slip|gully|short\s*of\s*his\s*ground)\b",
    re.IGNORECASE,
)
_APPEAL_RE  = re.compile(
    r"appeal(?:s|ed|ing)?|(?:big|huge|massive)\s+shout"
    r"|they\s+(?:all\s+)?(?:go\s+up|appeal)|(?:he\'?s?|that\'?s?)\s+(?:out|gone)",
    re.I,
)
_NOT_OUT_RE = re.compile(
    r"\bnot\s+out\b|\bno\s+ball\b|\breviewed\b|\bretained\b"
    r"|\boverturned\b|\bumpire\'?s?\s+call\b|\bunmoved\b",
    re.I,
)

FIELDING_POSITIONS = sorted([
    "first slip", "second slip", "third slip", "slip", "gully",
    "point", "backward point", "cover point", "cover", "extra cover",
    "mid-off", "mid-on", "mid-wicket", "square leg", "fine leg",
    "short fine leg", "deep fine leg", "third man", "long on", "long off",
    "deep mid-wicket", "deep square leg", "long leg", "short leg",
    "silly mid-on", "silly mid-off", "leg slip", "keeper", "caught behind",
], key=len, reverse=True)


def _clean_commentary_text(text: str) -> str:
    _FIXES = {
        r"\belby\b": "lbw", r"\bIbw\b": "lbw", r"\bl8w\b": "lbw",
        r"\bI8w\b": "lbw", r"\bout\s+side\b": "outside",
        r"\bmid\s+wicket\b": "mid-wicket",
    }
    t = text.lower()
    for p, r in _FIXES.items():
        t = re.sub(p, r, t, flags=re.IGNORECASE)
    return t


def is_valid_commentary(text: str, player_names: list = None) -> bool:
    if not text or len(text) < 20:
        return False
    if bool(_CRICKET_VALIDITY_RE.search(text)):
        return True
    if player_names:
        return any(n.lower() in text.lower() for n in player_names)
    return False


def classify_commentary(text: str, context: str = "wicket",
                        zero_shot=None) -> dict:
    """
    Classify commentary as a wicket or near-miss event.
    Uses regex first, then zero-shot NLI as fallback.
    Returns a dict with regex_type, zs_type, consensus_type, etc.
    """
    result = {
        "regex_type": None, "regex_conf": 0.0,
        "zs_type": None,    "zs_conf": 0.0,
        "consensus_type": None,
        "has_appeal": False, "has_not_out": False,
        "fielding_position": None,
    }
    t = _clean_commentary_text(text)
    patterns = (COMMENTARY_DISMISSAL_PATTERNS
                if context == "wicket" else NEAR_MISS_PATTERNS)
    for mode, pat in patterns:
        if pat.search(t):
            result["regex_type"] = mode
            result["regex_conf"] = 1.0
            break

    result["has_appeal"]  = bool(_APPEAL_RE.search(t))
    result["has_not_out"] = bool(_NOT_OUT_RE.search(t))

    if zero_shot is not None and not result["regex_type"]:
        if context == "wicket":
            LABELS = [
                "the batsman was bowled — the ball hit the stumps",
                "the batsman was caught by a fielder",
                "the batsman was caught and bowled by the bowler",
                "the batsman was out lbw — leg before wicket",
                "the batsman was run out — short of his ground",
                "the batsman was stumped by the wicket keeper",
                "nothing happened — not a wicket",
            ]
            LABEL_MAP = {
                "the batsman was bowled — the ball hit the stumps"        : "bowled",
                "the batsman was caught by a fielder"                     : "caught",
                "the batsman was caught and bowled by the bowler"         : "caught & bowled",
                "the batsman was out lbw — leg before wicket"             : "lbw",
                "the batsman was run out — short of his ground"           : "run out",
                "the batsman was stumped by the wicket keeper"            : "stumped",
                "nothing happened — not a wicket"                         : None,
            }
        else:
            LABELS = [
                "the fielder almost caught but dropped the ball",
                "the batsman almost got out lbw — big appeal, not out",
                "the batsman almost got run out — very close",
                "the ball beat the bat outside the edge — close call",
                "the batsman almost got stumped",
                "nothing significant — normal delivery",
            ]
            LABEL_MAP = {
                "the fielder almost caught but dropped the ball"       : "near_miss_caught",
                "the batsman almost got out lbw — big appeal, not out" : "near_miss_lbw",
                "the batsman almost got run out — very close"          : "near_miss_runout",
                "the ball beat the bat outside the edge — close call"  : "near_miss_edge",
                "the batsman almost got stumped"                       : "near_miss_stumping",
                "nothing significant — normal delivery"                : None,
            }
        try:
            r   = zero_shot(text[:400], candidate_labels=LABELS,
                            hypothesis_template="In this cricket commentary, {}.")
            top = r["labels"][0]
            scr = r["scores"][0]
            if scr >= 0.55:
                result["zs_type"] = LABEL_MAP.get(top)
                result["zs_conf"] = float(scr)
        except Exception:
            pass

    result["consensus_type"] = result["regex_type"] or result["zs_type"]

    # appeal+not-out fallback for near-miss
    if (result["has_appeal"] and result["has_not_out"]
            and not result["consensus_type"] and context == "near_miss"):
        result["consensus_type"] = "near_miss_lbw"

    if result["consensus_type"] in ("caught", "caught & bowled",
                                     "near_miss_caught", "near_miss_edge"):
        tl = t.lower()
        for pos in FIELDING_POSITIONS:
            if pos.lower() in tl:
                result["fielding_position"] = pos
                break

    return result


# Event-label parsing (LAST WICKET / FALL OF WICKET text in score strip)
_FULL_EVENT_RE = re.compile(
    r"(?:LAST\s+WICKET|FALL\s+OF\s+WICKET|FOW)\s*[:\-]?\s*"
    r"(\d{1,3})[-:](\d{1,2})\s+"
    r"([A-Z][A-Z\s]{3,30}?)\s+"
    r"(\d{1,3})\s*[\(\[]\s*(\d{1,3})",
    re.IGNORECASE,
)
_SCORE_ONLY_EVENT_RE = re.compile(
    r"(?:LAST\s+WICKET|FALL\s+OF\s+WICKET|FOW)\s*[:\-]?\s*"
    r"(\d{1,3})[-:](\d{1,2})",
    re.IGNORECASE,
)


def parse_event_text(text: str) -> Optional[dict]:
    text = str(text)
    m    = _FULL_EVENT_RE.search(text)
    if m:
        batsman = m.group(3).strip()
        batsman = re.sub(r"([A-Z]{5,})([A-Z]{2})",
                         lambda x: x.group(1) + " " + x.group(2), batsman)
        return {
            "score_runs"   : int(m.group(1)),
            "score_wickets": int(m.group(2)),
            "batsman"      : batsman.strip(),
            "runs"         : int(m.group(4)),
            "balls"        : int(m.group(5)),
            "source"       : "EVENT_LABEL_FULL",
        }
    m2 = _SCORE_ONLY_EVENT_RE.search(text)
    if m2:
        return {
            "score_runs"   : int(m2.group(1)),
            "score_wickets": int(m2.group(2)),
            "batsman"      : "",
            "runs"         : None,
            "balls"        : None,
            "source"       : "EVENT_LABEL_SCORE_ONLY",
        }
    return None
