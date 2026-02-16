# AI Labeller Web

FastAPI + vanilla JS web annotation tool.

## Live App

- https://labeller-web.onrender.com/

No local `uvicorn` command is needed if you use the live URL.

## Repository

- https://github.com/JamesChang666/labeller_web

## Features

- Open dataset by source mode: Images / YOLO / RF-DETR
- Upload local dataset folder from browser (cloud-safe)
- Upload model file from browser (`.pt` / `.onnx`, cloud-safe)
- Draw, move, select, delete boxes
- Undo / Redo
- Save + Next / Previous
- Propagate previous labels
- Auto Detect (YOLO)
- Fuse overlapped boxes (same class)
- Remove / Restore images
- Image dropdown jump
- Class names load/save
- Clear All
- Export all:
  - YOLO (`.txt`)
  - JSON (split-level files like `annotations/train.json`)

## Cloud Usage (Render)

- URL: `https://labeller-web.onrender.com/`
- Cloud runs in HEADLESS mode.
- Native OS file/folder dialogs are disabled on cloud.
- Use `Upload Folder` for local files from browser.
- Use `Upload Model` for model files on cloud.

## Local Development

```bash
cd web_labeller
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open: `http://127.0.0.1:8000`

## Render Deploy

1. New Web Service on Render
2. Connect `JamesChang666/labeller_web`
3. Use repo defaults (`render.yaml`)

If manual settings are needed:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Env: `HEADLESS=1`
