from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from ..core import renamer
from ..core.logger import get_logger

logger = get_logger(__name__)


def preview(base_dir: Path) -> List[renamer.RenamePlan]:
    logger.info("扫描目录以生成修复计划: %s", base_dir)
    return renamer.scan_directory(base_dir)


def execute(plans: Iterable[renamer.RenamePlan]) -> None:
    renamer.apply(plans, preview=False)
