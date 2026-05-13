import React from "react";
import { fmtTime, titleCase } from "../utils";

export default function EventCard({ event, active, onClick }) {
  const isWicket = event.type === "wicket";
  const accent = isWicket ? "var(--wicket)" : "var(--nearmiss)";
  return (
    <button
      onClick={onClick}
      style={{
        textAlign: "left",
        padding: 16,
        borderRadius: 12,
        background: active ? "var(--bg-2)" : "var(--bg-1)",
        border: `1px solid ${active ? accent + "88" : "var(--line)"}`,
        boxShadow: active ? `0 0 0 3px ${isWicket ? "var(--wicket-soft)" : "var(--nearmiss-soft)"}` : "none",
        position: "relative",
        overflow: "hidden",
        transition: "all 160ms ease",
        cursor: "pointer",
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.borderColor = "var(--line-strong)";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.borderColor = "var(--line)";
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: accent,
          opacity: active ? 1 : 0.6,
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "3px 8px",
            borderRadius: 999,
            background: isWicket ? "var(--wicket-soft)" : "var(--nearmiss-soft)",
            color: accent,
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {isWicket ? `W${event.wicket_number}` : "Near miss"}
        </div>
        <div className="mono" style={{ fontSize: 12, color: "var(--text-3)" }}>
          {fmtTime(event.delivery_ts_sec)}
        </div>
      </div>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4, letterSpacing: "-0.01em" }}>
        {event.batsman || "Unknown"}
      </div>
      <div style={{ fontSize: 13, color: "var(--text-2)" }}>
        {titleCase(event.dismissal_mode || event.sub_type || "")}
        {event.bowler && <span style={{ color: "var(--text-3)" }}> · b {event.bowler}</span>}
      </div>
      <div
        className="mono"
        style={{
          marginTop: 12,
          paddingTop: 10,
          borderTop: "1px solid var(--line)",
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <span style={{ fontSize: 12, color: "var(--text-2)" }}>{event.score || "—"}</span>
        <span style={{ fontSize: 12, color: "var(--text-3)" }}>Over {event.over || "—"}</span>
      </div>
    </button>
  );
}
