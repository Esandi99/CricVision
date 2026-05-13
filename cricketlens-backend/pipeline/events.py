"""
pipeline/events.py — Extract wicket events from Phase 1 scan data.

Implements the 5-signal wicket detection strategy from the notebook:
  Signal 1: "LAST WICKET / FALL OF WICKET" event-label groups
  Signal 2: Score wicket-count jump (diff == 1) + monotonicity check
  Signal 3: YOLO wicket_graphic — refines delivery timestamp
  Signal 4: W marker in delivery dots (gameplay-only)
  Signal 5: Innings-end inference (all-out without 10th wicket shown)

After detection, each event is validated against YOLO confirmation signals.
Unconfirmed score-jump events are flagged as SCORE_JUMP_UNCONFIRMED.

Output: a list of event-row dicts (also accessible as a DataFrame).
"""

import logging
from typing import Optional, Callable

import pandas as pd

from pipeline.helpers import (
    parse_event_text,
    seconds_to_hhmmss,
    build_ball_change_index,
)

log = logging.getLogger(__name__)

# Seconds after the "LAST WICKET" label that the delivery occurred.
# Used for Signal 1 / 2 only; Signal 3 provides a YOLO-refined timestamp.
LABEL_DELAY_SEC = 55

# A score-jump event without any YOLO confirmation within this window
# is flagged as UNCONFIRMED (still included, marked for review).
YOLO_CONFIRM_WINDOW = 120  # seconds


