import React, { useRef, useState } from "react";

export default function UploadScreen({ onUpload }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handleFile = (file) => {
    if (!file) return;
    onUpload(file);
  };

  return (
    <div style={{ maxWidth: 720, margin: "80px auto", padding: "0 24px" }}>
      <div style={{ textAlign: "center", marginBottom: 36 }}>
        <div
          style={{
            fontSize: 13,
            color: "var(--text-3)",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            marginBottom: 12,
          }}
        >
          Step 1 of 2
        </div>
        <h1 style={{ margin: 0, fontSize: 38, fontWeight: 600, letterSpacing: "-0.02em" }}>
          Upload a match video
        </h1>
        <p style={{ marginTop: 12, color: "var(--text-2)", fontSize: 15 }}>
          We'll detect every wicket and near-miss and give you a clickable timeline.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFile(e.dataTransfer.files[0]);
        }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${drag ? "var(--wicket)" : "var(--line-strong)"}`,
          borderRadius: 14,
          padding: "60px 24px",
          background: drag ? "var(--wicket-soft)" : "var(--bg-1)",
          textAlign: "center",
          cursor: "pointer",
          transition: "all 160ms ease",
        }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 14,
            background: "var(--bg-3)",
            margin: "0 auto 18px",
            display: "grid",
            placeItems: "center",
            border: "1px solid var(--line-strong)",
          }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 4v12m0-12l-4 4m4-4l4 4M4 20h16" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div style={{ fontSize: 16, fontWeight: 500 }}>
          Drop your video here, or <span style={{ color: "var(--wicket)" }}>click to browse</span>
        </div>
        <div className="mono" style={{ marginTop: 10, color: "var(--text-3)", fontSize: 13 }}>
          .mp4 · .mkv · .avi · .mov · .ts — up to 10 GB
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
      </div>

      <div style={{ marginTop: 28, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
        {[
          { n: "01", t: "Scan", d: "YOLO + OCR detect score-strip and graphics every 2s" },
          { n: "02", t: "Detect", d: "5-signal wicket detection, dismissal cards, commentary" },
          { n: "03", t: "Review", d: "Clickable timeline with full event metadata" },
        ].map((s) => (
          <div
            key={s.n}
            style={{ padding: 16, borderRadius: 10, background: "var(--bg-1)", border: "1px solid var(--line)" }}
          >
            <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", marginBottom: 8 }}>{s.n}</div>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{s.t}</div>
            <div style={{ fontSize: 13, color: "var(--text-2)" }}>{s.d}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
