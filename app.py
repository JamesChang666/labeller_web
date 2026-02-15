from __future__ import annotations

import base64
import glob
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

try:
    from ultralytics import YOLO
    HAS_YOLO = True
except Exception:
    HAS_YOLO = False


ALLOWED_EXTS = (".jpg", ".jpeg", ".png")


def list_images(path: str) -> list[str]:
    return sorted(
        f for f in glob.glob(f"{path}/*.*") if f.lower().endswith(ALLOWED_EXTS)
    )


def norm(path: str) -> str:
    return os.path.abspath(path).replace("\\", "/")


def yolo_root(path: str) -> str | None:
    p = norm(path).rstrip("/")

    def ok(c: str) -> bool:
        return any(os.path.isdir(f"{c}/images/{s}") for s in ("train", "val", "test"))

    cands = [p, norm(os.path.dirname(p)), norm(os.path.dirname(os.path.dirname(p)))]
    for c in cands:
        if c and ok(c):
            return c
    try:
        for child in os.listdir(p):
            cp = norm(os.path.join(p, child))
            if os.path.isdir(cp) and ok(cp):
                return cp
    except Exception:
        pass
    return None


def ensure_labels(root: str) -> None:
    for s in ("train", "val", "test"):
        if os.path.isdir(f"{root}/images/{s}"):
            os.makedirs(f"{root}/labels/{s}", exist_ok=True)


