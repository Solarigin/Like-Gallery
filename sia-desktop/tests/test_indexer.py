from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sia.core import indexer
from sia.core.config import SIAConfig
from sia.core.db import Asset, File, Item, get_engine, session_scope


def create_sample(base_dir: Path) -> None:
    engine = get_engine(base_dir)
    with session_scope(engine) as session:
        item = Item(author="tester", post_id="p1", source="src")
        session.add(item)
        asset = Asset(sha256="sha", ext="jpg", bytes=1, width=None, height=None)
        session.add(asset)
        session.flush()
        file_entry = File(
            asset_id=asset.id,
            rel_path="00001_tester/00001_tester_001.jpg",
            folder="tester",
            mtime=datetime.utcnow(),
        )
        session.add(file_entry)
        session.commit()


def test_build_index(tmp_path: Path) -> None:
    base_dir = tmp_path / "gallery"
    base_dir.mkdir()
    cfg = SIAConfig(base_dir=base_dir)
    create_sample(base_dir)
    index_path = indexer.build_index(cfg)
    data = index_path.read_text(encoding="utf-8")
    assert "tester" in data
    result = indexer.paginate(page=1, page_size=10, config=cfg)
    assert result["total"] >= 1
