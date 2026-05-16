import React, { useEffect, useRef } from "react";
import {
  formatTime,
  dismissalModeStyle,
  formatNmType,
  nmTypeIcon,
  titleCase,
} from "../utils.js";

/**
 * EventPanel — right-side scrollable panel with tabs + event cards.
 */
export default function EventPanel({
  results,
  activeTab,
  onTabChange,
  activeEventId,
  onSelectEvent, // (eventId, tsSec) => void
}) {
  const {
    events = [],
    duration_sec = 0,
    wicket_count = 0,
    nm_count = 0,
  } = results || {};

  // Safety check: ensure events is an array
  const eventArray = Array.isArray(events) ? events : [];

  const filtered = eventArray.filter((ev) => {
    if (activeTab === "wickets") return ev.type === "wicket";
    if (activeTab === "near_misses") return ev.type === "near_miss";
    return true;
  });

  const sorted = [...filtered].sort(
    (a, b) => (a.ts_sec ?? 0) - (b.ts_sec ?? 0),
  );
  const activeRef = useRef(null);

  // Scroll active card into view
  useEffect(() => {
    if (activeEventId && activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [activeEventId]);

  const tabs = [
    { key: "all", label: "All", count: eventArray.length },
    { key: "wickets", label: "Wickets", count: wicket_count },
    { key: "near_misses", label: "Near Misses", count: nm_count },
  ];

  return (
    <div
      style={{
        width: 384,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        background: "#111620",
        borderLeft: "1px solid #1e2535",
        overflow: "hidden",
      }}
    >
      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid #1e2535",
          flexShrink: 0,
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            id={`tab-${t.key}`}
            onClick={() => onTabChange(t.key)}
            style={{
              flex: 1,
              padding: "10px 0",
              background: "transparent",
              border: "none",
              borderBottom:
                activeTab === t.key
                  ? "2px solid #22c55e"
                  : "2px solid transparent",
              color: activeTab === t.key ? "#22c55e" : "#4a5568",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              transition: "color 150ms",
              letterSpacing: "0.04em",
            }}
          >
            {t.label}{" "}
            {t.count > 0 && (
              <span
                style={{
                  marginLeft: 4,
                  padding: "1px 5px",
                  borderRadius: 10,
                  background:
                    activeTab === t.key ? "rgba(34,197,94,0.15)" : "#1e2535",
                  color: activeTab === t.key ? "#22c55e" : "#6b7280",
                  fontSize: 10,
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Summary strip */}
      <div
        style={{
          padding: "7px 14px",
          fontSize: 11,
          color: "#4a5568",
          borderBottom: "1px solid #1e2535",
          flexShrink: 0,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {wicket_count} wickets · {nm_count} near misses
        {duration_sec ? ` · ${formatTime(duration_sec)}` : ""}
      </div>

      {/* Cards list */}
      <div
        className="scrollbar-thin"
        style={{ flex: 1, overflowY: "auto", padding: "10px 10px" }}
      >
        {sorted.length === 0 && (
          <div
            style={{
              padding: 24,
              textAlign: "center",
              color: "#4a5568",
              fontSize: 13,
            }}
          >
            No events match this filter.
          </div>
        )}
        {sorted.map((ev) => {
          const isActive = ev.event_id === activeEventId;
          const ref = isActive ? activeRef : null;
          return (
            <div key={ev.event_id} ref={ref}>
              {ev.type === "wicket" ? (
                <WicketCard
                  ev={ev}
                  isActive={isActive}
                  onSelect={onSelectEvent}
                />
              ) : (
                <NearMissCard
                  ev={ev}
                  isActive={isActive}
                  onSelect={onSelectEvent}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Wicket Card ──────────────────────────────────────────────────────────── */
function WicketCard({ ev, isActive, onSelect }) {
  const modeStyle = dismissalModeStyle(ev.dismissal_mode);
  const extractionBadge =
    ev.extraction_method === "vlm"
      ? {
          label: "VLM",
          style: { background: "rgba(34,197,94,0.15)", color: "#22c55e" },
        }
      : ev.extraction_method === "ocr"
        ? {
            label: "OCR",
            style: { background: "rgba(99,102,241,0.15)", color: "#818cf8" },
          }
        : null;

  return (
    <div
      className="event-card"
      id={`event-card-${ev.event_id}`}
      onClick={() => onSelect(ev.event_id, ev.ts_sec ?? 0)}
      style={{
        marginBottom: 8,
        borderRadius: 10,
        border: "1px solid",
        borderColor: isActive ? "rgba(239,68,68,0.4)" : "#1e2535",
        borderLeft: `4px solid #ef4444`,
        background: isActive ? "rgba(239,68,68,0.05)" : "#0a0d12",
        padding: "11px 13px",
        boxShadow: isActive ? "0 0 0 1px rgba(239,68,68,0.2)" : "none",
      }}
    >
      {/* Row 1 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 5,
        }}
      >
        <span
          className="font-display"
          style={{ fontSize: 18, color: "#ef4444", letterSpacing: "0.05em" }}
        >
          W{ev.innings_wicket}
        </span>
        <span style={{ fontSize: 10, color: "#4a5568", marginRight: "auto" }}>
          INN {ev.innings}
        </span>
        {extractionBadge && (
          <span
            style={{
              ...extractionBadge.style,
              padding: "1px 5px",
              borderRadius: 4,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.06em",
            }}
          >
            {extractionBadge.label}
          </span>
        )}
        <span className="font-mono" style={{ fontSize: 10, color: "#4a5568" }}>
          {formatTime(ev.ts_sec)}
        </span>
      </div>

      {/* Row 2: batsman */}
      <div
        className="font-display"
        style={{
          fontSize: 20,
          color: "#e2e8f0",
          letterSpacing: "0.03em",
          marginBottom: 4,
        }}
      >
        {ev.batsman || "—"}
      </div>

      {/* Row 3: mode · over · score */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
          marginBottom: 4,
        }}
      >
        <span
          className="mode-badge"
          style={{
            ...modeStyle,
            borderRadius: 4,
            fontSize: 10,
            padding: "2px 7px",
            fontWeight: 700,
          }}
        >
          {titleCase(ev.dismissal_mode || "unknown")}
        </span>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>ov {ev.over}</span>
        <span style={{ fontSize: 12, color: "#94a3b8" }}>{ev.score}</span>
      </div>

      {/* Row 4: bowler / fielder */}
      {ev.bowler && (
        <div style={{ fontSize: 11, color: "#4a5568", marginBottom: 2 }}>
          ↳ {ev.bowler}
          {ev.fielder ? ` · c ${ev.fielder}` : ""}
        </div>
      )}

      {/* Row 5: runs (balls) */}
      {ev.runs != null && (
        <div className="font-mono" style={{ fontSize: 11, color: "#6b7280" }}>
          {ev.runs}({ev.balls})
        </div>
      )}
    </div>
  );
}

/* ── Near-Miss Card ───────────────────────────────────────────────────────── */
function NearMissCard({ ev, isActive, onSelect }) {
  const icon = nmTypeIcon(ev.nm_type);
  const typeLabel = formatNmType(ev.nm_type);
  const confPct = Math.round((ev.confidence ?? 0) * 100);

  return (
    <div
      className="event-card"
      id={`event-card-${ev.event_id}`}
      onClick={() => onSelect(ev.event_id, ev.ts_sec ?? 0)}
      style={{
        marginBottom: 8,
        borderRadius: 10,
        border: "1px solid",
        borderColor: isActive ? "rgba(245,158,11,0.4)" : "#1e2535",
        borderLeft: `4px solid #f59e0b`,
        background: isActive ? "rgba(245,158,11,0.05)" : "#0a0d12",
        padding: "11px 13px",
        boxShadow: isActive ? "0 0 0 1px rgba(245,158,11,0.2)" : "none",
      }}
    >
      {/* Row 1 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: 5,
        }}
      >
        <span
          className="font-display"
          style={{ fontSize: 18, color: "#f59e0b", letterSpacing: "0.05em" }}
        >
          NM{ev.nm_number}
        </span>
        <span style={{ fontSize: 10, color: "#4a5568", marginRight: "auto" }}>
          INN {ev.innings}
        </span>
        <span className="font-mono" style={{ fontSize: 10, color: "#4a5568" }}>
          {formatTime(ev.ts_sec)}
        </span>
      </div>

      {/* Row 2: icon + type */}
      <div
        className="font-display"
        style={{
          fontSize: 19,
          color: "#e2e8f0",
          letterSpacing: "0.02em",
          marginBottom: 4,
        }}
      >
        {icon} {typeLabel}
      </div>

      {/* Row 3: fielding position */}
      {ev.fielding_position && (
        <div style={{ fontSize: 11, color: "#4a5568", marginBottom: 4 }}>
          {ev.fielding_position}
        </div>
      )}

      {/* Row 4: confidence bar */}
      <div style={{ marginBottom: 4 }}>
        <div
          style={{
            height: 3,
            background: "#1e2535",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <div className="confidence-bar" style={{ width: `${confPct}%` }} />
        </div>
        <div
          className="font-mono"
          style={{ fontSize: 10, color: "#4a5568", marginTop: 2 }}
        >
          {confPct}% confidence
        </div>
      </div>

      {/* Row 5: appeal / not out */}
      {ev.has_appeal && ev.has_not_out && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            padding: "2px 8px",
            borderRadius: 4,
            background: "rgba(245,158,11,0.12)",
            border: "1px solid rgba(245,158,11,0.25)",
            fontSize: 10,
            color: "#f59e0b",
            fontWeight: 600,
          }}
        >
          🔔 Appeal — Not out
        </div>
      )}
    </div>
  );
}
