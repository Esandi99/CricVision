# ═══════════════════════════════════════════════════════════════════
# THREE TARGETED PATCHES for Cell C
# Apply each patch in the location described above it.
# ═══════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────
# PATCH 1: _run_phase1  (fixes: det.get("class_name", "") crash)
#
# FIND this block (around the event_label loop):
#
#     event_label = ""
#     for det in detections:
#         cls = det.get("class_name", "")
#         if cls in ("wicket_graphic", "dismissal_card",
#                    "third_umpire_graphic", "umpire_out_signal"):
#             event_label = cls
#             break
#
# REPLACE with:
#
#     event_label = ""
#     for det in detections:
#         if not isinstance(det, dict):   # ← PATCH 1
#             continue
#         cls = det.get("class_name", "")
#         if cls in ("wicket_graphic", "dismissal_card",
#                    "third_umpire_graphic", "umpire_out_signal"):
#             event_label = cls
#             break
# ───────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────
# PATCH 2: _run_cell10_wicket_extraction
#          (fixes: p["score_wickets"] on a string row)
#
# FIND:
#     df_ev = df_phase1[df_phase1["parsed"].notna()].copy().reset_index(drop=True)
#
# REPLACE with:
#     df_phase1["parsed"] = df_phase1["parsed"].apply(
#         lambda x: x if isinstance(x, dict) else None   # ← PATCH 2
#     )
#     df_ev = df_phase1[df_phase1["parsed"].notna()].copy().reset_index(drop=True)
# ───────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────
# PATCH 3: _run_phase3  (THE MAIN FIX — fixes the reported error)
#          parse_card_full_text() returns a raw string on OCR failure
#
# FIND (two places, both inside the for loop):
#
#   Place A:
#     parsed_ocr = parse_card_full_text(full_text, name_dict, roster=roster)
#
#   Place B:
#     parsed_ocr = parse_card_full_text(stored, name_dict, roster=roster)
#
# REPLACE Place A with:
#     parsed_ocr = _safe_dict(
#         parse_card_full_text(full_text, name_dict, roster=roster), "ocr_full"
#     )
#
# REPLACE Place B with:
#     parsed_ocr = _safe_dict(
#         parse_card_full_text(stored, name_dict, roster=roster), "ocr_stored"
#     )
# ───────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────
# PATCH 4: _run_phase3  (safety net for ALL .get() calls on parsed_ocr)
#          Add this line RIGHT AFTER each parse_card_full_text call
#          (after Patch 3 is applied) as an extra guard:
#
#     if not isinstance(parsed_ocr, dict):
#         parsed_ocr = {}
# ───────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────
# QUICK SUMMARY of root cause:
#
# parse_card_full_text() is returning a plain string (raw OCR text
# or an error message) instead of a dict.  When the code then does:
#
#     ocr_batsman = parsed_ocr.get("batsman", "")
#
# Python raises:  AttributeError: 'str' object has no attribute 'get'
#
# The _safe_dict() helper already in Cell C handles this — it just
# wasn't being called on the parse_card_full_text() result.
# ───────────────────────────────────────────────────────────────────
