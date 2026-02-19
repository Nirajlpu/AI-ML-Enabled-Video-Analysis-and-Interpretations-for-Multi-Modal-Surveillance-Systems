# VisionIQ

VisionIQ is an AI-powered surveillance analytics platform with a React frontend and a Flask backend using YOLO-based detection.

## Tech Stack

- Frontend: React + TypeScript + Vite
- Backend: Flask + OpenCV + Ultralytics YOLO
- Database: PostgreSQL (`DATABASE_URL`)

## Project Structure

```text
VisionIQ/
├── backend/      # Flask API, detection + analytics logic
├── frontend/     # React dashboard UI
├── quickstart.sh # One-command local setup helper
└── README.md
```

## Quick Start (Recommended)

From the project root:

```bash
chmod +x quickstart.sh
./quickstart.sh
```

Then run services in separate terminals:

```bash
# Terminal 1
cd backend
source venv/bin/activate
python app.py
```

```bash
# Terminal 2
cd frontend
npm run dev
```

Open: `http://localhost:5173`

## Manual Setup

### 1) Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>
JWT_SECRET=change-this-secret
PORT=5001
```

Start backend:

```bash
python app.py
```

### 2) Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
VITE_API_URL=http://localhost:5001
```

Start frontend:

```bash
npm run dev
```

## Notes

- YOLO model files are loaded from `backend/` (for example `yolo11n.pt`) or downloaded automatically by Ultralytics when missing.
- Face recognition features depend on `insightface`, `onnxruntime`, and `faiss-cpu`.
- The backend default port is `5001` (from `backend/app.py`).

## Useful Docs

- `SETUP_AND_DEPLOYMENT.md`
- `DEPLOYMENT_CHECKLIST.md`
- `LIVE_MONITORING.md`
- `FEATURES.md`
