import React, { useEffect, useMemo, useRef, useState } from "react";
import { fmtTime, titleCase, btnStyle } from "../utils";

/**
 * Real <video> element + a custom timeline track with clickable markers.
 * Markers are positioned by `delivery_ts_sec / videoDuration`.
 */
export default function VideoPlayer({
  videoUrl,
  events,
  filter,
  activeId,
  setActiveId,
  seekRequest,         // { ts, nonce } — bumps when parent wants to jump
}) {
  const videoRef = useRef(null);
  const trackRef = useRef(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [hoverEvent, setHoverEvent] = useState(null);
  const [hoverX, setHoverX] = useState(null);

  // Wire <video> events
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onMeta = () => setDuration(v.duration || 0);
    const onTime = () => setCurrentTime(v.currentTime || 0);
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
  }, [videoUrl]);

  // External seek requests
  useEffect(() => {
    if (!seekRequest || !videoRef.current) return;
    videoRef.current.currentTime = Math.max(0, seekRequest.ts - 1.5); // start just before
    videoRef.current.play().catch(() => {});
  }, [seekRequest]);

  const visibleEvents = useMemo(
    () =>
      events.filter((e) =>
        filter === "all" ? true : filter === "wickets" ? e.type === "wicket" : e.type === "near_miss"
      ),
    [events, filter]
  );

  const seekToPct = (clientX) => {
    if (!duration) return;
    const r = trackRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    if (videoRef.current) videoRef.current.currentTime = pct * duration;
  };

  const onMove = (e) => {
    if (!duration) return;
    const r = trackRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    setHoverX(pct);
    let nearest = null;
    let bestDist = Infinity;
    visibleEvents.forEach((ev) => {
      const evPct = ev.delivery_ts_sec / duration;
      const d = Math.abs(evPct - pct);
      if (d < bestDist && d < 0.012) {
        bestDist = d;
        nearest = ev;
      }
    });
    setHoverEvent(nearest);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  };

  const jumpToNext = () => {
    const next = visibleEvents.find((e) => e.delivery_ts_sec > currentTime + 1);
    if (next && videoRef.current) {
      videoRef.current.currentTime = next.delivery_ts_sec - 1.5;
      videoRef.current.play().catch(() => {});
      setActiveId(next.event_id);
    }
  };

  return (
    <div
      style={{
        background: "#000",
        borderRadius: 14,
        overflow: "hidden",
        border: "1px solid var(--line)",
        boxShadow: "var(--shadow-1)",
      }}
    >
      <div style={{ aspectRatio: "16/9", background: "#000" }}>
        <video
          ref={videoRef}
          src={videoUrl}
          style={{ width: "100%", height: "100%", display: "block", objectFit: "contain", background: "#000" }}
          onClick={togglePlay}
        />
      </div>

      <div style={{ padding: "12px 16px 16px", background: "var(--bg-1)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12 }}>
          <button
            onClick={togglePlay}
            aria-label={playing ? "Pause" : "Play"}
            style={{
              width: 36,
              height: 36,
              borderRadius: 999,
              background: "var(--wicket)",
              border: "none",
              display: "grid",
              placeItems: "center",
              color: "#0b0e14",
            }}
          >
            {playing ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="5" width="4" height="14" rx="1" />
                <rect x="14" y="5" width="4" height="14" rx="1" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>
          <div className="mono" style={{ fontSize: 13, color: "var(--text-1)" }}>
            {fmtTime(currentTime)} <span style={{ color: "var(--text-3)" }}>/ {fmtTime(duration)}</span>
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={jumpToNext} style={btnStyle("subtle")}>
            Jump to next event ↦
          </button>
        </div>

        <div
          ref={trackRef}
          onMouseMove={onMove}
          onMouseLeave={() => {
            setHoverEvent(null);
            setHoverX(null);
          }}
          onClick={(e) => seekToPct(e.clientX)}
          style={{ position: "relative", height: 48, paddingTop: 18, cursor: "pointer", userSelect: "none" }}
        >
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 22,
              height: 6,
              background: "var(--bg-3)",
              borderRadius: 999,
            }}
          />
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 22,
              height: 6,
              width: duration ? `${(currentTime / duration) * 100}%` : 0,
              background: "linear-gradient(90deg, #f59e0b 0%, #ea580c 100%)",
              borderRadius: 999,
              transition: "width 200ms linear",
            }}
          />

          {duration > 0 &&
            visibleEvents.map((ev) => {
              const left = (ev.delivery_ts_sec / duration) * 100;
              const isActive = ev.event_id === activeId;
              const color = ev.type === "wicket" ? "var(--wicket)" : "var(--nearmiss)";
              return (
                <button
                  key={ev.event_id}
                  onClick={(e) => {
                    e.stopPropagation();
                    setActiveId(ev.event_id);
                    if (videoRef.current) {
                      videoRef.current.currentTime = Math.max(0, ev.delivery_ts_sec - 1.5);
                      videoRef.current.play().catch(() => {});
                    }
                  }}
                  aria-label={`${ev.type} at ${fmtTime(ev.delivery_ts_sec)}`}
                  style={{
                    position: "absolute",
                    top: 17,
                    left: `${left}%`,
                    transform: `translate(-50%, 0) ${isActive ? "scale(1.35)" : "scale(1)"}`,
                    width: 16,
                    height: 16,
                    borderRadius: 999,
                    background: color,
                    border: `2px solid ${isActive ? "#fff" : "rgba(11,14,20,0.9)"}`,
                    boxShadow: isActive
                      ? `0 0 0 4px ${ev.type === "wicket" ? "var(--wicket-soft)" : "var(--nearmiss-soft)"}`
                      : `0 2px 6px rgba(0,0,0,0.4)`,
                    padding: 0,
                    cursor: "pointer",
                    transition: "transform 160ms ease, box-shadow 160ms",
                    zIndex: isActive ? 3 : 2,
                  }}
                />
              );
            })}

          {duration > 0 && (
            <div
              style={{
                position: "absolute",
                left: `${(currentTime / duration) * 100}%`,
                top: 14,
                transform: "translateX(-50%)",
                width: 2,
                height: 22,
                background: "#fff",
                borderRadius: 2,
                boxShadow: "0 0 0 1px rgba(0,0,0,0.5)",
                pointerEvents: "none",
                zIndex: 4,
              }}
            />
          )}

          {hoverX != null && hoverEvent && (
            <div
              style={{
                position: "absolute",
                left: `${hoverX * 100}%`,
                bottom: 30,
                transform: "translateX(-50%)",
                background: "var(--bg-3)",
                border: "1px solid var(--line-strong)",
                padding: "8px 12px",
                borderRadius: 8,
                whiteSpace: "nowrap",
                fontSize: 12,
                pointerEvents: "none",
                zIndex: 5,
                boxShadow: "var(--shadow-1)",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 999,
                    background: hoverEvent.type === "wicket" ? "var(--wicket)" : "var(--nearmiss)",
                  }}
                />
                <span style={{ fontWeight: 600 }}>
                  {hoverEvent.type === "wicket" ? `Wicket #${hoverEvent.wicket_number}` : "Near miss"}
                </span>
                <span className="mono" style={{ color: "var(--text-3)" }}>
                  {fmtTime(hoverEvent.delivery_ts_sec)}
                </span>
              </div>
              <div style={{ color: "var(--text-2)", marginTop: 2 }}>
                {hoverEvent.batsman} · {titleCase(hoverEvent.dismissal_mode || hoverEvent.sub_type)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