def read_yolo_labels(label_path: str, w: int, h: int) -> list[list[float]]:
    rects: list[list[float]] = []
    if not os.path.isfile(label_path) or os.path.getsize(label_path) == 0:
        return rects
    with open(label_path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            c, cx, cy, bw, bh = map(float, parts)
            rects.append([
                (cx - bw / 2) * w,
                (cy - bh / 2) * h,
                (cx + bw / 2) * w,
                (cy + bh / 2) * h,
                int(c),
            ])
    return rects


def save_yolo_labels(label_path: str, rects: list[list[float]], w: int, h: int) -> None:
    os.makedirs(os.path.dirname(label_path), exist_ok=True)
    if not rects:
        if os.path.exists(label_path):
            os.remove(label_path)
        return
    lines: list[str] = []
    for x1, y1, x2, y2, cid in rects:
        cx = ((x1 + x2) / 2) / w
        cy = ((y1 + y2) / 2) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        lines.append(f"{int(cid)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
    with open(label_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(lines))


@dataclass
class ProjectState:
    root: str = ""
    mode: str = "images"
    split: str = "train"
    images: list[str] = None

    def __post_init__(self):
        if self.images is None:
            self.images = []


class OpenProjectReq(BaseModel):
    path: str
    mode: str = "images"  # images | yolo | rfdetr


class SaveReq(BaseModel):
    image_path: str
    split: str
    rects: list[list[float]]


class DetectReq(BaseModel):
    image_path: str
    model_path: str = ""
    conf: float = 0.5
    cls: int = 0


class ExportReq(BaseModel):
    output_dir: str
    fmt: str  # YOLO (.txt) | JSON


class ClassesReq(BaseModel):
    names: list[str]


class RemoveReq(BaseModel):
    image_path: str
    split: str


class RestoreReq(BaseModel):
    split: str
    filename: str


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
HEADLESS = os.environ.get("HEADLESS", "0") == "1" or os.environ.get("RENDER", "") == "true"

app = FastAPI(title="AI Labeller Web")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

state = ProjectState()
model_cache: dict[str, Any] = {}
model_library: list[str] = ["yolo26m.pt", "yolo26n.pt"]
class_names: list[str] = ["class0", "class1", "class2"]


@app.get("/")
def root() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/system")
def system_info() -> dict[str, Any]:
    return {"dialogs_enabled": not HEADLESS}


@app.get("/api/dialog/folder")
def pick_folder(title: str = "Select Folder") -> dict[str, Any]:
    if HEADLESS:
        raise HTTPException(status_code=400, detail="Folder dialog is disabled on cloud server")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title)
        root.destroy()
        return {"path": norm(folder) if folder else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Folder dialog failed: {e}")


@app.get("/api/dialog/file")
def pick_file(
    title: str = "Select File",
    kind: str = "all",  # all | model
) -> dict[str, Any]:
    if HEADLESS:
        raise HTTPException(status_code=400, detail="File dialog is disabled on cloud server")
    try:
        import tkinter as tk
        from tkinter import filedialog
        if kind == "model":
            filetypes = [
                ("Model files", "*.pt *.onnx"),
                ("PyTorch", "*.pt"),
                ("ONNX", "*.onnx"),
                ("All files", "*.*"),
            ]
        else:
            filetypes = [("All files", "*.*")]
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        return {"path": norm(path) if path else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File dialog failed: {e}")


@app.get("/api/models")
def get_models() -> dict[str, Any]:
    return {"models": model_library}


@app.post("/api/models/import")
def import_model(payload: dict[str, str]) -> dict[str, Any]:
    path = norm(payload.get("path", ""))
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="Model file not found")
    if path not in model_library:
        model_library.append(path)
    return {"ok": True, "models": model_library, "selected": path}


@app.post("/api/project/open")
def open_project(req: OpenProjectReq) -> dict[str, Any]:
    path = norm(req.path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Folder not found")

    detected_root = yolo_root(path)
    if req.mode in ("yolo", "rfdetr") and detected_root:
        rootp = detected_root
    elif req.mode in ("yolo", "rfdetr") and os.path.isdir(f"{path}/images"):
        rootp = path
    elif req.mode == "images" and detected_root:
        rootp = detected_root
    else:
        rootp = path

    state.root = rootp
    state.mode = req.mode

    if os.path.isdir(f"{rootp}/images"):
        ensure_labels(rootp)
        split_files = {s: list_images(f"{rootp}/images/{s}") for s in ("train", "val", "test") if os.path.isdir(f"{rootp}/images/{s}")}
        non_empty = [s for s, files in split_files.items() if files]
        state.split = "train" if "train" in non_empty else (non_empty[0] if non_empty else (next(iter(split_files)) if split_files else "train"))
        state.images = split_files.get(state.split, [])
    else:
        state.split = "train"
        state.images = list_images(rootp)
        os.makedirs(f"{rootp}/labels/train", exist_ok=True)

    return {
        "root": state.root,
        "mode": state.mode,
        "split": state.split,
        "images": state.images,
        "count": len(state.images),
        "class_names": class_names,
    }


@app.post("/api/project/split")
def change_split(payload: dict[str, str]) -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    split = payload.get("split", "train")
    if os.path.isdir(f"{state.root}/images/{split}"):
        state.split = split
        state.images = list_images(f"{state.root}/images/{split}")
    else:
        state.split = "train"
        state.images = []
    return {"split": state.split, "images": state.images}


@app.get("/api/project/info")
def project_info() -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    splits = []
    if os.path.isdir(f"{state.root}/images"):
        for s in ("train", "val", "test"):
            if os.path.isdir(f"{state.root}/images/{s}"):
                splits.append(s)
    else:
        splits = ["train"]
    return {
        "root": state.root,
        "mode": state.mode,
        "split": state.split,
        "splits": splits,
        "count": len(state.images),
        "class_names": class_names,
    }


@app.get("/api/image")
def get_image(path: str) -> FileResponse:
    p = norm(path)
    if not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(p)


@app.get("/api/labels")
def get_labels(image_path: str, split: str = "train") -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    img = norm(image_path)
    if not os.path.isfile(img):
        raise HTTPException(status_code=404, detail="Image missing")
    with Image.open(img) as im:
        w, h = im.width, im.height
    base = os.path.splitext(os.path.basename(img))[0]
    lbl = f"{state.root}/labels/{split}/{base}.txt"
    rects = read_yolo_labels(lbl, w, h)
    return {
        "rects": rects,
        "width": w,
        "height": h,
        "has_label_file": os.path.isfile(lbl) and os.path.getsize(lbl) > 0,
    }


@app.post("/api/labels/save")
def save_labels(req: SaveReq) -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    img = norm(req.image_path)
    if not os.path.isfile(img):
        raise HTTPException(status_code=404, detail="Image missing")
    with Image.open(img) as im:
        w, h = im.width, im.height
    base = os.path.splitext(os.path.basename(img))[0]
    lbl = f"{state.root}/labels/{req.split}/{base}.txt"
    save_yolo_labels(lbl, req.rects, w, h)
    return {"ok": True}


@app.get("/api/classes")
def get_classes() -> dict[str, Any]:
    return {"class_names": class_names}


@app.post("/api/classes")
def set_classes(req: ClassesReq) -> dict[str, Any]:
    global class_names
    names = [n.strip() for n in req.names if n.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="Class names cannot be empty")
    class_names = names
    return {"ok": True, "class_names": class_names}


@app.post("/api/remove")
def remove_image(req: RemoveReq) -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    img = norm(req.image_path)
    if not os.path.isfile(img):
        raise HTTPException(status_code=404, detail="Image not found")
    split = req.split
    filename = os.path.basename(img)
    base = os.path.splitext(filename)[0]

    rem_img_dir = f"{state.root}/removed/{split}/images"
    rem_lbl_dir = f"{state.root}/removed/{split}/labels"
    os.makedirs(rem_img_dir, exist_ok=True)
    os.makedirs(rem_lbl_dir, exist_ok=True)
    dst_img = f"{rem_img_dir}/{filename}"
    shutil.move(img, dst_img)

    for ext in (".txt", ".json"):
        src_lbl = f"{state.root}/labels/{split}/{base}{ext}"
        if os.path.isfile(src_lbl):
            shutil.move(src_lbl, f"{rem_lbl_dir}/{base}{ext}")

    if os.path.isdir(f"{state.root}/images/{split}"):
        state.images = list_images(f"{state.root}/images/{split}")
    return {"ok": True, "images": state.images, "removed": filename}


@app.get("/api/restore/list")
def restore_list(split: str = "train") -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    rem_img_dir = f"{state.root}/removed/{split}/images"
    if not os.path.isdir(rem_img_dir):
        return {"files": []}
    files = sorted([f for f in os.listdir(rem_img_dir) if f.lower().endswith(ALLOWED_EXTS)])
    return {"files": files}


@app.post("/api/restore")
def restore_image(req: RestoreReq) -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    split = req.split
    filename = req.filename
    base = os.path.splitext(filename)[0]
    rem_img = f"{state.root}/removed/{split}/images/{filename}"
    if not os.path.isfile(rem_img):
        raise HTTPException(status_code=404, detail="Removed file not found")

    dst_img_dir = f"{state.root}/images/{split}"
    dst_lbl_dir = f"{state.root}/labels/{split}"
    os.makedirs(dst_img_dir, exist_ok=True)
    os.makedirs(dst_lbl_dir, exist_ok=True)
    shutil.move(rem_img, f"{dst_img_dir}/{filename}")

    for ext in (".txt", ".json"):
        rem_lbl = f"{state.root}/removed/{split}/labels/{base}{ext}"
        if os.path.isfile(rem_lbl):
            shutil.move(rem_lbl, f"{dst_lbl_dir}/{base}{ext}")

    if os.path.isdir(f"{state.root}/images/{split}"):
        state.images = list_images(f"{state.root}/images/{split}")
    return {"ok": True, "images": state.images, "restored": filename}


@app.post("/api/detect")
def detect(req: DetectReq) -> dict[str, Any]:
    if not HAS_YOLO:
        raise HTTPException(status_code=400, detail="ultralytics not installed")
    img = norm(req.image_path)
    raw_model = req.model_path.strip()
    model_path = norm(raw_model) if raw_model else ""
    if not os.path.isfile(img):
        raise HTTPException(status_code=404, detail="Image not found")
    model_id = model_path
    if model_path and os.path.isfile(model_path):
        model_id = model_path
    elif raw_model and ("/" not in raw_model and "\\" not in raw_model):
        # Allow model-name inference (e.g. yolo26m.pt) like desktop behavior.
        model_id = raw_model
    elif not raw_model:
        model_id = model_library[0] if model_library else "yolo26m.pt"
    else:
        raise HTTPException(status_code=404, detail="Model not found")

    model = model_cache.get(model_id)
    if model is None:
        model = YOLO(model_id)
        model_cache[model_id] = model

    results = model(img, conf=req.conf, verbose=False)
    rects: list[list[float]] = []
    for r in results:
        if r.boxes is None:
            continue
        for b in r.boxes.xyxy:
            rects.append([b[0].item(), b[1].item(), b[2].item(), b[3].item(), req.cls])
    return {"rects": rects, "model": model_id}


@app.post("/api/export")
def export_all(req: ExportReq) -> dict[str, Any]:
    if not state.root:
        raise HTTPException(status_code=400, detail="No project loaded")
    out_dir = norm(req.output_dir)
    os.makedirs(out_dir, exist_ok=True)

    entries: list[tuple[str, str, str]] = []
    if os.path.isdir(f"{state.root}/images"):
        for split in ("train", "val", "test"):
            if not os.path.isdir(f"{state.root}/images/{split}"):
                continue
            for img in list_images(f"{state.root}/images/{split}"):
                base = os.path.splitext(os.path.basename(img))[0]
                lbl = f"{state.root}/labels/{split}/{base}.txt"
                entries.append((split, img, lbl))
    else:
        for img in list_images(state.root):
            base = os.path.splitext(os.path.basename(img))[0]
            lbl = f"{state.root}/labels/train/{base}.txt"
            entries.append(("train", img, lbl))

    if req.fmt == "YOLO (.txt)":
        for split, img, lbl in entries:
            os.makedirs(f"{out_dir}/images/{split}", exist_ok=True)
            os.makedirs(f"{out_dir}/labels/{split}", exist_ok=True)
            shutil.copy2(img, f"{out_dir}/images/{split}/{os.path.basename(img)}")
            if os.path.isfile(lbl):
                shutil.copy2(lbl, f"{out_dir}/labels/{split}/{os.path.basename(lbl)}")
    else:
        by_split: dict[str, list[dict[str, Any]]] = {}
        for split, img, lbl in entries:
            os.makedirs(f"{out_dir}/images/{split}", exist_ok=True)
            os.makedirs(f"{out_dir}/annotations", exist_ok=True)
            shutil.copy2(img, f"{out_dir}/images/{split}/{os.path.basename(img)}")
            with Image.open(img) as im:
                w, h = im.width, im.height
            rects = read_yolo_labels(lbl, w, h)
            anns = []
            for x1, y1, x2, y2, cid in rects:
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                anns.append({"class_id": int(cid), "bbox_xyxy": [x1, y1, x2, y2], "bbox_yolo": [cx, cy, bw, bh]})
            item = {
                "image": os.path.basename(img),
                "split": split,
                "width": w,
                "height": h,
                "annotations": anns,
            }
            by_split.setdefault(split, []).append(item)
        for split, items in by_split.items():
            out_json = f"{out_dir}/annotations/{split}.json"
            with open(out_json, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)

    return {"ok": True, "count": len(entries), "output": out_dir}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
