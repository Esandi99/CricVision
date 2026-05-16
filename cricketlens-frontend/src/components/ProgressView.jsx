import React from "react";
import { formatFileSize } from "../utils.js";

const STAGES = [
  { label: "Video Info", min: 0,  max: 5  },
  { label: "Frame Scan", min: 5,  max: 44 },
  { label: "Events",     min: 44, max: 46 },
  { label: "Cards",      min: 46, max: 65 },
  { label: "Extraction", min: 65, max: 84 },
  { label: "Commentary", min: 84, max: 97 },
  { label: "Done",       min: 97, max: 100 },
];

function activeStageIndex(pct) {
  for (let i = STAGES.length - 1; i >= 0; i--) {
    if (pct >= STAGES[i].min) return i;
  }
  return 0;
}

/**
 * ProgressView — shown during uploading and processing phases.
 */
export default function ProgressView({
  phase,
  uploadProgress,
  pipelineProgress,
  pipelineMessage,
  pipelineError,
  filename,
  onReset,
}) {
  const isUploading  = phase === "uploading";
  const isProcessing = phase === "processing";
  const stageIdx     = isProcessing ? activeStageIndex(pipelineProgress) : -1;

  if (phase === "error") {
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: 32 }}>
        <div style={{
          maxWidth: 520,
          background: "rgba(239,68,68,0.08)",
          border: "1px solid rgba(239,68,68,0.3)",
          borderRadius: 14,
          padding: "28px 32px",
          textAlign: "center",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚠</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "#ef4444", marginBottom: 8 }}>Processing failed</div>
          <div className="font-mono" style={{ fontSize: 12, color: "#94a3b8", wordBreak: "break-all" }}>
            {pipelineError || "Unknown error"}
          </div>
          <button
            id="progress-retry-btn"
            onClick={onReset}
            style={{
              marginTop: 20,
              padding: "10px 32px",
              borderRadius: 8,
              background: "#ef4444",
              border: "none",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  const barPct  = isUploading ? uploadProgress : pipelineProgress;
  const barMax  = 100;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: "32px 40px" }}>
      <div style={{ width: "100%", maxWidth: 580 }}>
        {/* Phase label */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div style={{ fontSize: 13, color: "#94a3b8" }}>
            {isUploading ? "Uploading" : "Processing"}{filename ? ` · ` : ""}<span className="font-mono" style={{ color: "#e2e8f0" }}>{filename}</span>
          </div>
          <div className="font-mono" style={{ fontSize: 13, color: "#22c55e" }}>
            {Math.round(barPct)}%
          </div>
        </div>

        {/* Progress bar */}
        <div style={{ height: 6, background: "#1e2535", borderRadius: 3, overflow: "hidden", marginBottom: 12 }}>
          <div
            className={isProcessing ? "progress-shimmer" : ""}
            style={{
              height: "100%",
              width: `${barPct}%`,
              borderRadius: 3,
              background: isUploading ? "linear-gradient(90deg, #6366f1, #8b5cf6)" : undefined,
              transition: "width 600ms ease",
            }}
          />
        </div>

        {/* Live log line */}
        {pipelineMessage && (
          <div
            className="font-mono"
            style={{
              fontSize: 11,
              color: "#4a5568",
              marginBottom: 20,
              minHeight: 16,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {pipelineMessage}
          </div>
        )}

        {/* Stage strip — only during pipeline */}
        {isProcessing && (
          <div style={{ display: "flex", gap: 4 }}>
            {STAGES.map((s, i) => {
              const isActive    = i === stageIdx;
              const isCompleted = i < stageIdx;
              return (
                <div
                  key={s.label}
                  style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
                >
                  {/* Dot */}
                  <div
                    className={isActive ? "stage-active-dot" : ""}
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: "50%",
                      background: isActive ? "#22c55e" : isCompleted ? "#16a34a" : "#1e2535",
                      border: `1px solid ${isActive ? "#22c55e" : isCompleted ? "#16a34a" : "#2d3a52"}`,
                    }}
                  />
                  {/* Label */}
                  <div style={{
                    fontSize: 9,
                    textAlign: "center",
                    color: isActive ? "#22c55e" : isCompleted ? "#4a5568" : "#2d3a52",
                    fontWeight: isActive ? 600 : 400,
                    whiteSpace: "nowrap",
                  }}>
                    {isCompleted ? "✓ " : ""}{s.label}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Upload hint */}
        {isUploading && (
          <div style={{ marginTop: 24, padding: "12px 16px", background: "#111620", border: "1px solid #1e2535", borderRadius: 10, fontSize: 12, color: "#4a5568" }}>
            Large files may take several minutes to transfer. Don't close this tab.
          </div>
        )}

        {/* Processing hint */}
        {isProcessing && (
          <div style={{ marginTop: 24, padding: "12px 16px", background: "#111620", border: "1px solid #1e2535", borderRadius: 10, fontSize: 12, color: "#4a5568" }}>
            YOLO, OCR, and Whisper are running locally — typically 0.3–0.5× video length on GPU, longer on CPU.
          </div>
        )}
      </div>
    </div>
  );
}
