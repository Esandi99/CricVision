import React, { useEffect, useReducer, useRef, useCallback } from "react";
import { reducer, initialState, A } from "./reducer.js";
import {
  checkHealth,
  uploadVideo,
  importLocalFile,
  streamProgress,
  getJob,
  getEvents,
  notifyProxy,
  deleteJob,
} from "./api.js";

import TopBar from "./components/TopBar.jsx";
import SettingsPanel from "./components/SettingsPanel.jsx";
import UploadZone from "./components/UploadZone.jsx";
import ProgressView from "./components/ProgressView.jsx";
import VideoPlayer from "./components/VideoPlayer.jsx";
import MatchTimeline from "./components/MatchTimeline.jsx";
import EventPanel from "./components/EventPanel.jsx";

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const {
    baseUrl,
    connectionStatus,
    backendBusy,
    uploadFile,
    runCommentary,
    phase,
    uploadProgress,
    pipelineProgress,
    pipelineMessage,
    pipelineError,
    jobId,
    results,
    activeEventId,
    settingsOpen,
    activeTab,
  } = state;

  // Shared time ref for VideoPlayer → MatchTimeline (no re-renders)
  const timeRef = useRef(0);
  const videoRef = useRef(null); // forwarded to VideoPlayer via a callback ref
  const cleanupRef = useRef(null); // store SSE cleanup function

  // ── Health check ──────────────────────────────────────────────────────────
  // notifyProxy is called first on every check so _backendUrl is guaranteed
  // to be set before the /health request reaches the Vite proxy middleware.

  const doHealthCheck = useCallback(async () => {
    if (!baseUrl) {
      dispatch({ type: A.SET_CONNECTION, payload: { status: "disconnected" } });
      return;
    }
    await notifyProxy(baseUrl); // sync proxy target before every request
    try {
      const data = await checkHealth();
      dispatch({
        type: A.SET_CONNECTION,
        payload: { status: "connected", busy: data.busy ?? false },
      });
    } catch {
      dispatch({ type: A.SET_CONNECTION, payload: { status: "disconnected" } });
    }
  }, [baseUrl]);

  // Poll every 15 s
  useEffect(() => {
    doHealthCheck();
    const id = setInterval(doHealthCheck, 15_000);
    return () => clearInterval(id);
  }, [doHealthCheck]);

  // ── On-mount: restore last job ────────────────────────────────────────────

  useEffect(() => {
    const lastJobId = localStorage.getItem("cl_last_job_id");
    if (!lastJobId || !baseUrl) return;
    (async () => {
      try {
        const job = await getJob(lastJobId);
        // Only restore if job is still processing (not completed)
        if (job.status === "processing" || job.status === "uploading") {
          dispatch({ type: A.PIPELINE_START, payload: lastJobId });
          // Re-attach SSE stream to monitor progress
          // (cleanup handled in handleUpload hook)
        }
        // Don't auto-restore completed jobs — user should see home page on refresh
      } catch {
        /* silently ignore — stale job ID */
      }
    })();
    // only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Upload handler ────────────────────────────────────────────────────────

  const handleUpload = useCallback(
    async (file) => {
      if (!baseUrl) {
        // Auto-open settings instead of a blocking alert
        dispatch({ type: A.TOGGLE_SETTINGS, payload: true });
        return;
      }
      dispatch({ type: A.UPLOAD_START });

      // Ensure proxy target is set before upload
      await notifyProxy(baseUrl);

      let jobIdLocal;
      try {
        const res = await uploadVideo(file, {
          runCommentary,
          onProgress: (p) =>
            dispatch({ type: A.UPLOAD_PROGRESS, payload: Math.round(p * 100) }),
        });
        jobIdLocal = res.job_id;
      } catch (err) {
        dispatch({ type: A.ERROR, payload: err.message });
        return;
      }

      dispatch({ type: A.PIPELINE_START, payload: jobIdLocal });

      // SSE
      let sseCleanup;
      let pollId;

      const onSSEUpdate = (data) => {
        dispatch({ type: A.PIPELINE_UPDATE, payload: data });
        if (data.status === "done") {
          const r = data.events
            ? {
                events: Array.isArray(data.events) ? data.events : [],
                duration_sec: data.duration_sec ?? 0,
                wicket_count: data.wicket_count ?? 0,
                nm_count: data.nm_count ?? 0,
              }
            : null;
          if (r) {
            dispatch({ type: A.DONE, payload: r });
          } else {
            // fetch separately
            getEvents(jobIdLocal)
              .then((evData) => {
                // Ensure arrays
                evData.events = Array.isArray(evData.events)
                  ? evData.events
                  : [];
                evData.duration_sec = evData.duration_sec ?? 0;
                evData.wicket_count = evData.wicket_count ?? 0;
                evData.nm_count = evData.nm_count ?? 0;
                dispatch({ type: A.DONE, payload: evData });
              })
              .catch((err) =>
                dispatch({ type: A.ERROR, payload: err.message }),
              );
          }
        } else if (data.status === "error") {
          dispatch({
            type: A.ERROR,
            payload: data.error || data.message || "Processing failed",
          });
        }
      };

      const onSSEError = () => {
        // Fallback: poll with exponential backoff
        if (pollId) return;
        let pollAttempt = 0;
        const maxAttempts = 60; // max 5 mins of polling with backoff
        let consecutiveErrors = 0;

        pollId = setInterval(async () => {
          pollAttempt++;
          try {
            const job = await getJob(jobIdLocal);
            consecutiveErrors = 0; // reset on success
            dispatch({
              type: A.PIPELINE_UPDATE,
              payload: {
                progress: job.progress ?? 0,
                message: job.message ?? "",
              },
            });
            if (job.status === "done") {
              clearInterval(pollId);
              const evData = await getEvents(jobIdLocal);
              // Ensure arrays and defaults
              evData.events = Array.isArray(evData.events) ? evData.events : [];
              evData.duration_sec = evData.duration_sec ?? 0;
              evData.wicket_count = evData.wicket_count ?? 0;
              evData.nm_count = evData.nm_count ?? 0;
              dispatch({ type: A.DONE, payload: evData });
            } else if (job.status === "error") {
              clearInterval(pollId);
              dispatch({
                type: A.ERROR,
                payload: job.error || "Processing failed",
              });
            }
          } catch (err) {
            consecutiveErrors++;
            // Stop polling after too many failures
            if (consecutiveErrors > 10 || pollAttempt > maxAttempts) {
              clearInterval(pollId);
              dispatch({
                type: A.ERROR,
                payload: `Connection lost after ${consecutiveErrors} failed attempts. Check your backend URL. Error: ${err.message}`,
              });
            }
          }
        }, 3000);
      };

      sseCleanup = streamProgress(jobIdLocal, onSSEUpdate, onSSEError);
      cleanupRef.current = () => {
        sseCleanup?.();
        if (pollId) clearInterval(pollId);
      };
      return () => {
        sseCleanup?.();
        if (pollId) clearInterval(pollId);
      };
    },
    [baseUrl, runCommentary],
  );

  // ── Stop processing handler ────────────────────────────────────────────────

  const handleStop = useCallback(async () => {
    if (!jobId) return;
    try {
      // Clean up SSE connection
      cleanupRef.current?.();
      cleanupRef.current = null;
      // Delete the job on backend (cancels processing)
      await deleteJob(jobId);
    } catch (err) {
      console.error("Error stopping job:", err);
    }
    // Reset UI
    dispatch({ type: A.RESET_UPLOAD });
  }, [jobId]);

  // ── Import local path handler ─────────────────────────────────────────────

  const handleImportLocal = useCallback(
    async (filePath) => {
      if (!baseUrl) {
        dispatch({ type: A.TOGGLE_SETTINGS, payload: true });
        return;
      }
      await notifyProxy(baseUrl);
      dispatch({ type: A.UPLOAD_START });
      dispatch({ type: A.UPLOAD_PROGRESS, payload: 100 }); // no real upload

      let jobIdLocal;
      try {
        const res = await importLocalFile(filePath, { runCommentary });
        jobIdLocal = res.job_id;
      } catch (err) {
        dispatch({ type: A.ERROR, payload: err.message });
        return;
      }

      dispatch({ type: A.PIPELINE_START, payload: jobIdLocal });

      let sseCleanup;
      let pollId;

      const onSSEUpdate = (data) => {
        dispatch({ type: A.PIPELINE_UPDATE, payload: data });
        if (data.status === "done") {
          const r = data.events
            ? {
                events: Array.isArray(data.events) ? data.events : [],
                duration_sec: data.duration_sec ?? 0,
                wicket_count: data.wicket_count ?? 0,
                nm_count: data.nm_count ?? 0,
              }
            : null;
          if (r) {
            dispatch({ type: A.DONE, payload: r });
          } else {
            getEvents(jobIdLocal)
              .then((evData) => {
                evData.events = Array.isArray(evData.events)
                  ? evData.events
                  : [];
                evData.duration_sec = evData.duration_sec ?? 0;
                evData.wicket_count = evData.wicket_count ?? 0;
                evData.nm_count = evData.nm_count ?? 0;
                dispatch({ type: A.DONE, payload: evData });
              })
              .catch((err) =>
                dispatch({ type: A.ERROR, payload: err.message }),
              );
          }
        } else if (data.status === "error") {
          dispatch({
            type: A.ERROR,
            payload: data.error || data.message || "Processing failed",
          });
        }
      };

      const onSSEError = () => {
        if (pollId) return;
        let pollAttempt = 0;
        let consecutiveErrors = 0;
        pollId = setInterval(async () => {
          pollAttempt++;
          try {
            const job = await getJob(jobIdLocal);
            consecutiveErrors = 0;
            dispatch({
              type: A.PIPELINE_UPDATE,
              payload: {
                progress: job.progress ?? 0,
                message: job.message ?? "",
              },
            });
            if (job.status === "done") {
              clearInterval(pollId);
              const evData = await getEvents(jobIdLocal);
              evData.events = Array.isArray(evData.events) ? evData.events : [];
              evData.duration_sec = evData.duration_sec ?? 0;
              evData.wicket_count = evData.wicket_count ?? 0;
              evData.nm_count = evData.nm_count ?? 0;
              dispatch({ type: A.DONE, payload: evData });
            } else if (job.status === "error") {
              clearInterval(pollId);
              dispatch({
                type: A.ERROR,
                payload: job.error || "Processing failed",
              });
            }
          } catch (err) {
            consecutiveErrors++;
            if (consecutiveErrors > 10 || pollAttempt > 60) {
              clearInterval(pollId);
              dispatch({
                type: A.ERROR,
                payload: `Connection lost: ${err.message}`,
              });
            }
          }
        }, 3000);
      };

      sseCleanup = streamProgress(jobIdLocal, onSSEUpdate, onSSEError);
      cleanupRef.current = () => {
        sseCleanup?.();
        if (pollId) clearInterval(pollId);
      };
      return () => {
        sseCleanup?.();
        if (pollId) clearInterval(pollId);
      };
    },
    [baseUrl, runCommentary],
  );

  // ── Event seek handler ────────────────────────────────────────────────────

  const handleSelectEvent = useCallback((eventId, tsSec) => {
    dispatch({ type: A.SET_ACTIVE_EVENT, payload: eventId });
    const v = videoRef.current;
    if (v) {
      v.currentTime = Math.max(0, tsSec - 10);
      v.play().catch(() => {});
    }
  }, []);

  // ── Settings handlers ─────────────────────────────────────────────────────

  const handleSaveUrl = (url) =>
    dispatch({ type: A.SET_BASE_URL, payload: url });
  const handleToggleCommentary = () =>
    dispatch({ type: A.SET_RUN_COMMENTARY, payload: !runCommentary });
  const handleLoadResults = (jid, evData) => {
    dispatch({ type: A.SET_RESULTS, payload: { jobId: jid, results: evData } });
  };

  // ── isDone shorthand ──────────────────────────────────────────────────────

  const isDone = phase === "done";
  const isIdle = phase === "idle";
  const isProgress =
    phase === "uploading" || phase === "processing" || phase === "error";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
        background: "#0a0d12",
      }}
    >
      {/* TopBar */}
      <TopBar
        baseUrl={baseUrl}
        connectionStatus={connectionStatus}
        phase={phase}
        onToggleSettings={() => dispatch({ type: A.TOGGLE_SETTINGS })}
        onReset={() => dispatch({ type: A.RESET_UPLOAD })}
        onStop={handleStop}
      />

      {/* Settings panel */}
      <SettingsPanel
        open={settingsOpen}
        baseUrl={baseUrl}
        runCommentary={runCommentary}
        onClose={() => dispatch({ type: A.TOGGLE_SETTINGS, payload: false })}
        onSaveUrl={handleSaveUrl}
        onToggleCommentary={handleToggleCommentary}
        onLoadResults={handleLoadResults}
      />

      {/* Main content area */}
      <div
        style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}
      >
        {/* Centre area */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            minWidth: 0,
          }}
        >
          {/* Upload / progress / video */}
          <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
            {isIdle && (
              <div style={{ height: "100%", overflowY: "auto" }}>
                <UploadZone
                  backendBusy={backendBusy}
                  baseUrl={baseUrl}
                  connectionStatus={connectionStatus}
                  onUpload={handleUpload}
                  onImportLocal={handleImportLocal}
                  onOpenSettings={() =>
                    dispatch({ type: A.TOGGLE_SETTINGS, payload: true })
                  }
                />
              </div>
            )}

            {isProgress && (
              <ProgressView
                phase={phase}
                uploadProgress={uploadProgress}
                pipelineProgress={pipelineProgress}
                pipelineMessage={pipelineMessage}
                pipelineError={pipelineError}
                filename={uploadFile?.name}
                onReset={() => dispatch({ type: A.RESET_UPLOAD })}
              />
            )}

            {isDone && (
              <VideoPlayer
                baseUrl={baseUrl}
                jobId={jobId}
                events={results?.events || []}
                activeEventId={activeEventId}
                onSeekToEvent={handleSelectEvent}
                timeRef={timeRef}
                videoRef={videoRef}
              />
            )}
          </div>

          {/* Match Timeline — only when done */}
          {isDone && (
            <MatchTimeline
              events={results?.events || []}
              duration={results?.duration_sec}
              timeRef={timeRef}
              activeEventId={activeEventId}
              onSelectEvent={handleSelectEvent}
              videoRef={videoRef}
            />
          )}
        </div>

        {/* Event Panel — only when done */}
        {isDone && (
          <EventPanel
            results={results}
            activeTab={activeTab}
            onTabChange={(t) =>
              dispatch({ type: A.SET_ACTIVE_TAB, payload: t })
            }
            activeEventId={activeEventId}
            onSelectEvent={handleSelectEvent}
          />
        )}
      </div>
    </div>
  );
}
