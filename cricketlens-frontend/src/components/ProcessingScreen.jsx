import React from "react";

export default function ProcessingScreen({ filename, progress, message, uploadProgress }) {
  // Combine upload phase (0-15%) with processing phase (15-100%) for smoother UX.
  const overall = uploadProgress < 1 ? uploadProgress * 0.15 : 0.15 + progress * 0.85;
  const C = 2 * Math.PI * 38;

  return (
    <div style={{ maxWidth: 600, margin: "120px auto", padding: "0 24px", textAlign: "center" }}>
      <div style={{ position: "relative", width: 88, height: 88, margin: "0 auto 28px" }}>
        <svg width="88" height="88" viewBox="0 0 88 88">
          <circle cx="44" cy="44" r="38" fill="none" stroke="var(--bg-3)" strokeWidth="6" />
          <circle
            cx="44"
            cy="44"
            r="38"
            fill="none"
            stroke="var(--wicket)"
            strokeWidth="6"
            strokeDasharray={`${C}`}
            strokeDashoffset={`${C * (1 - overall)}`}
            strokeLinecap="round"
            transform="rotate(-90 44 44)"
            style={{ transition: "stroke-dashoffset 600ms ease" }}
          />
        </svg>
        <div
          className="mono"
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            fontWeight: 600,
            fontSize: 18,
          }}
        >
          {Math.round(overall * 100)}%
        </div>
      </div>
      <h2 style={{ margin: 0, fontSize: 22, fontWeight: 600 }}>{message || "Processing…"}</h2>
      <div className="mono" style={{ marginTop: 8, color: "var(--text-3)", fontSize: 13 }}>{filename}</div>
      <div
        style={{
          marginTop: 28,
          padding: "14px 18px",
          background: "var(--bg-1)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          color: "var(--text-2)",
          fontSize: 13,
        }}
      >
        Heavy ML models — YOLO, OCR, Whisper — run on the backend. This usually takes 0.3-0.5× the video duration.
      </div>
    </div>
  );
}
