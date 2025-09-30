from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sia.core.config import SIAConfig
from sia.server.api import app


def _set_config(tmp_path: Path, monkeypatch) -> SIAConfig:
    config = SIAConfig(base_dir=tmp_path, log_dir=tmp_path / "logs")
    monkeypatch.setattr("sia.server.api.CONFIG.get", lambda: config, raising=False)
    return config


def test_gallery_home_served(tmp_path, monkeypatch):
    _set_config(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_images_json_bootstrap(tmp_path, monkeypatch):
    cfg = _set_config(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/images.json")
    assert resp.status_code == 200
    assert resp.json() == []
    assert (cfg.base_dir / "images.json").exists()


def test_serve_gallery_files(tmp_path, monkeypatch):
    cfg = _set_config(tmp_path, monkeypatch)
    image_dir = cfg.base_dir / "artist"
    image_dir.mkdir(parents=True)
    image = image_dir / "sample.txt"
    image.write_text("hello", encoding="utf-8")

    client = TestClient(app)
    resp = client.get("/artist/sample.txt")
    assert resp.status_code == 200
    assert resp.text == "hello"


def test_outside_gallery_blocked(tmp_path, monkeypatch):
    _set_config(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get("/../secret.txt")
    assert resp.status_code == 404
