from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, HttpUrl, field_validator

from ..core import indexer
from ..core.config import CONFIG, SIAConfig
from ..core.db import Asset, File, Item, get_engine, session_scope
from ..core.logger import get_logger
from .downloader import compute_signature, download_strict

logger = get_logger(__name__)

app = FastAPI(title="Social Image Archiver")

GALLERY_PATH = Path(__file__).resolve().parents[3] / "gallery.html"

FILE_PATTERN = re.compile(r"^(?P<prefix>\d{5})_[^_]+_(?P<index>\d{3})")


class SavePayload(BaseModel):
    author: str
    postId: str
    images: List[HttpUrl]
    source: Optional[str] = None
    caption: Optional[str] = None

    @field_validator("author")
    @classmethod
    def author_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("author 不能为空")
        return v


async def get_config() -> SIAConfig:
    return CONFIG.get()


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=FileResponse)
async def gallery_page() -> FileResponse:
    if not GALLERY_PATH.exists():
        raise HTTPException(status_code=500, detail="gallery.html 未找到")
    return FileResponse(GALLERY_PATH, media_type="text/html")


@app.get("/images.json")
async def images_json(config: SIAConfig = Depends(get_config)) -> JSONResponse:
    path = config.base_dir / "images.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")
        return JSONResponse([])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="images.json 格式错误") from exc
    return JSONResponse(data)


@app.get("/api/items")
async def api_items(
    page: int = 1,
    page_size: int = 40,
    author: Optional[str] = None,
    q: Optional[str] = None,
    config: SIAConfig = Depends(get_config),
) -> dict[str, object]:
    return indexer.paginate(page=page, page_size=page_size, author=author, query=q, config=config)


def resolve_author_folder(author: str, base_dir: Path) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", author)
    base_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        p for p in base_dir.iterdir()
        if p.is_dir() and p.name.endswith(f"_{safe}")
    ]
    if candidates:
        return candidates[0]
    index = _next_folder_index(base_dir)
    folder = base_dir / f"{index:05d}_{safe}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _next_folder_index(base_dir: Path) -> int:
    max_idx = 0
    for directory in base_dir.glob("*/"):
        if not directory.is_dir():
            continue
        parts = directory.name.split("_", 1)
        if parts and parts[0].isdigit():
            max_idx = max(max_idx, int(parts[0]))
    return max_idx + 1


def _current_max_index(folder: Path) -> int:
    max_idx = 0
    for file in folder.glob("*.*"):
        match = FILE_PATTERN.match(file.name)
        if match:
            idx = int(match.group("index"))
            max_idx = max(max_idx, idx)
    return max_idx


def _resolve_gallery_file(path: str, base_dir: Path) -> Path:
    target = (base_dir / path).resolve()
    base = base_dir.resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=404, detail="文件不在图库目录内")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return target


@app.post("/save")
async def save_endpoint(request: Request, payload: SavePayload, config: SIAConfig = Depends(get_config)) -> dict[str, object]:
    body = await request.body()
    if len(body) > config.download.max_body_kb * 1024:
        raise HTTPException(status_code=413, detail="请求体过大")
    signature = request.headers.get("X-Signature")
    expected = compute_signature(config.hmac_key, body)
    if signature != expected:
        raise HTTPException(status_code=401, detail="签名不正确")
    base_dir = config.base_dir
    engine = get_engine(base_dir)
    folder = resolve_author_folder(payload.author, base_dir)
    saved: List[str] = []
    duplicates: List[str] = []
    with session_scope(engine) as session:
        item = Item(author=payload.author, post_id=payload.postId, source=payload.source)
        session.add(item)
        session.flush()
        max_idx = _current_max_index(folder)
        for image_url in payload.images:
            max_idx += 1
            suffix = Path(image_url.path).suffix or ".jpg"
            filename = f"{folder.name}_{max_idx:03d}{suffix}"
            dst = folder / filename
            sha, size, content_type = download_strict(
                str(image_url),
                dst,
                config.download.allowed_types,
                config.download.timeout,
                config.download.max_attempts,
            )
            asset = session.query(Asset).filter(Asset.sha256 == sha).first()
            if asset:
                duplicates.append(str(dst))
            else:
                asset = Asset(sha256=sha, ext=suffix.lstrip("."), bytes=size, width=None, height=None)
                session.add(asset)
                session.flush()
            file_entry = File(
                asset_id=asset.id,
                rel_path=str(dst.relative_to(base_dir)).replace("\\", "/"),
                folder=payload.author,
                mtime=datetime.utcnow(),
            )
            session.add(file_entry)
            saved.append(str(dst))
        session.commit()
    indexer.incremental_update(saved, config=config)
    return {"ok": True, "saved": saved, "duplicates": duplicates}


@app.get("/{requested_path:path}")
async def gallery_assets(requested_path: str, config: SIAConfig = Depends(get_config)) -> FileResponse:
    if requested_path in {"", "index.html"}:
        return await gallery_page()
    file_path = _resolve_gallery_file(requested_path, config.base_dir)
    return FileResponse(file_path)
