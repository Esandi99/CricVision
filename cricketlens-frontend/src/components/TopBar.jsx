import React from "react";

/**
 * TopBar — fixed top bar, h-12.
 * Shows: brand, connection status dot + URL, gear icon.
 */
export default function TopBar({
  baseUrl,
  connectionStatus,
  onToggleSettings,
  phase,
  onReset,
  onStop,
}) {
  const dotColor =
    connectionStatus === "connected"
      ? "#22c55e"
      : connectionStatus === "disconnected"
        ? "#ef4444"
        : "#6b7280";

  const isPulsing = connectionStatus === "connected";

  return (
    <header
      className="flex items-center justify-between px-5 border-b border-cl-border bg-cl-surface"
      style={{ height: 48, flexShrink: 0, zIndex: 60, position: "relative" }}
    >
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 7,
            background: "linear-gradient(135deg, #f59e0b 0%, #ef4444 100%)",
            display: "grid",
            placeItems: "center",
            boxShadow: "0 0 12px rgba(239,68,68,0.4)",
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
            <circle
              cx="12"
              cy="12"
              r="10"
              fill="none"
              stroke="white"
              strokeWidth="2"
            />
            <path d="M12 2 Q16 7 12 12 Q8 7 12 2Z" fill="white" />
          </svg>
        </div>
        <span
          className="font-display text-cl-text"
          style={{ fontSize: 22, letterSpacing: "0.12em" }}
        >
          CRICVISION
        </span>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Stop button - shown during processing */}
        {phase === "processing" && (
          <button
            onClick={onStop}
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: "#ef4444",
              color: "#fff",
              border: "none",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#dc2626")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#ef4444")}
          >
            ⏹ Stop
          </button>
        )}

        {/* Home button - shown when processing is done or error */}
        {(phase === "done" || phase === "error") && (
          <button
            onClick={onReset}
            className="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: "#22c55e",
              color: "#0a0d12",
              border: "none",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#16a34a")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#22c55e")}
          >
            + New
          </button>
        )}

        {/* Status dot + URL */}
        <div className="flex items-center gap-2">
          <span
            className={isPulsing ? "conn-pulse" : ""}
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: dotColor,
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span
            className="font-mono text-cl-muted"
            style={{
              fontSize: 11,
              maxWidth: 220,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={baseUrl || "No URL set"}
          >
            {baseUrl ? baseUrl.replace(/^https?:\/\//, "") : "no backend URL"}
          </span>
        </div>

        {/* Gear button */}
        <button
          id="settings-toggle-btn"
          onClick={onToggleSettings}
          aria-label="Open settings"
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "transparent",
            border: "1px solid #1e2535",
            display: "grid",
            placeItems: "center",
            color: "#94a3b8",
            cursor: "pointer",
            transition: "background 150ms",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#1e2535")}
          onMouseLeave={(e) =>
            (e.currentTarget.style.background = "transparent")
          }
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    </header>
  );
}
