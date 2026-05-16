import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { Readable } from "stream";

/**
 * Dynamic proxy plugin — rewritten to use Node.js native fetch (undici).
 *
 * WHY fetch instead of https.request:
 *   The raw https.request approach was returning 502 due to TLS/SNI
 *   handshake failures when connecting to ngrok on Windows.  Node's
 *   built-in fetch (Node ≥ 18, backed by undici) handles modern TLS,
 *   HTTP/2 negotiation, and connection keep-alive correctly out of the box.
 *
 * HOW:
 *   React calls  POST /__cl_set_url  to update the proxy target.
 *   All /api/* and /health requests are forwarded server-side so the
 *   browser never touches ngrok directly (no CORS).
 *   Request bodies are streamed (Readable.toWeb) — no memory spike on
 *   large video uploads.  Response bodies are streamed back via a
 *   ReadableStream reader loop, which works for SSE and video Range.
 */

// Default target = local backend.  Override at runtime via Settings → Backend URL
// (which calls POST /__cl_set_url).  This keeps the proxy working out-of-the-box
// for local development without any configuration.
let _backendUrl = "http://localhost:8000";

function dynamicProxyPlugin() {
  return {
    name: "cl-dynamic-proxy",
    configureServer(server) {
      // ── 1. Update proxy target ─────────────────────────────────────────
      server.middlewares.use((req, res, next) => {
        if (req.url !== "/__cl_set_url" || req.method !== "POST") return next();
        let body = "";
        req.on("data", (d) => (body += d));
        req.on("end", () => {
          try {
            const parsed = JSON.parse(body);
            _backendUrl = (parsed.url || "").replace(/\/$/, "");
            console.log(`[cl-proxy] target → ${_backendUrl}`);
          } catch {}
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end('{"ok":true}');
        });
      });

      // ── 2. OPTIONS preflight ───────────────────────────────────────────
      server.middlewares.use((req, res, next) => {
        if (req.method !== "OPTIONS") return next();
        const p = req.url.split("?")[0];
        if (!p.startsWith("/api/") && p !== "/health") return next();
        res.writeHead(204, {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Headers": "*",
          "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
          "Access-Control-Max-Age": "86400",
        });
        res.end();
      });

      // ── 3. Main proxy (fetch-based) ────────────────────────────────────
      server.middlewares.use(async (req, res, next) => {
        const pathname = req.url.split("?")[0];
        if (!pathname.startsWith("/api/") && pathname !== "/health") {
          return next();
        }

        if (!_backendUrl) {
          console.log("[cl-proxy] No backend URL configured");
          res.writeHead(503, { "Content-Type": "application/json" });
          res.end(
            JSON.stringify({
              detail: "No backend URL configured. Set it in Settings.",
            }),
          );
          return;
        }

        let targetUrl;
        try {
          targetUrl = new URL(req.url, _backendUrl);
        } catch (err) {
          console.error(`[cl-proxy] Bad target URL: ${err.message}`);
          res.writeHead(400);
          res.end("Bad target URL");
          return;
        }

        console.log(
          `[cl-proxy] Forwarding ${req.method} ${req.url} → ${targetUrl}`,
        );

        // Build forwarded headers — strip hop-by-hop, inject ngrok header
        const fwdHeaders = {};
        for (const [k, v] of Object.entries(req.headers)) {
          const kl = k.toLowerCase();
          if (
            [
              "host",
              "connection",
              "upgrade",
              "transfer-encoding",
              "keep-alive",
              "proxy-authorization",
              "proxy-authenticate",
              "te",
              "trailers",
            ].includes(kl)
          )
            continue;
          // Drop content-length for bodyless requests
          if (
            (req.method === "GET" || req.method === "HEAD") &&
            kl === "content-length"
          )
            continue;
          fwdHeaders[k] = v;
        }
        fwdHeaders["host"] = targetUrl.hostname;
        fwdHeaders["ngrok-skip-browser-warning"] = "true";

        const hasBody = req.method !== "GET" && req.method !== "HEAD";

        try {
          let body = undefined;

          if (hasBody) {
            // Stream the request body directly — no buffering.
            // Node.js 18+ fetch (undici) accepts a Node Readable stream
            // as body when duplex:'half' is set.  This is crucial for
            // large video uploads (1-2 GB) that would OOM if buffered.
            body = req;
          }

          // 30-minute timeout — large local video uploads need time
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 1800000);

          let fetchRes;
          try {
            fetchRes = await fetch(targetUrl.toString(), {
              method: req.method,
              headers: fwdHeaders,
              body: body,
              signal: controller.signal,
              // duplex:'half' is REQUIRED by undici (Node 18+ fetch) when body
              // is a stream (Readable). Without it the upload silently stalls.
              ...(body ? { duplex: "half" } : {}),
            });
          } finally {
            clearTimeout(timeoutId);
          }

          console.log(`[cl-proxy] Backend responded with ${fetchRes.status}`);

          // Forward response headers + inject CORS
          const responseHeaders = {};
          fetchRes.headers.forEach((v, k) => {
            responseHeaders[k] = v;
          });
          responseHeaders["access-control-allow-origin"] = "*";
          responseHeaders["access-control-allow-headers"] = "*";
          responseHeaders["access-control-expose-headers"] =
            "Content-Range, Accept-Ranges, Content-Length, Content-Type";

          res.writeHead(fetchRes.status, responseHeaders);

          if (!fetchRes.body) {
            res.end();
            return;
          }

          // Stream the response body back to the browser.
          // This works for JSON, SSE, and video Range responses.
          const reader = fetchRes.body.getReader();
          res.on("close", () => reader.cancel().catch(() => {}));

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done || res.destroyed) break;
              res.write(value);
            }
          } finally {
            res.end();
          }
        } catch (err) {
          console.error(
            `[cl-proxy] Error: ${req.method} ${targetUrl} → ${err.message}`,
          );
          console.error(
            `[cl-proxy] Error name: ${err.name}, code: ${err.code}`,
          );
          console.error(err.stack);

          // Provide helpful error message
          let errorDetail = err.message;
          if (err.name === "AbortError") {
            errorDetail =
              "Request timeout (>30min). Backend may be unresponsive.";
          } else if (err.message.includes("ECONNREFUSED")) {
            errorDetail = `Cannot connect to backend at ${targetUrl.hostname}. Is the backend running?`;
          } else if (err.message.includes("ETIMEDOUT")) {
            errorDetail =
              "Network timeout. Backend may be unreachable or very slow.";
          } else if (err.message.includes("ENOTFOUND")) {
            errorDetail = `DNS resolution failed for ${targetUrl.hostname}. Check the backend URL.`;
          }

          if (!res.headersSent) {
            res.writeHead(502, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: `Proxy error: ${errorDetail}` }));
          }
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), dynamicProxyPlugin()],
  server: {
    strictPort: false,
  },
});
