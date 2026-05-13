# CricketLens Frontend

React + Vite SPA that talks to the CricketLens FastAPI backend.

```
cricketlens-frontend/
├── index.html              Vite entry HTML
├── package.json
├── vite.config.js          Proxies /api → http://localhost:8000
├── .env.example
└── src/
    ├── main.jsx            React mount point
    ├── App.jsx             Top-level state machine: upload → processing → review
    ├── api.js              fetch + SSE + upload helpers
    ├── utils.js            time/string helpers
    ├── styles.css          Design tokens (CSS variables)
    └── components/
        ├── Header.jsx
        ├── UploadScreen.jsx
        ├── ProcessingScreen.jsx
        ├── ReviewScreen.jsx
        ├── VideoPlayer.jsx     <video> + custom marker timeline
        ├── EventDetailCard.jsx Side card for the active event
        ├── FilterTabs.jsx      All / Wickets / Near misses
        └── EventCard.jsx       Card in the events grid
```

---

## 1. Install

You'll need **Node 18+** (`node --version`).

In a terminal at the project root:

```bash
cd cricketlens-frontend
npm install
```

That installs:

| Package                | Why |
|------------------------|-----|
| `react`, `react-dom`   | UI framework |
| `vite`                 | Dev server + bundler |
| `@vitejs/plugin-react` | JSX / Fast Refresh |

No other deps — fonts come from Google Fonts (preloaded in `index.html`),
icons are inline SVGs, and the styling is plain CSS variables.

---

## 2. Start the backend (in a separate terminal)

```bash
cd ../cricketlens-backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Backend runs on `http://localhost:8000`.

---

## 3. Start the frontend

```bash
cd cricketlens-frontend
npm run dev
```

Open **http://localhost:5173** — Vite proxies `/api/*` to `localhost:8000`,
so no CORS pain.

---

## 4. How the app flows

1. **Upload** — drag-drop or click. We `POST /api/upload` and also keep a
   local `URL.createObjectURL(file)` so the `<video>` tag can play
   immediately (the backend doesn't expose a streaming endpoint yet).
2. **Processing** — we open an `EventSource` on `/api/stream/{job_id}`
   and update the progress ring as messages arrive.
3. **Review** — once `status: "done"`, we read `events` from the final
   SSE message (or fall back to `GET /api/events/{job_id}`) and render
   the player + side card + grid.

---

## 5. Production build

```bash
npm run build      # outputs to dist/
npm run preview    # serves dist/ on port 4173
```

For production, set `VITE_API_BASE` to your backend's public URL
(`cp .env.example .env` and edit). Make sure the backend's
`CORS_ORIGINS` env var includes your frontend origin.

---

## 6. Optional backend improvement: stream the original video

Right now we use `URL.createObjectURL(file)` so playback works without
a streaming endpoint. If you want the video to be playable across
sessions / from another device, add this to `routers/api.py`:

```python
from fastapi.responses import FileResponse

@router.get("/video/{job_id}")
def stream_video(job_id: str):
    job = _job_store.get(job_id)
    if job is None or not job.video_path:
        raise HTTPException(404, "Video not available")
    return FileResponse(job.video_path, media_type="video/mp4")
```

Then in `src/api.js` set the player URL to
`` `${BASE}/api/video/${jobId}` ``.

---

## 7. Running in VS Code

1. Open the project root folder in VS Code (`File → Open Folder…`).
2. Open two integrated terminals: one for the backend, one for the
   frontend (`` Ctrl+` `` to toggle, then `+` to add a second).
3. Run the two commands from sections 2 and 3 above.
4. Recommended VS Code extensions: **ESLint**, **Prettier**,
   **ES7+ React/Redux/React-Native snippets**, **Python**.

That's it. Drag a match video onto the page and watch the markers
appear on the timeline as the backend reports each phase.
