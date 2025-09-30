from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from sqlalchemy import desc, select

from .config import CONFIG, SIAConfig
from .db import File, Item, get_engine, session_scope
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class GalleryItem:
    author: str
    path: str
    mtime: datetime
    post_id: str
    source: str

    def to_json(self) -> dict[str, str]:
        return {
            "author": self.author,
            "path": self.path,
            "mtime": int(self.mtime.timestamp()),
            "post_id": self.post_id,
            "source": self.source,
        }


def _images_path(base_dir: Path) -> Path:
    return base_dir / "images.json"


def build_index(config: Optional[SIAConfig] = None) -> Path:
    cfg = config or CONFIG.get()
    engine = get_engine(cfg.base_dir)
    with session_scope(engine) as session:
        stmt = (
            select(File, Item)
            .join(Item, File.folder == Item.author)
            .order_by(desc(File.mtime))
        )
        gallery: List[GalleryItem] = []
        for file_row, item in session.execute(stmt):
            gallery.append(
                GalleryItem(
                    author=file_row.folder,
                    path=file_row.rel_path.replace("\\", "/"),
                    mtime=file_row.mtime,
                    post_id=item.post_id,
                    source=item.source or "",
                )
            )
    output = [item.to_json() for item in gallery]
    path = _images_path(cfg.base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("重建索引: %s 项", len(output))
    return path


def incremental_update(rel_paths: Iterable[str], config: Optional[SIAConfig] = None) -> None:
    cfg = config or CONFIG.get()
    path = _images_path(cfg.base_dir)
    if not path.exists():
        build_index(cfg)
        return
    # for simplicity, rebuild entire index if updates significant
    build_index(cfg)


def paginate(
    page: int = 1,
    page_size: int = 40,
    author: Optional[str] = None,
    query: Optional[str] = None,
    config: Optional[SIAConfig] = None,
) -> dict[str, object]:
    cfg = config or CONFIG.get()
    engine = get_engine(cfg.base_dir)
    with session_scope(engine) as session:
        stmt = (
            select(File, Item)
            .join(Item, File.folder == Item.author)
            .order_by(desc(File.mtime))
        )
        if author:
            stmt = stmt.where(File.folder == author)
        if query:
            like_term = f"%{query}%"
            stmt = stmt.where(File.rel_path.like(like_term))
        total = session.execute(stmt).all()
        start = (page - 1) * page_size
        end = start + page_size
        slice_rows = total[start:end]
        items = [
            GalleryItem(
                author=file.folder,
                path=file.rel_path,
                mtime=file.mtime,
                post_id=item.post_id,
                source=item.source or "",
            ).to_json()
            for file, item in slice_rows
        ]
    return {
        "page": page,
        "page_size": page_size,
        "total": len(total),
        "items": items,
    }
