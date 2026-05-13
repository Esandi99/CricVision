import React, { useMemo, useState } from "react";
import VideoPlayer from "./VideoPlayer.jsx";
import EventDetailCard from "./EventDetailCard.jsx";
import FilterTabs from "./FilterTabs.jsx";
import EventCard from "./EventCard.jsx";

export default function ReviewScreen({ videoUrl, events }) {
  const [activeId, setActiveId] = useState(null);
  const [filter, setFilter] = useState("all");
  const [seekRequest, setSeekRequest] = useState(null);

  const sortedEvents = useMemo(
    () => [...events].sort((a, b) => a.delivery_ts_sec - b.delivery_ts_sec),
    [events]
  );

  const visibleEvents = useMemo(() => {
    if (filter === "all") return sortedEvents;
    if (filter === "wickets") return sortedEvents.filter((e) => e.type === "wicket");
    return sortedEvents.filter((e) => e.type === "near_miss");
  }, [sortedEvents, filter]);

  const counts = useMemo(
    () => ({
      all: sortedEvents.length,
      wickets: sortedEvents.filter((e) => e.type === "wicket").length,
      near_miss: sortedEvents.filter((e) => e.type === "near_miss").length,
    }),
    [sortedEvents]
  );

  const activeEvent = useMemo(
    () => sortedEvents.find((e) => e.event_id === activeId) || null,
    [sortedEvents, activeId]
  );
  const activeIdx = activeEvent ? visibleEvents.findIndex((e) => e.event_id === activeEvent.event_id) : -1;

  const goto = (delta) => {
    const next = visibleEvents[activeIdx + delta];
    if (next) {
      setActiveId(next.event_id);
      setSeekRequest({ ts: next.delivery_ts_sec, nonce: Date.now() });
    }
  };

  const handleCardClick = (ev) => {
    setActiveId(ev.event_id);
    setSeekRequest({ ts: ev.delivery_ts_sec, nonce: Date.now() });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <main style={{ maxWidth: 1440, margin: "0 auto", padding: "20px 28px 60px" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 360px",
          gap: 20,
          marginBottom: 28,
        }}
      >
        <VideoPlayer
          videoUrl={videoUrl}
          events={sortedEvents}
          filter={filter}
          activeId={activeId}
          setActiveId={setActiveId}
          seekRequest={seekRequest}
        />
        <EventDetailCard
          event={activeEvent}
          onClose={() => setActiveId(null)}
          onPrev={() => goto(-1)}
          onNext={() => goto(1)}
          hasPrev={activeIdx > 0}
          hasNext={activeIdx >= 0 && activeIdx < visibleEvents.length - 1}
        />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, letterSpacing: "-0.01em" }}>All events</h2>
          <div style={{ fontSize: 13, color: "var(--text-3)", marginTop: 2 }}>
            Click any card to jump the player to that moment.
          </div>
        </div>
        <FilterTabs value={filter} onChange={setFilter} counts={counts} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 12,
        }}
      >
        {visibleEvents.map((ev) => (
          <EventCard
            key={ev.event_id}
            event={ev}
            active={ev.event_id === activeId}
            onClick={() => handleCardClick(ev)}
          />
        ))}
        {visibleEvents.length === 0 && (
          <div
            style={{
              gridColumn: "1 / -1",
              padding: 40,
              textAlign: "center",
              color: "var(--text-3)",
              border: "1px dashed var(--line)",
              borderRadius: 12,
            }}
          >
            No events match this filter.
          </div>
        )}
      </div>
    </main>
  );
}
