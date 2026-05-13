import React from "react";
import { fmtTime, titleCase, btnStyle } from "../utils";

export default function EventDetailCard({ event, onClose, onPrev, onNext, hasPrev, hasNext }) {
  if (!event) {
    return (
      <div
        style={{
          height: "100%",
          minHeight: 360,
          padding: 24,
          borderRadius: 14,
          background: "var(--bg-1)",
          border: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          color: "var(--text-3)",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 12,
            background: "var(--bg-3)",
            display: "grid",
            placeItems: "center",
            marginBottom: 14,
            border: "1px solid var(--line)",
          }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" strokeLinecap="round" />
          </svg>
        </div>
        <div style={{ fontWeight: 500, color: "var(--text-1)" }}>No event selected</div>
        <div style={{ fontSize: 13, marginTop: 6 }}>Click any marker on the timeline or a card below.</div>
      </div>
    );
  }

  const isWicket = event.type === "wicket";
  const accent = isWicket ? "var(--wicket)" : "var(--nearmiss)";
  const accentSoft = isWicket ? "var(--wicket-soft)" : "var(--nearmiss-soft)";

  return (
    <div
      style={{
        borderRadius: 14,
        overflow: "hidden",
        background: "var(--bg-1)",
        border: "1px solid var(--line)",
        boxShadow: "var(--shadow-1)",
      }}
    >
      <div style={{ height: 4, background: `linear-gradient(90deg, ${accent}, ${isWicket ? "#ea580c" : "#0ea5e9"})` }} />

      <div style={{ padding: 20 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "5px 10px",
              borderRadius: 999,
              background: accentSoft,
              border: `1px solid ${accent}55`,
              fontSize: 12,
              fontWeight: 600,
              color: accent,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            <span style={{ width: 7, height: 7, borderRadius: 999, background: accent, boxShadow: `0 0 6px ${accent}` }} />
            {isWicket ? `Wicket #${event.wicket_number}` : "Near miss"}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: "transparent",
              border: "1px solid var(--line)",
              display: "grid",
              placeItems: "center",
              color: "var(--text-2)",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div style={{ fontSize: 11, color: "var(--text-3)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
          Batsman
        </div>
        <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.01em", marginTop: 2 }}>
          {event.batsman || "—"}
        </div>
        {event.runs != null && (
          <div className="mono" style={{ fontSize: 13, color: "var(--text-2)", marginTop: 4 }}>
            {event.runs} ({event.balls})
          </div>
        )}

        <div
          style={{
            marginTop: 18,
            padding: "14px 16px",
            borderRadius: 10,
            background: "var(--bg-2)",
            border: "1px solid var(--line)",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-3)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {isWicket ? "Dismissal" : "Type"}
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4, color: accent }}>
            {titleCase(event.dismissal_mode || event.sub_type || "—")}
          </div>
          {event.bowler && (
            <div style={{ fontSize: 13, color: "var(--text-1)", marginTop: 8 }}>
              <span style={{ color: "var(--text-3)" }}>b </span>
              {event.bowler}
              {event.fielder && (
                <>
                  <br />
                  <span style={{ color: "var(--text-3)" }}>c </span>
                  {event.fielder}
                </>
              )}
            </div>
          )}
        </div>

        <div
          style={{
            marginTop: 14,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 1,
            background: "var(--line)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            overflow: "hidden",
          }}
        >
          {[
            ["Score", event.score],
            ["Over", event.over],
            ["Innings", event.innings],
            ["Time", fmtTime(event.delivery_ts_sec)],
          ].map(([k, v]) => (
            <div key={k} style={{ padding: "12px 14px", background: "var(--bg-1)" }}>
              <div style={{ fontSize: 11, color: "var(--text-3)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                {k}
              </div>
              <div className="mono" style={{ fontSize: 14, fontWeight: 600, marginTop: 3 }}>
                {v ?? "—"}
              </div>
            </div>
          ))}
        </div>

        {event.confidence != null && (
          <div style={{ marginTop: 14 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                color: "var(--text-2)",
                marginBottom: 6,
              }}
            >
              <span>Detection confidence</span>
              <span className="mono" style={{ color: "var(--text-1)" }}>
                {(event.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div style={{ height: 4, background: "var(--bg-3)", borderRadius: 999, overflow: "hidden" }}>
              <div
                style={{
                  width: `${event.confidence * 100}%`,
                  height: "100%",
                  background:
                    event.confidence > 0.9
                      ? "var(--good)"
                      : event.confidence > 0.75
                      ? "var(--wicket)"
                      : "var(--bad)",
                  borderRadius: 999,
                  transition: "width 240ms",
                }}
              />
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
          <button
            onClick={onPrev}
            disabled={!hasPrev}
            style={{ ...btnStyle("subtle"), flex: 1, opacity: hasPrev ? 1 : 0.4, cursor: hasPrev ? "pointer" : "default" }}
          >
            ← Prev
          </button>
          <button
            onClick={onNext}
            disabled={!hasNext}
            style={{ ...btnStyle("subtle"), flex: 1, opacity: hasNext ? 1 : 0.4, cursor: hasNext ? "pointer" : "default" }}
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
