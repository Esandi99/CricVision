import React, { useEffect, useRef, useState } from "react";
import { formatTime } from "../utils.js";

/**
 * MatchTimeline — full-width horizontal div-based timeline.
 * Layers: scanline, innings boundary, event segments, markers, playhead, time axis.
 * Uses ResizeObserver + requestAnimationFrame for smooth playhead (no state updates).
 */
export default function MatchTimeline({
  events = [],
  duration,
  timeRef,
  activeEventId,
  onSelectEvent,         // (eventId, tsSec) => void
  videoRef,             // to call currentTime setter + play
}) {
  const containerRef = useRef(null);
  const playheadRef  = useRef(null);
  const rafRef       = useRef(null);
  const [width, setWidth] = useState(0);
  const [tooltip, setTooltip] = useState(null); // { x, ev }

  // ResizeObserver
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    setWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, []);

  // rAF playhead
  useEffect(() => {
    const tick = () => {
      if (playheadRef.current && duration > 0 && width > 0) {
        const t   = timeRef?.current ?? 0;
        const pct = Math.min(1, t / duration);
        playheadRef.current.style.left = `${pct * width}px`;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [duration, width, timeRef]);

  if (!duration || duration <= 0) return null;

  const pxPerSec = width / duration;

  // Innings 2 boundary
  const inn2Events = events.filter(e => e.innings === 2);
  const inn2Start  = inn2Events.length > 0 ? Math.min(...inn2Events.map(e => e.ts_sec ?? 0)) : null;

  // Time axis ticks — every 10 min, labels every 30 min
  const axisTicks = [];
  for (let t = 600; t < duration; t += 600) {
    axisTicks.push({ t, label: t % 1800 === 0 ? formatTime(t) : null });
  }

  const handleClick = (e) => {
    if (!duration || !width) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x    = e.clientX - rect.left;
    const t    = (x / width) * duration;
    // Try to find a nearby event (within 10px)
    let hit = null;
    for (const ev of events) {
      const evX = (ev.ts_sec ?? 0) * pxPerSec;
      if (Math.abs(evX - x) < 10) { hit = ev; break; }
    }
    if (hit) {
      onSelectEvent(hit.event_id, hit.ts_sec ?? 0);
    } else {
      // Seek video directly
      const v = videoRef?.current;
      if (v) { v.currentTime = Math.max(0, t); v.play().catch(() => {}); }
    }
  };

  const markerHeight = 38; // px for marker area above axis

  return (
    <div
      style={{
        height: 80,
        background: "#0a0d12",
        borderTop: "1px solid #1e2535",
        position: "relative",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      <div
        ref={containerRef}
        onClick={handleClick}
        onMouseMove={(e) => {
          const rect = containerRef.current.getBoundingClientRect();
          const x    = e.clientX - rect.left;
          // find closest event within 12px
          let best = null, bestD = 12;
          for (const ev of events) {
            const d = Math.abs((ev.ts_sec ?? 0) * pxPerSec - x);
            if (d < bestD) { bestD = d; best = ev; }
          }
          setTooltip(best ? { x, ev: best } : null);
        }}
        onMouseLeave={() => setTooltip(null)}
        style={{
          position: "absolute",
          inset: 0,
          cursor: "crosshair",
          // Layer 1: scanline
          backgroundImage: "repeating-linear-gradient(to bottom, transparent, transparent 2px, rgba(255,255,255,0.015) 2px, rgba(255,255,255,0.015) 4px)",
        }}
      >
        {/* Layer 2 — innings 2 boundary */}
        {inn2Start != null && width > 0 && (
          <>
            <div style={{
              position: "absolute",
              left: inn2Start * pxPerSec,
              top: 0,
              bottom: 20,
              width: 1,
              background: "rgba(255,255,255,0.25)",
              borderLeft: "1px dashed rgba(255,255,255,0.25)",
            }} />
            <div style={{
              position: "absolute",
              left: inn2Start * pxPerSec + 4,
              top: 4,
              fontSize: 9,
              color: "rgba(255,255,255,0.4)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              fontFamily: "'JetBrains Mono', monospace",
              pointerEvents: "none",
            }}>
              2nd innings
            </div>
          </>
        )}

        {/* Layer 3 — event segments */}
        {events.map(ev => {
          const ts  = ev.ts_sec ?? 0;
          const end = ev.ts_end_sec ?? ts + 8;
          const w   = Math.max(2, (end - ts) * pxPerSec);
          return (
            <div
              key={`seg-${ev.event_id}`}
              style={{
                position: "absolute",
                left: ts * pxPerSec,
                top: 0,
                bottom: 20,
                width: w,
                background: ev.type === "wicket"
                  ? "rgba(239,68,68,0.12)"
                  : "rgba(245,158,11,0.08)",
                pointerEvents: "none",
              }}
            />
          );
        })}

        {/* Layer 4 — event markers */}
        {events.map(ev => {
          const ts       = ev.ts_sec ?? 0;
          const left     = ts * pxPerSec;
          const isActive = ev.event_id === activeEventId;
          const isWicket = ev.type === "wicket";
          const color    = isWicket ? "#ef4444" : "#f59e0b";
          return (
            <div
              key={`marker-${ev.event_id}`}
              className="timeline-marker"
              style={{
                position: "absolute",
                left: left - (isActive ? 2 : 1),
                bottom: 20,
                width: isActive ? 4 : 2,
                top: 0,
                background: color,
                opacity: isActive ? 1 : 0.75,
                boxShadow: isActive ? `0 0 8px ${color}` : "none",
              }}
            >
              {/* Triangle top for wickets */}
              {isWicket && (
                <div style={{
                  position: "absolute",
                  top: -5,
                  left: "50%",
                  transform: "translateX(-50%)",
                  width: 0, height: 0,
                  borderLeft: "4px solid transparent",
                  borderRight: "4px solid transparent",
                  borderBottom: `5px solid ${color}`,
                }} />
              )}
              {/* Diamond for near-misses */}
              {!isWicket && (
                <div style={{
                  position: "absolute",
                  top: -5,
                  left: "50%",
                  transform: "translateX(-50%) rotate(45deg)",
                  width: 7, height: 7,
                  background: color,
                }} />
              )}
            </div>
          );
        })}

        {/* Layer 5 — playhead (div updated by rAF, not state) */}
        <div
          ref={playheadRef}
          style={{
            position: "absolute",
            top: 0,
            bottom: 20,
            width: 1,
            background: "rgba(255,255,255,0.6)",
            pointerEvents: "none",
            zIndex: 5,
          }}
        />

        {/* Layer 6 — time axis */}
        <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 20, borderTop: "1px solid #1e2535" }}>
          {axisTicks.map(({ t, label }) => (
            <div
              key={t}
              style={{
                position: "absolute",
                left: t * pxPerSec,
                top: 0,
                bottom: 0,
                display: "flex",
                alignItems: "center",
              }}
            >
              <div style={{ width: 1, height: label ? 8 : 4, background: "#1e2535" }} />
              {label && (
                <div
                  className="font-mono"
                  style={{ fontSize: 9, color: "#4a5568", paddingLeft: 3, whiteSpace: "nowrap" }}
                >
                  {label}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Hover tooltip */}
      {tooltip && (
        <div style={{
          position: "absolute",
          left: Math.min(tooltip.x, width - 200),
          bottom: 26,
          background: "#111620",
          border: "1px solid #1e2535",
          borderRadius: 7,
          padding: "7px 11px",
          fontSize: 11,
          pointerEvents: "none",
          zIndex: 20,
          whiteSpace: "nowrap",
          boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
        }}>
          <span style={{ color: tooltip.ev.type === "wicket" ? "#ef4444" : "#f59e0b", fontWeight: 700, marginRight: 6 }}>
            {tooltip.ev.event_id}
          </span>
          {tooltip.ev.type === "wicket"
            ? `${tooltip.ev.batsman || ""} / ${tooltip.ev.dismissal_mode || ""}  ov ${tooltip.ev.over || ""}  ${tooltip.ev.score || ""}`
            : `${tooltip.ev.label || tooltip.ev.event_id} / ${(tooltip.ev.nm_type || "").replace(/^near_miss_/, "").replace(/_/g, " ")}`
          }
        </div>
      )}
    </div>
  );
}
