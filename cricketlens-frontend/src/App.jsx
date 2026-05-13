import React, { useEffect, useState } from "react";
import Header from "./components/Header.jsx";
import UploadScreen from "./components/UploadScreen.jsx";
import ProcessingScreen from "./components/ProcessingScreen.jsx";
import ReviewScreen from "./components/ReviewScreen.jsx";
import { uploadVideo, streamProgress, getEvents } from "./api.js";

/**
 * Top-level state machine:
 *   "upload"     → drop / browse a video
 *   "processing" → upload + SSE progress stream
 *   "review"     → video player + timeline + events
 *   "error"      → something went wrong
 */
export default function App() {
  const [stage, setStage] = useState("upload");
  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);  // local object-URL for playback
  const [jobId, setJobId] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState("Queued");
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);

  // Cleanup the object URL when we leave review
  useEffect(() => {
    return () => { if (videoUrl) URL.revokeObjectURL(videoUrl); };
  }, [videoUrl]);

  const handleUpload = async (f) => {
    try {
      setFile(f);
      setVideoUrl(URL.createObjectURL(f));   // we play the local file directly
      setStage("processing");
      setUploadProgress(0);
      setProgress(0);
      setMessage("Uploading…");

      const { job_id } = await uploadVideo(f, {
        runCommentary: true,
        onProgress: (p) => setUploadProgress(p),
      });
      setJobId(job_id);
      setUploadProgress(1);

      // Subscribe to SSE for live updates.
      streamProgress(
        job_id,
        async (data) => {
          setProgress(data.progress ?? 0);
          setMessage(data.message ?? "");
          if (data.status === "done") {
            // Fetch full events payload (SSE may include it inline, but be safe).
            try {
              const evs = data.events?.length ? { events: data.events } : await getEvents(job_id);
              setEvents(evs.events || []);
              setStage("review");
            } catch (err) {
              setError(err.message);
              setStage("error");
            }
          } else if (data.status === "error") {
            setError(data.message || "Processing failed");
            setStage("error");
          }
        },
        (err) => {
          setError("Lost connection to server: " + (err?.message || err));
          setStage("error");
        }
      );
    } catch (err) {
      setError(err.message);
      setStage("error");
    }
  };

  const reset = () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    setStage("upload");
    setFile(null);
    setVideoUrl(null);
    setJobId(null);
    setUploadProgress(0);
    setProgress(0);
    setMessage("");
    setEvents([]);
    setError(null);
  };

  return (
    <>
      <Header
        filename={file?.name}
        status={stage === "review" ? "done" : stage === "error" ? "error" : stage === "processing" ? "processing" : "idle"}
        onNew={stage !== "upload" ? reset : null}
      />
      {stage === "upload" && <UploadScreen onUpload={handleUpload} />}
      {stage === "processing" && (
        <ProcessingScreen
          filename={file?.name}
          progress={progress}
          message={message}
          uploadProgress={uploadProgress}
        />
      )}
      {stage === "review" && <ReviewScreen videoUrl={videoUrl} events={events} />}
      {stage === "error" && (
        <div style={{ maxWidth: 600, margin: "120px auto", textAlign: "center", padding: 24 }}>
          <h2 style={{ color: "var(--bad)" }}>Something went wrong</h2>
          <p style={{ color: "var(--text-2)" }}>{error}</p>
          <button
            onClick={reset}
            style={{
              marginTop: 16,
              padding: "10px 18px",
              borderRadius: 8,
              background: "var(--wicket)",
              color: "#0b0e14",
              border: "none",
              fontWeight: 600,
            }}
          >
            Start over
          </button>
        </div>
      )}
    </>
  );
}
