"# CricVision

A comprehensive cricket match analysis and event detection system powered by computer vision, OCR, and speech recognition.

## Overview

CricVision processes cricket match videos to automatically detect and extract key events including:

- **Wickets**: Ball dismissals with comprehensive wicket card data
- **Near-Miss Events**: Close shaves, boundaries, and other significant moments
- **Player Information**: Batter and bowler identification from broadcast overlays
- **Commentary Analysis**: Automated speech-to-text and event correlation from match commentary

The system uses:

- **YOLO v8s** for object detection (wicket cards, score displays, broadcaster logos)
- **EasyOCR** for optical character recognition on broadcast overlays
- **OpenAI Whisper** for commentary transcription and analysis
- **FastAPI** backend with React frontend

## Project Structure

```
CricVision/
├── cricketlens-backend/       # FastAPI backend server
│   ├── main.py               # Application entry point
│   ├── config.py             # Configuration and settings
│   ├── requirements.txt       # Python dependencies
│   ├── pipeline/             # Video processing pipeline
│   ├── routers/              # API endpoints
│   └── storage/              # Job store and persistence
│
├── cricketlens-frontend/      # React + Vite frontend
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│
├── aprill11/                 # Data processing notebooks
├── cricket_pipeline_v2/      # Additional pipeline code
├── Dataset/                  # Training data and models
└── README.md                 # This file
```

## Setup Instructions

### Backend Setup

1. **Navigate to backend directory:**

   ```powershell
   cd cricketlens-backend
   ```

2. **Install Python dependencies:**

   ```powershell
   pip install -r requirements.txt
   ```

   > **Note**: PyTorch and TorchVision should be installed separately with the correct CUDA version for GPU support:

   ```powershell
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

3. **Start the backend server:**

   ```powershell
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload --workers 1
   ```

   Or use the provided startup script:

   ```powershell
   .\start_local.ps1
   ```

   The backend will be available at: **http://localhost:8000**
   - API documentation: **http://localhost:8000/docs**
   - ReDoc documentation: **http://localhost:8000/redoc**

### Frontend Setup

1. **Navigate to frontend directory:**

   ```powershell
   cd cricketlens-frontend
   ```

2. **Install Node dependencies:**

   ```powershell
   npm install
   ```

3. **Start the development server:**

   ```powershell
   npm run dev
   ```

   The frontend will be available at: **http://localhost:5173**

## API Endpoints

### Job Management

- `POST /api/upload` - Upload a cricket video for processing
- `POST /api/import-local` - Process a local video file
- `GET /api/jobs` - List all jobs
- `GET /api/jobs/{job_id}` - Get job status
- `GET /api/stream/{job_id}` - Stream real-time progress updates (Server-Sent Events)
- `POST /api/reprocess/{job_id}` - Reprocess a job
- `DELETE /api/jobs/{job_id}` - Delete a job

### Event Retrieval

- `GET /api/events/{job_id}` - Get detected wickets and near-miss events
- `GET /api/video/{job_id}` - Stream video with HTTP Range support

### Health

- `GET /health` - Server health check

## Usage Example

1. Start the backend server
2. Start the frontend (or use API docs at `/docs`)
3. Upload a cricket match video
4. Monitor progress via SSE stream
5. Retrieve detected events once processing completes

## Configuration

Key configuration options in `config.py`:

- `YOLO_CONF_THRESHOLD` - Confidence threshold for object detection (default: 0.35)
- `YOLO_MODEL_PATH` - Path to YOLO weights (auto-resolved to Dataset folder)
- `BROADCASTER_CROPS` - OCR region coordinates for different broadcasters
- `UPLOAD_FOLDER` - Directory for storing uploaded videos
- `OUTPUTS_FOLDER` - Directory for storing processing results

## Requirements

- Python 3.10+
- Node.js 16+ (for frontend)
- CUDA 11.8+ (optional, for GPU acceleration)
- ~4GB free disk space for models and video processing

## License

Proprietary - CricVision"