def extract_wicket_events(
    df_p1: pd.DataFrame,
    phase1_csv: str,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """
    Detect all wicket events from *df_p1* using 5 signals.

    Returns a DataFrame with one row per wicket, including:
        wicket_number, innings, innings_wicket, score,
        delivery_ts_sec/str, last_wicket_ts_sec/str, over_num, ball_num,
        batsman, runs, balls, source, n_frames
    """
    df_phase1 = df_p1.copy()
    df_phase1["parsed"]         = df_phase1["strip_text"].apply(parse_event_text)
    df_phase1["wickets_filled"] = df_phase1["wickets"].ffill().fillna(0).astype(float)

    # ── Signal 1: event-label groups ──────────────────────────────────────────
    df_ev    = df_phase1[df_phase1["parsed"].notna()].copy().reset_index(drop=True)
    groups   = []
    cur_rows = []
    last_ts  = -999
    last_wkt = -1

    for _, row in df_ev.iterrows():
        p   = row["parsed"]
        ts  = row["timestamp_sec"]
        wkt = p["score_wickets"]
        if (wkt != last_wkt or ts - last_ts > 90) and cur_rows:
            groups.append(cur_rows)
            cur_rows = []
        cur_rows.append(row)
        last_ts, last_wkt = ts, wkt
    if cur_rows:
        groups.append(cur_rows)

    covered = {
        (int(grp[0]["innings"]), grp[0]["parsed"]["score_wickets"])
        for grp in groups
    }
    log.info("Signal 1 (event label): %d events", len(groups))

    if progress_cb:
        progress_cb(0.1, "Signal 1: event labels found")

    # ── Signal 2: score jump + monotonicity ───────────────────────────────────
    df_sorted = df_phase1.sort_values("timestamp_sec").reset_index(drop=True)
    df_sorted["wkt_diff"] = df_sorted["wickets_filled"].diff().fillna(0)
    valid_jumps           = df_sorted[df_sorted["wkt_diff"] == 1]

    last_sj_ts        = -999
    last_runs_per_inn = {1: -1, 2: -1}
    sj_added          = 0

    for _, row in valid_jumps.iterrows():
        ts  = row["timestamp_sec"]
        inn = int(row["innings"])
        wkt = int(row["wickets_filled"])
        if ts - last_sj_ts < 30:
            continue
        curr_runs = int(row["runs"]) if pd.notna(row["runs"]) else 0
        if curr_runs < last_runs_per_inn.get(inn, -1):
            continue
        key = (inn, wkt)
        if key in covered:
            last_sj_ts = ts
            last_runs_per_inn[inn] = max(last_runs_per_inn.get(inn, -1), curr_runs)
            continue
        row_copy = row.copy()
        row_copy["parsed"] = {
            "score_runs"   : curr_runs,
            "score_wickets": wkt,
            "batsman"      : "",
            "runs"         : None,
            "balls"        : None,
            "source"       : "SCORE_JUMP",
        }
        groups.append([row_copy])
        covered.add(key)
        last_sj_ts = ts
        last_runs_per_inn[inn] = max(last_runs_per_inn.get(inn, -1), curr_runs)
        sj_added  += 1

    log.info("Signal 2 (score jump): %d new events", sj_added)

    if progress_cb:
        progress_cb(0.25, f"Signal 2: {sj_added} score-jump events")

    # ── Signal 3: YOLO wicket_graphic — refine delivery timestamp ─────────────
    if "yolo_wicket" in df_phase1.columns:
        yolo_ts_list = df_phase1[
            df_phase1["yolo_wicket"] == True
        ]["timestamp_sec"].tolist()
        refined = 0
        for grp in groups:
            event_ts   = grp[0]["timestamp_sec"]
            candidates = [t for t in yolo_ts_list
                          if event_ts - 180 <= t <= event_ts + 10]
            if candidates:
                earliest = min(candidates)
                if abs(earliest - event_ts) > 5:
                    grp[0]["_yolo_delivery_ts"] = earliest
                    refined += 1
        log.info("Signal 3 (YOLO): refined delivery timestamp for %d events", refined)

    # ── Signal 4: W marker in delivery dots ───────────────────────────────────
    wm_added = 0
    if "has_w_marker" in df_phase1.columns:
        wm_frames = df_phase1[
            (df_phase1["has_w_marker"] == True) &
            (df_phase1["is_gameplay"]  == True) &
            (df_phase1["runs"].notna()) &
            (df_phase1["wickets"].notna())
        ].sort_values("timestamp_sec").copy()

        wm_clusters = []
        cur_cluster = []
        prev_ts     = -999
        for _, row in wm_frames.iterrows():
            ts = float(row["timestamp_sec"])
            if cur_cluster and ts - prev_ts > 15:
                wm_clusters.append(cur_cluster)
                cur_cluster = []
            cur_cluster.append(row)
            prev_ts = ts
        if cur_cluster:
            wm_clusters.append(cur_cluster)

        for cluster in wm_clusters:
            best_row = cluster[0]
            ts       = float(best_row["timestamp_sec"])
            inn      = int(best_row["innings"])
            already  = any(
                abs(grp[0]["timestamp_sec"] - ts) <= 90 and
                int(grp[0]["innings"]) == inn
                for grp in groups
            )
            if already:
                continue
            cluster_wkts = [
                int(r["wickets_filled"])
                for r in cluster
                if pd.notna(r.get("wickets_filled")) and r["wickets_filled"] > 0
            ]
            wkt_from_score = (max(set(cluster_wkts), key=cluster_wkts.count)
                              if cluster_wkts else None)
            if wkt_from_score is not None and wkt_from_score > 0:
                wkt = wkt_from_score
            else:
                covered_in_inn = sorted(k[1] for k in covered if k[0] == inn)
                wkt = (max(covered_in_inn) + 1) if covered_in_inn else 1
            key = (inn, wkt)
            if key in covered:
                continue
            runs_vals = [int(r["runs"]) for r in cluster if pd.notna(r.get("runs"))]
            curr_runs = max(runs_vals) if runs_vals else 0
            if curr_runs < last_runs_per_inn.get(inn, -1):
                continue
            best_row_copy = best_row.copy()
            best_row_copy["parsed"] = {
                "score_runs"   : curr_runs,
                "score_wickets": wkt,
                "batsman"      : "",
                "runs"         : None,
                "balls"        : None,
                "source"       : "W_MARKER",
            }
            groups.append([best_row_copy])
            covered.add(key)
            last_runs_per_inn[inn] = max(last_runs_per_inn.get(inn, -1), curr_runs)
            wm_added += 1

    log.info("Signal 4 (W marker): %d new events", wm_added)

    if progress_cb:
        progress_cb(0.4, f"Signal 4: {wm_added} W-marker events")

    # ── Signal 5: Innings-end inference ───────────────────────────────────────
    ie_added = 0
    for inn_check in [1, 2]:
        inn_wkts = sorted(
            g[0]["parsed"]["score_wickets"]
            for g in groups if int(g[0]["innings"]) == inn_check
        )
        if not inn_wkts or max(inn_wkts) != 9:
            continue
        inn_frames = df_phase1[df_phase1["innings"] == inn_check]
        last_valid = inn_frames[
            (inn_frames["wickets_filled"] == 9) &
            (inn_frames["runs"].notna())
        ]
        if last_valid.empty:
            continue
        last_row  = last_valid.iloc[-1]
        last_ts   = float(last_row["timestamp_sec"])
        last_runs = int(last_row["runs"])
        # Verify innings ended all-out
        next_inn = df_phase1[
            (df_phase1["timestamp_sec"] > last_ts) &
            (df_phase1["timestamp_sec"] < last_ts + 600) &
            (df_phase1["runs"].notna()) &
            (df_phase1["runs"] <= 5) &
            (df_phase1["wickets"].notna()) &
            (df_phase1["wickets"] <= 1)
        ]
        if next_inn.empty:
            continue
        key = (inn_check, 10)
        if key in covered:
            continue
        row_copy = last_row.copy()
        row_copy["parsed"] = {
            "score_runs"   : last_runs,
            "score_wickets": 10,
            "batsman"      : "",
            "runs"         : None,
            "balls"        : None,
            "source"       : "INNINGS_END",
        }
        groups.append([row_copy])
        covered.add(key)
        ie_added += 1

    log.info("Signal 5 (innings end): %d new events", ie_added)

    # ── YOLO confirmation pass ─────────────────────────────────────────────────
    yolo_confirm_ts: set = set()
    for col in ["yolo_wicket", "yolo_card", "has_w_marker", "yolo_replay"]:
        if col in df_phase1.columns:
            yolo_confirm_ts.update(
                df_phase1[df_phase1[col] == True]["timestamp_sec"].tolist()
            )

    for grp in groups:
        src = grp[0]["parsed"]["source"]
        if src not in ("SCORE_JUMP", "W_MARKER"):
            continue
        ts  = float(grp[0]["timestamp_sec"])
        inn = int(grp[0]["innings"])
        confirmed = any(abs(t - ts) <= YOLO_CONFIRM_WINDOW for t in yolo_confirm_ts)
        if not confirmed:
            grp[0]["parsed"]["source"] = "SCORE_JUMP_UNCONFIRMED"

    # ── Sort + dedup ───────────────────────────────────────────────────────────
    groups.sort(key=lambda g: g[0]["timestamp_sec"])
    seen     = set()
    groups_d = []
    for grp in groups:
        p   = grp[0]["parsed"]
        inn = int(grp[0]["innings"])
        wkt = p["score_wickets"]
        key = (inn, wkt)
        if key in seen:
            continue
        seen.add(key)
        groups_d.append(grp)
    groups = groups_d

    # ── Build event rows ───────────────────────────────────────────────────────
    event_rows = []
    global_num = inn1_count = inn2_count = 0

    for grp in groups:
        first      = grp[0]
        p          = first["parsed"]
        global_num += 1
        innings    = int(first["innings"])

        if innings == 1:
            inn1_count += 1
            inn_wkt = inn1_count
        else:
            inn2_count += 1
            inn_wkt = inn2_count

        lw_ts  = first["timestamp_sec"]
        source = p["source"]

        if source in ("SCORE_JUMP", "W_MARKER", "SCORE_JUMP_UNCONFIRMED"):
            yolo_ref    = first.get("_yolo_delivery_ts")
            delivery_ts = (yolo_ref - 2) if yolo_ref else max(0.0, lw_ts - 60)
        else:
            delivery_ts = max(0.0, lw_ts - LABEL_DELAY_SEC)

        event_rows.append({
            "wicket_number"      : global_num,
            "innings"            : innings,
            "innings_wicket"     : inn_wkt,
            "score"              : f"{p['score_runs']}-{p['score_wickets']}",
            "delivery_ts_sec"    : round(delivery_ts, 3),
            "delivery_ts_str"    : seconds_to_hhmmss(delivery_ts),
            "last_wicket_ts_sec" : lw_ts,
            "last_wicket_ts_str" : seconds_to_hhmmss(lw_ts),
            "last_wicket_end_sec": grp[-1]["timestamp_sec"],
            "over_num"           : first.get("over_num"),
            "ball_num"           : first.get("ball_num"),
            "wicket_ball_in_over": first.get("wicket_ball_in_over"),
            "batsman"            : p["batsman"],
            "runs"               : p["runs"],
            "balls"              : p["balls"],
            "source"             : source,
            "n_frames"           : len(grp),
        })

    df_wickets = pd.DataFrame(event_rows)
    log.info("Wickets detected: %d  (Inn1=%d  Inn2=%d)",
             len(df_wickets), inn1_count, inn2_count)

    if progress_cb:
        progress_cb(1.0, f"Event extraction complete: {len(df_wickets)} wickets")

    return df_wickets
