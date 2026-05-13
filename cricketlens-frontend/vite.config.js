import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const BACKEND = env.VITE_BACKEND_URL || "https://armless-candle-duffel.ngrok-free.dev";

  /**
   * WHY WE ONLY PROXY /api/stream
   * ─────────────────────────────
   * fetch() and XHR can send custom headers, so they go DIRECTLY to the ngrok
   * URL (set in VITE_API_BASE) with  ngrok-skip-browser-warning: true.
   *
   * EventSource (SSE) has NO header API — it cannot bypass ngrok's browser
   * warning interstitial on its own.  The Vite proxy adds the header for it.
   *
   * Routing large uploads through the proxy caused ERR_CONNECTION_RESET
   * because Vite's http-proxy buffers the entire request body before
   * forwarding it, and the default 60 s timeout kills long uploads.
   */
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // SSE only — long-lived connection, generous timeout
        "/api/stream": {
          target:      BACKEND,
          changeOrigin: true,
          secure:      true,
          headers:     { "ngrok-skip-browser-warning": "true" },
          // 1-hour timeout — jobs can run for a very long time
          proxyTimeout: 3_600_000,
          timeout:      3_600_000,
        },
      },
    },
  };
});

