from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sia.server import api
from sia.server.downloader import compute_signature
from sia.core.config import SIAConfig


def test_save_endpoint(monkeypatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "gallery"
    cfg = SIAConfig(base_dir=base_dir, hmac_key="secret")

    monkeypatch.setattr(api.CONFIG, "get", lambda: cfg)

    def fake_download(url: str, dst: Path, *_args, **_kwargs):
        data = b"data"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        return ("a" * 64, len(data), "image/jpeg")

    monkeypatch.setattr(api, "download_strict", fake_download)

    client = TestClient(api.app)
    payload = {
        "author": "tester",
        "postId": "p1",
        "images": ["http://example.com/image.jpg"],
        "source": "src",
    }
    body = json.dumps(payload, ensure_ascii=False).encode()
    signature = compute_signature(cfg.hmac_key, body)
    response = client.post(
        "/save",
        content=body,
        headers={"X-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    saved_path = Path(data["saved"][0])
    assert saved_path.exists()
