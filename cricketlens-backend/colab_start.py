"""
colab_start.py  —  CricketLens Backend  (Google Colab edition)
===============================================================
Paste this file to /content/drive/MyDrive/cricketlens-backend/
then run the cell below in a Colab notebook:

    !python /content/drive/MyDrive/cricketlens-backend/colab_start.py

Or copy-paste the cells individually into separate Colab cells.
"""

# ══════════════════════════════════════════════════════════════════════════════
# CELL 1 — Mount Drive + set paths
# ══════════════════════════════════════════════════════════════════════════════
from google.colab import drive
import os

if not os.path.exists("/content/drive/MyDrive"):
    drive.mount("/content/drive")
else:
    print("✅ Drive already mounted")

# ── Paths — edit these to match your Drive layout ─────────────────────────────
BACKEND_DIR    = "/content/drive/MyDrive/cricketlens-backend"
YOLO_PATH      = "/content/drive/MyDrive/Dataset/yolo_region_detection/models/cricket_v3_yolov8s/weights/best.pt"
DATA_DIR       = "/content/drive/MyDrive/cricketlens_jobs"   # where jobs are stored
WHISPER_SIZE   = "small"   # "small" or "medium"
NGROK_TOKEN    = "your_ngrok_token_here"   # ← get free token at dashboard.ngrok.com

# ── Set env vars BEFORE importing the backend ─────────────────────────────────
os.environ["YOLO_MODEL_PATH"]        = YOLO_PATH
os.environ["CRICKETLENS_DATA_DIR"]   = DATA_DIR
os.environ["WHISPER_MODEL"]          = WHISPER_SIZE

print(f"  YOLO  : {YOLO_PATH}")
print(f"  Data  : {DATA_DIR}")
print(f"  Exists: {os.path.exists(YOLO_PATH)}")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 2 — Install packages
# ══════════════════════════════════════════════════════════════════════════════
import subprocess

def _pip(*pkgs):
    subprocess.run(["pip", "install", "-q", *pkgs], check=True)

def _apt(*pkgs):
    subprocess.run(["apt-get", "install", "-y", "-q", *pkgs],
                   capture_output=True, check=False)

print("📦 Installing packages (this takes ~2 min on first run)…")
_apt("ffmpeg")
_pip("fastapi", "uvicorn[standard]", "python-multipart", "aiofiles", "nest_asyncio")
_pip("opencv-python-headless", "Pillow")
_pip("ultralytics")
_pip("easyocr")
_pip("rapidfuzz")
_pip("openai-whisper")
_pip("transformers", "accelerate", "sentencepiece", "huggingface-hub")
_pip("pandas", "numpy", "tqdm")
_pip("pyngrok")
print("✅ Packages ready")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 3 — Start the backend server
# ══════════════════════════════════════════════════════════════════════════════
import sys, threading, time, asyncio
import nest_asyncio
nest_asyncio.apply()

# Add backend to path so imports work
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

# Kill any stale process on port 8000
subprocess.run(["fuser", "-k", "8000/tcp"], capture_output=True)
time.sleep(0.5)

def _start_server():
    import uvicorn
    from main import app   # imports CricketLens FastAPI app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(
        uvicorn.Server(
            uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
        ).serve()
    )

_thread = threading.Thread(target=_start_server, daemon=True)
_thread.start()

# Confirm the server is up
import urllib.request as _ur
_bound = False
for _i in range(12):
    time.sleep(1)
    try:
        _ur.urlopen("http://localhost:8000/health", timeout=2)
        _bound = True
        break
    except Exception:
        pass

if _bound:
    print(f"✅ Server started (took {_i+1}s)")
else:
    print("❌ Server failed to start — check errors above")

# ══════════════════════════════════════════════════════════════════════════════
# CELL 4 — Create ngrok tunnel + display the URL
# ══════════════════════════════════════════════════════════════════════════════
from pyngrok import ngrok as _ngrok, conf as _nc
from IPython.display import display as _disp, HTML as _HTML

_pub_url = None

if NGROK_TOKEN and NGROK_TOKEN != "your_ngrok_token_here":
    try:
        # Kill any existing tunnels
        for _t in _ngrok.get_tunnels():
            _ngrok.disconnect(_t.public_url)
        _ngrok.kill()
        time.sleep(0.5)

        _nc.get_default().auth_token = NGROK_TOKEN
        _ngrok.set_auth_token(NGROK_TOKEN)
        _tunnel  = _ngrok.connect(8000, "http")
        _pub_url = _tunnel.public_url
        print(f"✅ ngrok tunnel: {_pub_url}")
    except Exception as _ne:
        print(f"❌ ngrok failed: {_ne}")
        _pub_url = None

if not _pub_url:
    from google.colab.output import eval_js as _ejs
    _pub_url = _ejs("google.colab.kernel.proxyPort(8000)")
    print(f"ℹ️  Using Colab proxy: {_pub_url}")
    print("   Set NGROK_TOKEN above for a stable public URL")

# ── Display instructions ───────────────────────────────────────────────────────
_status = "✅ CRICKETLENS BACKEND RUNNING" if _bound else "❌ SERVER FAILED"

_disp(_HTML(f"""
<div style="font-family:monospace;padding:16px;background:#111620;border:1px solid #22c55e;
            border-radius:8px;margin:8px 0">
  <p style="color:#22c55e;font-size:13px;margin:0 0 12px;letter-spacing:2px">{_status}</p>
  <p style="color:#94a3b8;font-size:12px;margin:0 0 6px">
    Paste this URL in the <strong style="color:#e2e8f0">frontend Settings → Backend URL</strong>:
  </p>
  <code style="color:#e2e8f0;font-size:13px;background:#0a0d12;padding:8px 14px;
               border-radius:6px;display:block;word-break:break-all;margin-bottom:10px">
    {_pub_url}
  </code>
  <a href="{_pub_url}/health" target="_blank"
     style="color:#4a5568;font-size:11px;text-decoration:underline">
    Test /health endpoint
  </a>
  <p style="color:#4a5568;font-size:11px;margin:10px 0 0">
    Models load lazily on first job — startup uses &lt;1 GB RAM.
  </p>
</div>
"""))
