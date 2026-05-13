import React from "react";

export default function FilterTabs({ value, onChange, counts }) {
  const tabs = [
    { id: "all", label: "All events", count: counts.all },
    { id: "wickets", label: "Wickets", count: counts.wickets, color: "var(--wicket)" },
    { id: "near_miss", label: "Near misses", count: counts.near_miss, color: "var(--nearmiss)" },
  ];
  return (
    <div
      style={{
        display: "inline-flex",
        padding: 4,
        gap: 4,
        background: "var(--bg-1)",
        border: "1px solid var(--line)",
        borderRadius: 999,
      }}
    >
      {tabs.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            style={{
              padding: "8px 16px",
              borderRadius: 999,
              background: active ? "var(--bg-3)" : "transparent",
              border: "1px solid",
              borderColor: active ? "var(--line-strong)" : "transparent",
              color: active ? "var(--text-0)" : "var(--text-2)",
              fontSize: 13,
              fontWeight: 500,
              display: "flex",
              gap: 8,
              alignItems: "center",
              transition: "all 140ms",
            }}
          >
            {t.color && <span style={{ width: 8, height: 8, borderRadius: 999, background: t.color }} />}
            {t.label}
            <span className="mono" style={{ fontSize: 11, color: active ? "var(--text-2)" : "var(--text-3)" }}>
              {t.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
