/**
 * api.js — all requests use RELATIVE paths so they go through the Vite
 * dev-server proxy (which injects the ngrok bypass header server-side).
 *
 * When the user saves a new ngrok URL, the React app calls notifyProxy(url)
 * which hits POST /__cl_set_url to update the proxy target.
 *
 * For production builds the proxy doesn't exist — but this tool is always
 * run with `npm run dev` against a Colab backend, so that's fine.
 */

// ─── Proxy target notification ─────────────────────────────────────────────

/** Tell the Vite proxy which ngrok URL to forward to. */
export async function notifyProxy(url) {
  try {
    await fetch("/__cl_set_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: (url || "").replace(/\/$/, "") }),
    });
  } catch {
    // Vite dev server not running (production build) — ignore
  }
}

// ─── Generic fetch wrapper ────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch {}
    throw new Error(msg);
  }
  return res;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function checkHealth() {
  const res = await apiFetch("/health");
  return res.json();
}

// ─── Upload (XHR for upload-progress events) ──────────────────────────────────

export function uploadVideo(file, { runCommentary = true, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);

    xhr.open("POST", `/api/upload?run_commentary=${runCommentary}`);
    // No special header needed — the Vite proxy injects ngrok-skip-browser-warning
    xhr.timeout = 0; // never timeout for large files

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Server returned invalid JSON"));
        }
      } else if (xhr.status === 503) {
        let msg = "Backend busy — another job is running";
        try {
          msg = JSON.parse(xhr.responseText).detail || msg;
        } catch {}
        reject(new Error(msg));
      } else {
        let msg = `Upload failed (${xhr.status})`;
        try {
          const errData = JSON.parse(xhr.responseText);
          msg = errData.detail || errData.message || msg;
          console.error("[uploadVideo] Backend error response:", errData);
        } catch {
          msg = xhr.responseText || msg;
          console.error("[uploadVideo] Raw response:", xhr.responseText);
        }
        reject(new Error(msg));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.ontimeout = () => reject(new Error("Upload timed out"));

    xhr.send(form);
  });
}

// ─── SSE stream ───────────────────────────────────────────────────────────────

/**
 * Subscribe to live progress via SSE.
 * Uses a relative path — the Vite proxy forwards it with the ngrok header.
 * Returns a cleanup function.
 */
export function streamProgress(jobId, onUpdate, onError) {
  // Relative path — proxy injects header, no query param needed
  const es = new EventSource(`/api/stream/${jobId}`);
  let closed = false;

  const close = () => {
    if (!closed) {
      closed = true;
      es.close();
    }
  };

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onUpdate(data);
      if (data.status === "done" || data.status === "error") close();
    } catch (err) {
      onError?.(err);
    }
  };

  es.onerror = (err) => {
    onError?.(err);
    close();
  };

  return close;
}

// ─── Jobs / Events ────────────────────────────────────────────────────────────

export async function getJob(jobId) {
  const res = await apiFetch(`/api/jobs/${jobId}`);
  return res.json();
}

export async function getEvents(jobId) {
  const res = await apiFetch(`/api/events/${jobId}`);
  return res.json();
}

export async function listJobs() {
  const res = await apiFetch("/api/jobs");
  return res.json();
}

export async function deleteJob(jobId) {
  const res = await apiFetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  return res.json();
}

// ─── Local file import (no upload — backend reads from disk path) ─────────────

/**
 * Tell the backend to start processing a file that already exists locally.
 * The server reads it in-place — no upload needed for 1.5 GB+ local videos.
 */
export async function importLocalFile(filePath, { runCommentary = true } = {}) {
  const res = await apiFetch("/api/import-local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_path: filePath, run_commentary: runCommentary }),
  });
  return res.json();
}
