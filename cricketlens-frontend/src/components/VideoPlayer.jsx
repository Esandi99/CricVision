import React, { useEffect, useRef, useState, useCallback } from "react";
import { formatTime } from "../utils.js";

/**
 * VideoPlayer — custom-controls video backed by /api/video/{jobId}.
 *
 * videoRef: passed in from App so MatchTimeline and App can also access
 *           the <video> element directly (seek, play, etc.).
 * timeRef:  ref updated on timeupdate — read by MatchTimeline's rAF loop
 *           without triggering re-renders.
 */
export default function VideoPlayer({
  baseUrl,
  jobId,
  events = [],
  activeEventId,
  timeRef,
  videoRef, // external ref — points at the <video> DOM node
}) {
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  const [banner, setBanner] = useState(null);
  const bannerTimer = useRef(null);

  // Use a relative path so video Range requests go through the Vite proxy
  // (which injects the ngrok-skip-browser-warning header server-side).
  // An absolute ngrok URL here would cause CORS on every Range request.
  const videoSrc = jobId ? `/api/video/${jobId}` : null;

  // Wire video events
  useEffect(() => {
    const v = videoRef?.current;
    if (!v) return;
    const onMeta = () => setDuration(v.duration || 0);
    const onTime = () => {
      const t = v.currentTime || 0;
      setCurrentTime(t);
      if (timeRef) timeRef.current = t;
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("loadedmetadata", onMeta);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("loadedmetadata", onMeta);
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [videoSrc, videoRef, timeRef]);

  // Keyboard shortcut: Space = play/pause
  useEffect(() => {
    const onKey = (e) => {
      if (
        e.code === "Space" &&
        !["INPUT", "TEXTAREA"].includes(e.target.tagName)
      ) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Show event banner whenever activeEventId changes
  useEffect(() => {
    if (!activeEventId || !events.length) return;
    const ev = events.find((e) => e.event_id === activeEventId);
    if (!ev) return;
    let text;
    if (ev.type === "wicket") {
      text = `W${ev.wicket_number || ""} — ${ev.batsman || ""}  ${ev.dismissal_mode || ""}  ${ev.score || ""}  ov ${ev.over || ""}`;
    } else {
      const nmFormatted = (ev.nm_type || "")
        .replace(/^near_miss_/, "")
        .replace(/_/g, " ");
      text = `NM — ${ev.label || ev.event_id}  ${nmFormatted}`;
    }
    clearTimeout(bannerTimer.current);
    setBanner({ text, key: Date.now() });
    bannerTimer.current = setTimeout(() => setBanner(null), 3200);
    return () => clearTimeout(bannerTimer.current);
  }, [activeEventId, events]);

  const togglePlay = () => {
    const v = videoRef?.current;
    if (!v) return;
    v.paused ? v.play().catch(() => {}) : v.pause();
  };

  const handleScrubberClick = (e) => {
    if (!duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    if (videoRef?.current) videoRef.current.currentTime = pct * duration;
  };

  const handleSpeed = (s) => {
    setSpeed(s);
    if (videoRef?.current) videoRef.current.playbackRate = s;
  };

  const handleVolume = (e) => {
    const v = parseFloat(e.target.value);
    setVolume(v);
    if (videoRef?.current) videoRef.current.volume = v;
  };

  const handleFullscreen = () => {
    const v = videoRef?.current;
    if (!v) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else v.requestFullscreen?.();
  };

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  // Event tick marks on scrubber
  // Defensive: ensure events is an array before mapping
  const eventsArray = Array.isArray(events) ? events : [];
  const tickMarks =
    duration > 0 && eventsArray.length > 0
      ? eventsArray.map((ev) => ({
          left: ((ev.ts_sec ?? 0) / duration) * 100,
          isWicket: ev.type === "wicket",
          id: ev.event_id,
        }))
      : [];

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: "#000",
      }}
    >
      {/* The actual video element */}
      <video
        ref={videoRef}
        src={videoSrc || undefined}
        crossOrigin="anonymous"
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
        onClick={togglePlay}
      />

      {/* Placeholder when no URL is configured */}
      {!videoSrc && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#4a5568",
            fontSize: 14,
          }}
        >
          Set backend URL to load video
        </div>
      )}

      {/* Event banner — top-centre, pointer-events-none */}
      {banner && (
        <div
          key={banner.key}
          className="banner-anim font-mono"
          style={{
            position: "absolute",
            top: 14,
            left: "50%",
            transform: "translateX(-50%)",
            background: "rgba(0,0,0,0.78)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            padding: "8px 18px",
            fontSize: 13,
            color: "#e2e8f0",
            whiteSpace: "nowrap",
            pointerEvents: "none",
            zIndex: 10,
          }}
        >
          {banner.text}
        </div>
      )}

      {/* Controls overlay — bottom gradient */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          background:
            "linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.5) 60%, transparent 100%)",
          padding: "16px 14px 10px",
        }}
      >
        {/* Scrubber track */}
        <div
          id="video-scrubber"
          onClick={handleScrubberClick}
          style={{
            position: "relative",
            height: 22,
            cursor: "pointer",
            marginBottom: 8,
          }}
        >
          {/* Track background */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: 0,
              right: 0,
              height: 4,
              background: "rgba(255,255,255,0.15)",
              borderRadius: 2,
              transform: "translateY(-50%)",
            }}
          />

          {/* Watched fill */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: 0,
              height: 4,
              width: `${progressPct}%`,
              background: "rgba(34,197,94,0.5)",
              borderRadius: 2,
              transform: "translateY(-50%)",
              transition: "width 200ms linear",
            }}
          />

          {/* Event tick marks */}
          {tickMarks.map((t) => (
            <div
              key={t.id}
              style={{
                position: "absolute",
                top: "50%",
                left: `${t.left}%`,
                transform: "translate(-50%, -50%)",
                width: 2,
                height: 11,
                background: t.isWicket ? "#ef4444" : "#f59e0b",
                borderRadius: 1,
                pointerEvents: "none",
                opacity: 0.85,
              }}
            />
          ))}

          {/* Playhead thumb */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: `${progressPct}%`,
              transform: "translate(-50%, -50%)",
              width: 13,
              height: 13,
              borderRadius: "50%",
              background: "#fff",
              pointerEvents: "none",
              boxShadow: "0 0 0 2px rgba(0,0,0,0.4)",
            }}
          />
        </div>

        {/* Controls row */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Play / Pause */}
          <button
            id="video-play-btn"
            onClick={togglePlay}
            aria-label={playing ? "Pause" : "Play"}
            style={{
              background: "transparent",
              border: "none",
              color: "#fff",
              cursor: "pointer",
              padding: 0,
              display: "grid",
              placeItems: "center",
            }}
          >
            {playing ? (
              <svg width="19" height="19" viewBox="0 0 24 24" fill="white">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg width="19" height="19" viewBox="0 0 24 24" fill="white">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>

          {/* Time */}
          <div
            className="font-mono"
            style={{ fontSize: 12, color: "#e2e8f0", whiteSpace: "nowrap" }}
          >
            {formatTime(currentTime)}
            <span style={{ color: "#4a5568" }}> / {formatTime(duration)}</span>
          </div>

          <div style={{ flex: 1 }} />

          {/* Speed buttons */}
          {[0.5, 1, 1.5, 2].map((s) => (
            <button
              key={s}
              onClick={() => handleSpeed(s)}
              style={{
                padding: "2px 7px",
                borderRadius: 4,
                background:
                  speed === s ? "rgba(255,255,255,0.2)" : "transparent",
                border: `1px solid ${speed === s ? "rgba(255,255,255,0.35)" : "transparent"}`,
                color: speed === s ? "#fff" : "#6b7280",
                fontSize: 11,
                cursor: "pointer",
                fontFamily: "'JetBrains Mono', monospace",
                transition: "all 100ms",
              }}
            >
              {s}×
            </button>
          ))}

          {/* Volume */}
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={handleVolume}
            className="volume-slider"
            aria-label="Volume"
            style={{ width: 68, height: 3, accentColor: "#22c55e" }}
          />

          {/* Fullscreen */}
          <button
            id="video-fullscreen-btn"
            onClick={handleFullscreen}
            aria-label="Fullscreen"
            style={{
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              cursor: "pointer",
              padding: 0,
              display: "grid",
              placeItems: "center",
            }}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
