import React from "react";
import { btnStyle } from "../utils";

export default function Header({ filename, status, onNew }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "16px 28px",
        borderBottom: "1px solid var(--line)",
        background: "rgba(11,14,20,0.7)",
        backdropFilter: "blur(12px)",
        position: "sticky",
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "linear-gradient(135deg, #f59e0b 0%, #ea580c 100%)",
            display: "grid",
            placeItems: "center",
            fontWeight: 700,
            color: "#0b0e14",
            fontSize: 15,
            boxShadow: "0 4px 14px rgba(245,158,11,.35)",
          }}
        >
          CL
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 15, letterSpacing: "-0.01em" }}>CricketLens</div>
          <div style={{ fontSize: 12, color: "var(--text-3)" }}>Match Review</div>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div className="mono" style={{ fontSize: 13, color: "var(--text-2)" }}>
          {filename || "—"}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 12px",
            borderRadius: 999,
            background: "var(--bg-2)",
            border: "1px solid var(--line)",
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: status === "done" ? "var(--good)" : status === "error" ? "var(--bad)" : "var(--wicket)",
              boxShadow:
                status === "done"
                  ? "0 0 8px var(--good)"
                  : status === "error"
                  ? "0 0 8px var(--bad)"
                  : "0 0 8px var(--wicket)",
            }}
          />
          <span style={{ fontSize: 12, color: "var(--text-1)", textTransform: "capitalize" }}>{status || "idle"}</span>
        </div>
        {onNew && (
          <button style={btnStyle("ghost")} onClick={onNew}>
            New upload
          </button>
        )}
      </div>
    </header>
  );
}
