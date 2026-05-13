export const fmtTime = (sec) => {
  if (sec == null || isNaN(sec)) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
};

export const titleCase = (s) =>
  s ? String(s).replace(/\b\w/g, (c) => c.toUpperCase()) : "";

export const btnStyle = (variant = "primary") => ({
  appearance: "none",
  border: "1px solid transparent",
  padding: "8px 14px",
  borderRadius: 8,
  fontSize: 13,
  fontWeight: 500,
  transition: "all 120ms ease",
  ...(variant === "primary"
    ? { background: "var(--wicket)", color: "#0b0e14", borderColor: "var(--wicket)" }
    : variant === "ghost"
    ? { background: "transparent", color: "var(--text-1)", borderColor: "var(--line)" }
    : variant === "subtle"
    ? { background: "var(--bg-2)", color: "var(--text-1)", borderColor: "var(--line)" }
    : {}),
});
