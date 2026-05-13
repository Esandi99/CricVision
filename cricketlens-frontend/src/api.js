// Thin wrapper around the FastAPI backend.
//
// ROUTING STRATEGY (important — read before editing)
// ────────────────────────────────────────────────────
//
//  fetch() / XHR  →  go DIRECTLY to the ngrok URL (VITE_API_BASE).
//    • They can add  ngrok-skip-browser-warning: true  themselves.
//    • Bypassing the Vite proxy avoids body-buffering + 60s timeout that
//      causes ERR_CONNECTION_RESET on large video uploads.
//
//  EventSource (SSE)  →  goes through the Vite proxy at a RELATIVE path.
//    • EventSource has NO header API, so it cannot bypass ngrok's browser
//      warning on its own.  The Vite proxy (vite.config.js) injects the
//      header for the /api/stream route and keeps the connection alive.
//
// VITE_API_BASE  must be set to the full ngrok URL in .env.development.

const BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

/** Headers every fetch/XHR request must carry.
 *  ngrok-skip-browser-warning bypasses the ngrok HTML interstitial page. */
function getHeaders(extra = {}) {
  return {
    "ngrok-skip-browser-warning": "true",
    ...extra,
  };
}

// ─── Upload ──────────────────────────────────────────────────────────────────

export async function uploadVideo(file, { runCommentary = true, onProgress } = {}) {
  const url = `${BASE}/api/upload?run_commentary=${runCommentary}`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);

    xhr.open("POST", url);
    // Must be set AFTER open() — this is what lets us bypass ngrok directly
    xhr.setRequestHeader("ngrok-skip-browser-warning", "true");

    // No timeout — uploads can take many minutes for large files
    xhr.timeout = 0;

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch (e) {
          reject(new Error("Server returned invalid JSON: " + xhr.responseText.slice(0, 200)));
        }
      } else if (xhr.status === 503) {
        // Backend is busy with another job
        let msg = "Server busy — another video is already processing. Wait and retry.";
        try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
        reject(new Error(msg));
      } else if (xhr.status === 400) {
        let msg = `Upload rejected (400)`;
        try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
        reject(new Error(msg));
      } else {
        reject(new Error(`Upload failed: ${xhr.status} — ${xhr.responseText.slice(0, 200)}`));
      }
    };

    xhr.onerror = () =>
      reject(new Error(
        "Network error during upload — check that the Colab backend is still running " +
        "and that the ngrok URL in .env.development is current."
      ));

    xhr.ontimeout = () => reject(new Error("Upload timed out"));

    xhr.send(form);
  });
}

// ─── Job queries ──────────────────────────────────────────────────────────────

export async function getJob(jobId) {
  const r = await fetch(`${BASE}/api/jobs/${jobId}`, { headers: getHeaders() });
  if (!r.ok) throw new Error(`Job fetch failed: ${r.status}`);
  return r.json();
}

export async function getEvents(jobId) {
  const r = await fetch(`${BASE}/api/events/${jobId}`, { headers: getHeaders() });
  if (!r.ok) throw new Error(`Events fetch failed: ${r.status}`);
  return r.json();
}

export async function listJobs() {
  const r = await fetch(`${BASE}/api/jobs`, { headers: getHeaders() });
  if (!r.ok) throw new Error(`Jobs list failed: ${r.status}`);
  return r.json();
}

export async function deleteJob(jobId) {
  const r = await fetch(`${BASE}/api/jobs/${jobId}`, {
    method: "DELETE",
    headers: getHeaders(),
  });
  if (!r.ok) throw new Error(`Delete failed: ${r.status}`);
  return r.json();
}

// ─── SSE progress stream ──────────────────────────────────────────────────────

/**
 * Subscribe to live progress for a job.
 * onUpdate({ status, progress, message, events }) fires on every SSE message.
 * Returns a cleanup function.
 *
 * IMPORTANT: EventSource uses a RELATIVE path (/api/stream/…) so the
 * Vite dev-proxy forwards it with the ngrok bypass header.  Do NOT
 * prepend BASE here — that would send the request directly to ngrok
 * without the header and trigger the HTML interstitial.
 */
export function streamProgress(jobId, onUpdate, onError) {
  const es = new EventSource(`/api/stream/${jobId}`);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onUpdate(data);
      if (data.status === "done" || data.status === "error") es.close();
    } catch (err) {
      onError?.(err);
    }
  };

  es.onerror = (err) => {
    onError?.(err);
    es.close();
  };

  return () => es.close();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Returns a local object-URL for immediate video playback (no backend needed). */
export function buildVideoUrlFromBlob(blob) {
  return URL.createObjectURL(blob);
}
