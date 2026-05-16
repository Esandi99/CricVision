import React, { useEffect, useRef, useState } from "react";
import {
  checkHealth,
  listJobs,
  deleteJob,
  getEvents,
  notifyProxy,
} from "../api.js";
import { timeAgo } from "../utils.js";

/**
 * SettingsPanel — slides in from the right.
 * Handles: URL input, test connection, run-commentary toggle, job history.
 */
export default function SettingsPanel({
  open,
  baseUrl,
  runCommentary,
  onClose,
  onSaveUrl,
  onToggleCommentary,
  onLoadResults, // (jobId, results) => void
}) {
  const [urlDraft, setUrlDraft] = useState(baseUrl);
  const [testStatus, setTestStatus] = useState(null); // null | "testing" | "ok" | "fail"
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const inputRef = useRef(null);

  // Sync draft when baseUrl changes externally
  useEffect(() => {
    setUrlDraft(baseUrl);
  }, [baseUrl]);

  // Load job history whenever panel opens
  useEffect(() => {
    if (!open || !baseUrl) return;
    setJobsLoading(true);
    listJobs()
      .then(setJobs)
      .catch(() => setJobs([]))
      .finally(() => setJobsLoading(false));
  }, [open, baseUrl]);

  const handleSave = () => {
    const trimmed = urlDraft.trim().replace(/\/$/, "");
    onSaveUrl(trimmed);
    setTestStatus(null);
  };

  const handleTest = async () => {
    const url = urlDraft.trim().replace(/\/$/, "");
    if (!url) return;
    setTestStatus("testing");
    try {
      // Sync the proxy target to the draft URL before testing
      await notifyProxy(url);
      await checkHealth();
      setTestStatus("ok");
    } catch {
      setTestStatus("fail");
    }
  };

  const handleLoadJob = async (job) => {
    if (job.status !== "done") return;
    try {
      const evData = await getEvents(job.job_id);
      // Ensure arrays and defaults
      evData.events = Array.isArray(evData.events) ? evData.events : [];
      evData.duration_sec = evData.duration_sec ?? 0;
      evData.wicket_count = evData.wicket_count ?? 0;
      evData.nm_count = evData.nm_count ?? 0;
      onLoadResults(job.job_id, evData);
      onClose();
    } catch (err) {
      alert("Failed to load job: " + err.message);
    }
  };

  const handleDeleteJob = async (e, jobId) => {
    e.stopPropagation();
    try {
      await deleteJob(jobId);
      setJobs((prev) => prev.filter((j) => j.job_id !== jobId));
    } catch (err) {
      alert("Delete failed: " + err.message);
    }
  };

  const statusBadge = (s) => {
    const styles = {
      done: { background: "rgba(34,197,94,0.15)", color: "#22c55e" },
      processing: { background: "rgba(245,158,11,0.15)", color: "#f59e0b" },
      error: { background: "rgba(239,68,68,0.15)", color: "#ef4444" },
      pending: { background: "rgba(100,116,139,0.15)", color: "#94a3b8" },
      uploading: { background: "rgba(99,102,241,0.15)", color: "#818cf8" },
    };
    const st = styles[s] || styles.pending;
    return (
      <span
        style={{
          ...st,
          padding: "2px 7px",
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {s}
      </span>
    );
  };

  if (!open) return null;

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 70,
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(2px)",
        }}
      />

      {/* Panel */}
      <aside
        className="settings-panel-open scrollbar-thin"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          bottom: 0,
          width: 320,
          zIndex: 80,
          background: "#111620",
          borderLeft: "1px solid #1e2535",
          display: "flex",
          flexDirection: "column",
          overflowY: "auto",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderBottom: "1px solid #1e2535",
          }}
        >
          <span style={{ fontWeight: 600, fontSize: 14 }}>Settings</span>
          <button
            onClick={onClose}
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: "transparent",
              border: "1px solid #1e2535",
              display: "grid",
              placeItems: "center",
              color: "#94a3b8",
              cursor: "pointer",
            }}
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div
          style={{
            padding: "20px",
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 28,
          }}
        >
          {/* ── Section 1: Backend URL ── */}
          <section>
            <div
              style={{
                fontSize: 11,
                color: "#94a3b8",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Backend URL
            </div>
            <input
              ref={inputRef}
              id="settings-url-input"
              value={urlDraft}
              onChange={(e) => {
                setUrlDraft(e.target.value);
                setTestStatus(null);
              }}
              placeholder="http://localhost:8000"
              style={{
                width: "100%",
                padding: "9px 12px",
                borderRadius: 8,
                background: "#0a0d12",
                border: "1px solid #1e2535",
                color: "#e2e8f0",
                fontSize: 12,
                fontFamily: "'JetBrains Mono', monospace",
                outline: "none",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#22c55e")}
              onBlur={(e) => (e.target.style.borderColor = "#1e2535")}
            />

            {/* Test status */}
            {testStatus === "ok" && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#22c55e" }}>
                ✓ Connected
              </div>
            )}
            {testStatus === "fail" && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#ef4444" }}>
                ✗ Could not connect
              </div>
            )}
            {testStatus === "testing" && (
              <div style={{ marginTop: 6, fontSize: 12, color: "#94a3b8" }}>
                Testing…
              </div>
            )}

            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <button
                id="settings-save-url-btn"
                onClick={handleSave}
                style={{
                  flex: 1,
                  padding: "8px 0",
                  borderRadius: 7,
                  background: "#22c55e",
                  border: "none",
                  color: "#0a0d12",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Save
              </button>
              <button
                id="settings-test-btn"
                onClick={handleTest}
                style={{
                  flex: 1,
                  padding: "8px 0",
                  borderRadius: 7,
                  background: "transparent",
                  border: "1px solid #1e2535",
                  color: "#e2e8f0",
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                Test
              </button>
            </div>
          </section>

          {/* ── Section 2: Options ── */}
          <section>
            <div
              style={{
                fontSize: 11,
                color: "#94a3b8",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Options
            </div>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              <div
                id="commentary-toggle"
                onClick={onToggleCommentary}
                style={{
                  width: 40,
                  height: 22,
                  borderRadius: 11,
                  cursor: "pointer",
                  background: runCommentary ? "#22c55e" : "#1e2535",
                  position: "relative",
                  transition: "background 200ms",
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    top: 3,
                    left: runCommentary ? 21 : 3,
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    background: "#fff",
                    transition: "left 200ms",
                  }}
                />
              </div>
              Run commentary analysis
            </label>
            <div
              style={{
                fontSize: 11,
                color: "#4a5568",
                marginTop: 4,
                paddingLeft: 52,
              }}
            >
              Uses Whisper to transcribe audio and enrich events
            </div>
          </section>

          {/* ── Section 3: Job History ── */}
          <section style={{ flex: 1 }}>
            <div
              style={{
                fontSize: 11,
                color: "#94a3b8",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Job History
            </div>
            {jobsLoading && (
              <div style={{ fontSize: 12, color: "#4a5568" }}>Loading…</div>
            )}
            {!jobsLoading && jobs.length === 0 && (
              <div style={{ fontSize: 12, color: "#4a5568" }}>No jobs yet.</div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {jobs
                .slice()
                .reverse()
                .map((job) => (
                  <div
                    key={job.job_id}
                    onClick={() => handleLoadJob(job)}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      background: "#0a0d12",
                      border: "1px solid #1e2535",
                      cursor: job.status === "done" ? "pointer" : "default",
                      opacity: job.status === "done" ? 1 : 0.6,
                      transition: "background 120ms",
                    }}
                    onMouseEnter={(e) => {
                      if (job.status === "done")
                        e.currentTarget.style.background = "#14192b";
                    }}
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.background = "#0a0d12")
                    }
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {job.filename || job.job_id}
                      </span>
                      <button
                        onClick={(e) => handleDeleteJob(e, job.job_id)}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "#4a5568",
                          cursor: "pointer",
                          padding: 2,
                          flexShrink: 0,
                        }}
                        title="Delete job"
                      >
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                        >
                          <path
                            d="M6 6l12 12M18 6L6 18"
                            strokeLinecap="round"
                          />
                        </svg>
                      </button>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginTop: 5,
                      }}
                    >
                      {statusBadge(job.status)}
                      {job.wicket_count != null && (
                        <span style={{ fontSize: 11, color: "#4a5568" }}>
                          {job.wicket_count}W · {job.nm_count ?? 0}NM
                        </span>
                      )}
                      <span
                        style={{
                          fontSize: 11,
                          color: "#4a5568",
                          marginLeft: "auto",
                        }}
                      >
                        {timeAgo(job.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          </section>
        </div>
      </aside>
    </>
  );
}
