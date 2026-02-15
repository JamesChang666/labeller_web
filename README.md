# AI Labeller Web

A standalone web version of the labeller built with FastAPI + vanilla JS canvas.

Repository:

- `https://github.com/JamesChang666/labeller_web`

## What it supports

- Open project by folder path (server-local path)
- Source modes: Images / YOLO dataset / RF-DETR dataset
- Bounding box draw/select/delete
- Move selected box by drag
- Class id editing for selected box
- Save + Next / Previous
- Propagate (copy previous image boxes)
- Auto Detect (YOLO model)
- Undo / Redo
- Fuse overlapped boxes (same class)
- Remove current image and restore removed images
- Image dropdown jump
- Class names load/save
- Model dropdown library + import model path
- Clear All
- Export All as:
  - `YOLO (.txt)`
  - `JSON` (full split json files, e.g. `annotations/train.json`)

## Run Local

```bash
cd web_labeller
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

- http://127.0.0.1:8000

## Deploy on Render (from GitHub)

1. Push this `web_labeller` repo to GitHub.
2. In Render: `New +` -> `Web Service` -> connect this repo.
3. Render will detect `render.yaml`.
4. Deploy.

Render start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Environment:

- `HEADLESS=1` on cloud (already configured in `render.yaml`)

## Production URL

After deployment, the URL is on Render, e.g.:

- `https://labeller-web.onrender.com`

Use your actual Render service URL.

Cloud (Render):

- Use your Render URL, e.g. `https://labeller-web.onrender.com`
- No local `uvicorn` command needed.

## Notes

- This web app reads local folders from the server machine path.
- On cloud (HEADLESS mode), native Browse dialogs are disabled.
- In cloud mode, use server-side paths or extend app with upload/S3 storage.
- For detect, pick/import model in dropdown. If empty, fallback is `yolo26m.pt`.
- Source mode is dataset type selection, not model file selection.
