import React, { useRef, useState } from "react";
import { formatFileSize } from "../utils.js";

const ACCEPTED = ".mp4,.mkv,.avi,.mov,.ts";
const TAB = { LOCAL: "local", UPLOAD: "upload" };

/**
 * UploadZone — two modes:
 *   Local Path  — paste an absolute path → backend reads from disk instantly
 *                 (recommended for local 1.5 GB+ files, zero upload time)
 *   Upload File — drag-drop / file picker → browser uploads the video
 */
export default function UploadZone({
  backendBusy, baseUrl, connectionStatus,
  onUpload, onImportLocal, onOpenSettings,
}) {
  const [tab, setTab]             = useState(TAB.LOCAL);
  const [drag, setDrag]           = useState(false);
  const [file, setFile]           = useState(null);
  const [localPath, setLocalPath] = useState("");
  const [pathError, setPathError] = useState("");
  const inputRef                  = useRef(null);

  const pickFile = (f) => { if (!f) return; setFile(f); };

  const handleDrop = (e) => {
    e.preventDefault(); setDrag(false);
    pickFile(e.dataTransfer.files[0]);
  };

  const handleSubmitUpload = () => {
    if (!file || backendBusy) return;
    onUpload(file);
  };

  const handleSubmitLocal = () => {
    const path = localPath.trim();
    if (!path) { setPathError("Enter the full path to a video file."); return; }
    const ext = path.split(".").pop().toLowerCase();
    if (!["mp4","mkv","avi","mov","ts"].includes(ext)) {
      setPathError("Unsupported format. Use .mp4, .mkv, .avi, .mov, or .ts"); return;
    }
    setPathError("");
    onImportLocal(path);
  };

  const disabled = connectionStatus === "disconnected" || backendBusy;

  return (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"center",
                  justifyContent:"center", height:"100%", padding:"24px 32px" }}>

      {/* Headline */}
      <div style={{ textAlign:"center", marginBottom:28 }}>
        <div style={{ fontSize:11, color:"#4a5568", letterSpacing:"0.14em",
                      textTransform:"uppercase", marginBottom:10 }}>
          Step 1 of 2
        </div>
        <h1 className="font-display"
            style={{ margin:0, fontSize:42, color:"#e2e8f0", letterSpacing:"0.06em" }}>
          SELECT A MATCH
        </h1>
        <p style={{ margin:"10px 0 0", color:"#94a3b8", fontSize:14 }}>
          Detect every wicket and near-miss — get a clickable timeline.
        </p>
      </div>

      {/* Tab switcher */}
      <div style={{ display:"flex", gap:4, padding:4, background:"#111620",
                    borderRadius:12, border:"1px solid #1e2535", marginBottom:24,
                    width:"100%", maxWidth:540 }}>
        {[
          { id:TAB.LOCAL,  icon:"\u26a1", label:"Local Path",  sub:"Instant — no upload" },
          { id:TAB.UPLOAD, icon:"\u2b06",  label:"Upload File", sub:"Browser upload" },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            flex:1, padding:"10px 16px", borderRadius:9, border:"none",
            cursor:"pointer",
            background: tab===t.id ? "#1e2535" : "transparent",
            color: tab===t.id ? "#e2e8f0" : "#4a5568",
            fontSize:13, fontWeight: tab===t.id ? 700 : 400,
            transition:"all 140ms ease",
            display:"flex", flexDirection:"column", alignItems:"center", gap:2,
          }}>
            <span>{t.icon} {t.label}</span>
            <span style={{ fontSize:10, opacity:0.7 }}>{t.sub}</span>
          </button>
        ))}
      </div>

      {/* LOCAL PATH TAB */}
      {tab === TAB.LOCAL && (
        <div style={{ width:"100%", maxWidth:540, display:"flex", flexDirection:"column", gap:14 }}>
          <div style={{ padding:"20px 22px", borderRadius:14, background:"#111620",
                        border:"1px solid #1e2535" }}>
            <div style={{ fontSize:12, color:"#94a3b8", marginBottom:10 }}>
              Paste the{" "}
              <strong style={{ color:"#e2e8f0" }}>absolute path</strong>{" "}
              to a video file on this machine. The backend reads it in-place —
              no upload needed for 1.5 GB+ files.
            </div>
            <input
              id="local-path-input"
              type="text"
              value={localPath}
              onChange={e => { setLocalPath(e.target.value); setPathError(""); }}
              onKeyDown={e => e.key==="Enter" && !disabled && handleSubmitLocal()}
              placeholder="e.g.  d:\Projects\CricVision\aprill11\videos\match.mp4"
              style={{
                width:"100%", boxSizing:"border-box",
                padding:"12px 14px", borderRadius:9, background:"#0a0d12",
                border:`1px solid ${pathError ? "#ef4444" : localPath ? "#22c55e" : "#2d3a52"}`,
                color:"#e2e8f0", fontSize:13, fontFamily:"monospace",
                outline:"none", transition:"border-color 140ms",
              }}
            />
            {pathError && (
              <div style={{ marginTop:7, fontSize:12, color:"#f87171" }}>{pathError}</div>
            )}
            <div style={{ marginTop:12, fontSize:11, color:"#4a5568" }}>
              Quick-fill — click to pre-fill a match video path:
            </div>
            {[
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\WI_IND_2022_T20I2\\WI_IND_2022_T20I2.mp4",
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\PAK_ZIM_2025_T20I1\\PAK_ZIM_2025_T20I1.mp4",
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\NZ_SL_2023_T20I3\\NZ_SL_2023_T20I3.mp4",
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\ENG_IND_2022_ODI2\\ENG_IND_2022_ODI2.mp4",
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\SL_PAK_2025_T20I3\\SL_PAK_2025_T20I3.mp4",
              "d:\\Projects\\CricVision\\cricket_pipeline_v2\\videos\\ENG_SA_2022_T20I1\\ENG_SA_2022_T20I1.mp4",
            ].map(hint => (
              <button key={hint} onClick={() => {
                setLocalPath(hint); setPathError("");
              }} style={{
                display:"block", width:"100%", textAlign:"left",
                marginTop:5, padding:"5px 10px", borderRadius:6,
                background:"transparent", border:"1px solid #1e2535",
                color:"#94a3b8", fontSize:11, fontFamily:"monospace", cursor:"pointer",
              }}>
                {hint.split("\\").pop()}
              </button>
            ))}
          </div>

          <button id="local-analyse-btn" onClick={handleSubmitLocal}
            disabled={!localPath.trim() || disabled}
            style={{
              padding:"13px 0", borderRadius:10, border:"none",
              background: localPath.trim() && !disabled
                ? "linear-gradient(135deg,#22c55e 0%,#16a34a 100%)" : "#1e2535",
              color: localPath.trim() && !disabled ? "#fff" : "#4a5568",
              fontSize:15, fontWeight:700, letterSpacing:"0.04em",
              cursor: localPath.trim() && !disabled ? "pointer" : "default",
              transition:"all 160ms ease",
              boxShadow: localPath.trim() && !disabled
                ? "0 4px 20px rgba(34,197,94,0.35)" : "none",
            }}>
            {"\u26a1"} Analyse Local File
          </button>
        </div>
      )}

      {/* UPLOAD FILE TAB */}
      {tab === TAB.UPLOAD && (
        <div style={{ width:"100%", maxWidth:540, display:"flex", flexDirection:"column", gap:14 }}>
          <div
            id="upload-dropzone"
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={drag ? "upload-drag" : ""}
            style={{
              border:`2px dashed ${drag ? "#ef4444" : file ? "#22c55e" : "#1e2535"}`,
              borderRadius:16, padding:"44px 24px", textAlign:"center", cursor:"pointer",
              background: drag ? "rgba(239,68,68,0.06)" : file ? "rgba(34,197,94,0.04)" : "#111620",
              transition:"all 160ms ease",
            }}>
            <div style={{
              width:56, height:56, borderRadius:14,
              background: file ? "rgba(34,197,94,0.12)" : "#1e2535",
              margin:"0 auto 16px", display:"grid", placeItems:"center",
              border:`1px solid ${file ? "rgba(34,197,94,0.3)" : "#2d3a52"}`,
            }}>
              {file ? (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
                     stroke="#22c55e" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              ) : (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
                     stroke="#94a3b8" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              )}
            </div>
            {file ? (
              <>
                <div style={{ fontSize:15, fontWeight:600, color:"#e2e8f0" }}>{file.name}</div>
                <div className="font-mono" style={{ fontSize:12, color:"#94a3b8", marginTop:4 }}>
                  {formatFileSize(file.size)}
                </div>
                <div style={{ fontSize:12, color:"#4a5568", marginTop:6 }}>
                  Click to choose a different file
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize:14, fontWeight:500, color:"#e2e8f0" }}>
                  Drop video here, or{" "}
                  <span style={{ color:"#ef4444" }}>click to browse</span>
                </div>
                <div className="font-mono" style={{ fontSize:12, color:"#4a5568", marginTop:8 }}>
                  .mp4 {"\u00b7"} .mkv {"\u00b7"} .avi {"\u00b7"} .mov {"\u00b7"} .ts
                </div>
                <div style={{ marginTop:10, fontSize:11, color:"#fbbf24",
                              padding:"5px 10px", background:"rgba(245,158,11,0.08)",
                              borderRadius:6, display:"inline-block" }}>
                  For local 1.5 GB+ files — use the {"\u26a1"} Local Path tab instead
                </div>
              </>
            )}
            <input ref={inputRef} type="file" accept={ACCEPTED} style={{ display:"none" }}
                   onChange={e => pickFile(e.target.files[0])} />
          </div>

          <button id="upload-submit-btn" onClick={handleSubmitUpload}
            disabled={!file || disabled}
            style={{
              padding:"13px 0", borderRadius:10, border:"none",
              background: file && !disabled
                ? "linear-gradient(135deg,#ef4444 0%,#dc2626 100%)" : "#1e2535",
              color: file && !disabled ? "#fff" : "#4a5568",
              fontSize:15, fontWeight:700, letterSpacing:"0.04em",
              cursor: file && !disabled ? "pointer" : "default",
              transition:"all 160ms ease",
              boxShadow: file && !disabled ? "0 4px 20px rgba(239,68,68,0.35)" : "none",
            }}>
            Upload &amp; Analyse
          </button>
        </div>
      )}

      {/* Backend status banner */}
      {connectionStatus === "disconnected" ? (
        <div style={{
          marginTop:18, display:"flex", alignItems:"center", gap:12,
          padding:"12px 18px", borderRadius:10,
          background:"rgba(239,68,68,0.08)", border:"1px solid rgba(239,68,68,0.25)",
          maxWidth:540, width:"100%",
        }}>
          <span style={{ fontSize:18 }}>{"⚙\ufe0f"}</span>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:13, fontWeight:600, color:"#fca5a5" }}>
              Backend unreachable
            </div>
            <div style={{ fontSize:12, color:"#4a5568", marginTop:2 }}>
              Run:{" "}
              <code style={{ color:"#94a3b8" }}>.\start_local.ps1</code>{" "}
              in the backend folder
            </div>
          </div>
          <button onClick={onOpenSettings} style={{
            padding:"7px 14px", borderRadius:7, background:"#ef4444",
            border:"none", color:"#fff", fontSize:12, fontWeight:600, cursor:"pointer",
          }}>Settings</button>
        </div>
      ) : backendBusy ? (
        <div style={{ marginTop:14, padding:"10px 18px", borderRadius:8,
                      background:"rgba(245,158,11,0.12)", border:"1px solid rgba(245,158,11,0.3)",
                      color:"#fbbf24", fontSize:13, maxWidth:540, width:"100%" }}>
          {"\u26a0"} Backend is busy with another job — wait for it to finish or delete it.
        </div>
      ) : null}

      {/* Pipeline steps */}
      <div style={{ marginTop:28, display:"grid", gridTemplateColumns:"repeat(3,1fr)",
                    gap:10, width:"100%", maxWidth:540 }}>
        {[
          { n:"01", t:"Scan",   d:"YOLO + OCR detects score-strip every 2s" },
          { n:"02", t:"Detect", d:"5-signal wicket detection + dismissal cards" },
          { n:"03", t:"Review", d:"Clickable timeline with full event metadata" },
        ].map(s => (
          <div key={s.n} style={{ padding:13, borderRadius:10, background:"#111620",
                                  border:"1px solid #1e2535" }}>
            <div className="font-mono" style={{ fontSize:10, color:"#4a5568", marginBottom:5 }}>
              {s.n}
            </div>
            <div style={{ fontWeight:600, fontSize:13, marginBottom:3 }}>{s.t}</div>
            <div style={{ fontSize:11, color:"#94a3b8" }}>{s.d}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
