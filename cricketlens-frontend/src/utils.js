// ─── Time helpers ─────────────────────────────────────────────────────────────

export function formatTime(sec) {
  if (sec == null || isNaN(sec)) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function timeAgo(unixTs) {
  if (!unixTs) return "";
  const diff = Math.floor(Date.now() / 1000 - unixTs);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

// ─── File size ────────────────────────────────────────────────────────────────

export function formatFileSize(bytes) {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${(bytes / 1073741824).toFixed(2)} GB`;
}

// ─── Near-miss type formatting ────────────────────────────────────────────────

export function formatNmType(str) {
  if (!str) return "Unclear";
  return str
    .replace(/^near_miss_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function nmTypeIcon(str) {
  if (!str) return "⚡";
  if (str.includes("caught")) return "🤲";
  if (str.includes("lbw")) return "🦵";
  if (str.includes("runout") || str.includes("run_out")) return "🏃";
  if (str.includes("edge")) return "🏏";
  if (str.includes("stumping")) return "🧤";
  return "⚡";
}

// ─── Dismissal mode badge ─────────────────────────────────────────────────────

export function dismissalModeClass(mode) {
  switch ((mode || "").toLowerCase()) {
    case "bowled":     return "mode-bowled";
    case "caught":     return "mode-caught";
    case "lbw":        return "mode-lbw";
    case "run out":    return "mode-runout";
    case "stumped":    return "mode-stumped";
    case "hit wicket": return "mode-hitwicket";
    default:           return "mode-default";
  }
}

export function dismissalModeStyle(mode) {
  switch ((mode || "").toLowerCase()) {
    case "bowled":     return { background: "rgba(249,115,22,0.18)", color: "#fb923c" };
    case "caught":     return { background: "rgba(14,165,233,0.18)", color: "#38bdf8" };
    case "lbw":        return { background: "rgba(168,85,247,0.18)", color: "#c084fc" };
    case "run out":    return { background: "rgba(245,158,11,0.18)", color: "#fbbf24" };
    case "stumped":    return { background: "rgba(20,184,166,0.18)", color: "#2dd4bf" };
    case "hit wicket": return { background: "rgba(244,63,94,0.18)", color: "#fb7185" };
    default:           return { background: "rgba(100,116,139,0.18)", color: "#94a3b8" };
  }
}

export function titleCase(s) {
  return s ? String(s).replace(/\b\w/g, (c) => c.toUpperCase()) : "";
}

// Legacy compat alias
export const fmtTime = formatTime;
