from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

CONFIG_DIR = Path.home() / ".sia"
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class DownloadPolicy:
    allowed_types: set[str] = field(
        default_factory=lambda: {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
        }
    )
    max_body_kb: int = 64
    max_attempts: int = 4
    timeout: int = 30


@dataclass
class SIAConfig:
    base_dir: Path = Path.home() / "SIA-Gallery"
    port: int = 18080
    hmac_key: str = "change-me"
    concurrency: int = 2
    retry_backoff: float = 0.5
    enable_hardlinks: bool = False
    log_dir: Path = CONFIG_DIR / "logs"
    download: DownloadPolicy = field(default_factory=DownloadPolicy)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["base_dir"] = str(self.base_dir)
        data["log_dir"] = str(self.log_dir)
        data["download"]["allowed_types"] = sorted(self.download.allowed_types)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SIAConfig":
        base_dir = Path(data.get("base_dir", Path.home() / "SIA-Gallery"))
        log_dir = Path(data.get("log_dir", CONFIG_DIR / "logs"))
        download_data = data.get("download", {})
        allowed = set(download_data.get("allowed_types", [])) or {
            "image/jpeg",
            "image/png",
        }
        policy = DownloadPolicy(
            allowed_types=allowed,
            max_body_kb=int(download_data.get("max_body_kb", 64)),
            max_attempts=int(download_data.get("max_attempts", 4)),
            timeout=int(download_data.get("timeout", 30)),
        )
        return cls(
            base_dir=base_dir,
            port=int(data.get("port", 18080)),
            hmac_key=str(data.get("hmac_key", "change-me")),
            concurrency=int(data.get("concurrency", 2)),
            retry_backoff=float(data.get("retry_backoff", 0.5)),
            enable_hardlinks=bool(data.get("enable_hardlinks", False)),
            log_dir=log_dir,
            download=policy,
        )


class ConfigManager:
    def __init__(self) -> None:
        self._listeners: list[Callable[[SIAConfig], None]] = []
        self._config = self._load()

    def _load(self) -> SIAConfig:
        if not CONFIG_PATH.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            config = SIAConfig()
            self.save(config)
            return config
        with CONFIG_PATH.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return SIAConfig.from_dict(data)

    def get(self) -> SIAConfig:
        return self._config

    def save(self, config: Optional[SIAConfig] = None) -> None:
        if config is not None:
            self._config = config
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as fp:
            yaml.safe_dump(self._config.to_dict(), fp, allow_unicode=True)
        self._notify()

    def update(self, **kwargs: Any) -> SIAConfig:
        data = self._config.to_dict()
        data.update(kwargs)
        updated = SIAConfig.from_dict(data)
        self.save(updated)
        return updated

    def add_listener(self, callback: Callable[[SIAConfig], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener(self._config)

    def signature(self) -> str:
        payload = json.dumps(self._config.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()


CONFIG = ConfigManager()
