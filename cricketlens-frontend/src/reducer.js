// ─── Initial state ────────────────────────────────────────────────────────────

export const initialState = {
  // Default to local backend — no settings required for local dev.
  // If the user saves a different URL via Settings it is stored in localStorage
  // and takes priority on the next page load.
  baseUrl:           localStorage.getItem("cl_base_url") || "http://localhost:8000",
  connectionStatus:  "unknown",      // "unknown" | "connected" | "disconnected"
  backendBusy:       false,

  uploadFile:        null,
  runCommentary:     localStorage.getItem("cl_run_commentary") !== "false",

  phase:             "idle",         // "idle"|"uploading"|"processing"|"done"|"error"
  uploadProgress:    0,              // 0–100
  pipelineProgress:  0,              // 0–100
  pipelineMessage:   "",
  pipelineError:     null,

  jobId:             null,
  results:           null,           // { events, duration_sec, wicket_count, nm_count }

  activeEventId:     null,
  settingsOpen:      false,
  activeTab:         "all",          // "all"|"wickets"|"near_misses"
  jobHistory:        [],
};

// ─── Action types ─────────────────────────────────────────────────────────────

export const A = {
  SET_BASE_URL:        "SET_BASE_URL",
  SET_CONNECTION:      "SET_CONNECTION",
  SET_BACKEND_BUSY:    "SET_BACKEND_BUSY",
  SET_FILE:            "SET_FILE",
  SET_RUN_COMMENTARY:  "SET_RUN_COMMENTARY",
  UPLOAD_START:        "UPLOAD_START",
  UPLOAD_PROGRESS:     "UPLOAD_PROGRESS",
  PIPELINE_START:      "PIPELINE_START",
  PIPELINE_UPDATE:     "PIPELINE_UPDATE",
  DONE:                "DONE",
  ERROR:               "ERROR",
  RESET_UPLOAD:        "RESET_UPLOAD",
  SET_ACTIVE_EVENT:    "SET_ACTIVE_EVENT",
  TOGGLE_SETTINGS:     "TOGGLE_SETTINGS",
  SET_ACTIVE_TAB:      "SET_ACTIVE_TAB",
  SET_JOB_HISTORY:     "SET_JOB_HISTORY",
  SET_RESULTS:         "SET_RESULTS",
  SET_JOB_ID:          "SET_JOB_ID",
};

// ─── Reducer ──────────────────────────────────────────────────────────────────

export function reducer(state, { type, payload }) {
  switch (type) {

    case A.SET_BASE_URL:
      localStorage.setItem("cl_base_url", payload);
      return { ...state, baseUrl: payload, connectionStatus: "unknown" };

    case A.SET_CONNECTION:
      return {
        ...state,
        connectionStatus: payload.status,
        backendBusy: payload.busy ?? state.backendBusy,
      };

    case A.SET_BACKEND_BUSY:
      return { ...state, backendBusy: payload };

    case A.SET_FILE:
      return { ...state, uploadFile: payload };

    case A.SET_RUN_COMMENTARY:
      localStorage.setItem("cl_run_commentary", String(payload));
      return { ...state, runCommentary: payload };

    case A.UPLOAD_START:
      return {
        ...state,
        phase: "uploading",
        uploadProgress: 0,
        pipelineProgress: 0,
        pipelineMessage: "Uploading…",
        pipelineError: null,
        jobId: null,
        results: null,
        activeEventId: null,
        activeTab: "all",
      };

    case A.UPLOAD_PROGRESS:
      return { ...state, uploadProgress: payload };

    case A.PIPELINE_START:
      return { ...state, phase: "processing", jobId: payload };

    case A.PIPELINE_UPDATE:
      return {
        ...state,
        pipelineProgress: Math.round((payload.progress ?? 0) * 100),
        pipelineMessage: payload.message ?? state.pipelineMessage,
      };

    case A.DONE:
      localStorage.setItem("cl_last_job_id", state.jobId || payload?.jobId || "");
      return {
        ...state,
        phase: "done",
        results: payload,
        pipelineProgress: 100,
      };

    case A.SET_RESULTS:
      return {
        ...state,
        phase: "done",
        results: payload.results,
        jobId: payload.jobId,
        pipelineProgress: 100,
        pipelineError: null,
      };

    case A.ERROR:
      return { ...state, phase: "error", pipelineError: payload };

    case A.RESET_UPLOAD:
      return {
        ...state,
        phase: "idle",
        uploadFile: null,
        uploadProgress: 0,
        pipelineProgress: 0,
        pipelineMessage: "",
        pipelineError: null,
        jobId: null,
        results: null,
        activeEventId: null,
      };

    case A.SET_ACTIVE_EVENT:
      return { ...state, activeEventId: payload };

    case A.TOGGLE_SETTINGS:
      return { ...state, settingsOpen: payload ?? !state.settingsOpen };

    case A.SET_ACTIVE_TAB:
      return { ...state, activeTab: payload };

    case A.SET_JOB_HISTORY:
      return { ...state, jobHistory: payload };

    case A.SET_JOB_ID:
      return { ...state, jobId: payload };

    default:
      return state;
  }
}
