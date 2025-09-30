from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest

from sia.server.downloader import download_strict


class ImageHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # type: ignore[override]
        if self.path != "/image.jpg":
            self.send_response(404)
            self.end_headers()
            return
        data = b"\xff\xd8JPEGDATA"
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def image_server(tmp_path: Path):
    handler = ImageHandler
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/image.jpg"
    server.shutdown()


def test_download_strict(tmp_path: Path, image_server: str) -> None:
    dst = tmp_path / "image.jpg"
    sha, size, content_type = download_strict(
        image_server,
        dst,
        {"image/jpeg"},
        timeout=5,
        max_attempts=2,
    )
    assert dst.exists()
    assert size == dst.stat().st_size
    assert content_type == "image/jpeg"
    assert len(sha) == 64
