
# ═══════════════════════════════════════════════════════════════════════════════
# CELL C FIX — paste this block RIGHT AFTER your imports in Cell C
# Fixes: Pipeline error: 'str' object has no attribute 'get'
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_dict(result, label="result"):
    """
    Coerce any pipeline return value to a dict.

    Some pipeline helper functions return a string (e.g. a file path or an
    error message) instead of a dict. Calling .get() on a str raises:
        AttributeError: 'str' object has no attribute 'get'

    This wrapper turns any non-dict return into a dict so the bridge never
    crashes on a bad return type.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        # String could be a file path or an inline error message
        return {"output": result, "error": None if not result.startswith("Error") else result}
    if result is None:
        return {}
    # Anything else (list, int, …) — wrap it
    return {"output": result}


# ── Now patch run_pipeline to use _safe_dict ──────────────────────────────────
# Find the section in run_pipeline where you call your pipeline steps and
# access the result with .get().  Replace lines like:
#
#   result = run_phase1(video_path, ...)
#   wickets = result.get("wickets", [])
#
# with:
#
#   result = _safe_dict(run_phase1(video_path, ...), "phase1")
#   wickets = result.get("wickets", [])
#
# OR — apply the wrapper globally by wrapping EVERY phase call like this:

# EXAMPLE — adapt to match your actual phase function names:
#
# async def run_pipeline(job_id: str, video_path: str, run_commentary: bool):
#     job = get_job(job_id)
#     try:
#         update_job(job_id, status="processing", progress=0.05, message="Phase 1: scanning frames")
#
#         phase1_raw = run_phase1(video_path)          # <-- your existing call
#         phase1     = _safe_dict(phase1_raw, "phase1")  # <-- wrap it
#         wickets    = phase1.get("wickets", [])
#         frames     = phase1.get("frames", [])
#
#         update_job(job_id, status="processing", progress=0.45, message="Phase 2: dismissal cards")
#
#         phase2_raw = run_phase2(video_path, wickets)
#         phase2     = _safe_dict(phase2_raw, "phase2")
#         cards      = phase2.get("cards", [])
#
#         update_job(job_id, status="processing", progress=0.75, message="Phase 3: extracting names")
#
#         phase3_raw = run_phase3(cards)
#         phase3     = _safe_dict(phase3_raw, "phase3")
#         events     = phase3.get("events", [])
#
#         if run_commentary:
#             update_job(job_id, status="processing", progress=0.90, message="Commentary analysis")
#             comm_raw = run_commentary_analysis(video_path, events)
#             comm     = _safe_dict(comm_raw, "commentary")
#             events   = comm.get("events", events)
#
#         update_job(job_id, status="done", progress=1.0, events=events)
#
#     except Exception as e:
#         update_job(job_id, status="error", message=f"Pipeline error: {e}")
#         raise

# ═══════════════════════════════════════════════════════════════════════════════
# QUICK DIAGNOSTIC — run this in a separate cell to find which step returns str
# ═══════════════════════════════════════════════════════════════════════════════

def diagnose_pipeline_return_types(video_path_sample):
    """
    Call this once with a short test clip to see which phase returns a str.
    Remove after debugging.
    """
    import traceback

    steps = {
        "phase1": lambda: run_phase1(video_path_sample),
    }
    # Add your other phase functions here, e.g.:
    # "phase2": lambda: run_phase2(video_path_sample, []),
    # "phase3": lambda: run_phase3([]),

    for name, fn in steps.items():
        try:
            r = fn()
            print(f"[{name}] type={type(r).__name__}  value_preview={str(r)[:120]}")
        except Exception as e:
            print(f"[{name}] EXCEPTION: {e}")
            traceback.print_exc()
