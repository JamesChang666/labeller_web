# AI Labeller Web (new project)

A standalone web version of your labeller built with FastAPI + vanilla JS canvas.

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
- Export All as:
  - `YOLO (.txt)`
  - `JSON` (full split json files, e.g. `annotations/train.json`)

## Run

```bash
cd web_labeller
pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

- http://127.0.0.1:8000

## Notes

- This web app reads local folders from the **server machine** path.
- You can input paths like `C:/Users/james/Desktop/labeller_test_file/yolo`.
- For detect, pick/import model in dropdown. If empty, it falls back to `yolo26m.pt`.
- Source mode is for dataset type selection, not model file selection.
