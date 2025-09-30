from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import Iterable, Tuple

import requests

from ..core.config import CONFIG, SIAConfig
from ..core.logger import get_logger

logger = get_logger(__name__)

CHUNK_SIZE = 8192


def compute_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return digest


def download_strict(
    url: str,
    dst: Path,
    allowed_types: Iterable[str],
    timeout: int,
    max_attempts: int,
) -> Tuple[str, int, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    attempts = 0
    backoff = 0.5
    allowed = set(allowed_types)
    while attempts < max_attempts:
        attempts += 1
        try:
            with requests.get(url, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "").split(";")[0]
                if content_type not in allowed:
                    raise ValueError(f"不允许的类型: {content_type}")
                content_length = int(resp.headers.get("Content-Length", "0"))
                tmp_path = dst.with_suffix(dst.suffix + ".part")
                sha = hashlib.sha256()
                total = 0
                with tmp_path.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        total += len(chunk)
                        sha.update(chunk)
                if content_length and total != content_length:
                    raise ValueError("大小不匹配")
                tmp_path.replace(dst)
                digest = sha.hexdigest()
                logger.info("下载完成 %s -> %s", url, dst)
                return digest, total, content_type
        except Exception as exc:  # noqa: BLE001
            logger.warning("下载失败(%s/%s): %s", attempts, max_attempts, exc)
            if attempts >= max_attempts:
                raise
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("下载失败")
