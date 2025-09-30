from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from .logger import get_logger

logger = get_logger(__name__)

FILE_PATTERN = re.compile(r"^(?P<folder>\d{5})_(?P<index>\d{3})")


@dataclass
class RenamePlan:
    source: Path
    destination: Path
    preview: bool = False


def _normalize_name(folder_index: int, file_index: int, suffix: str) -> str:
    return f"{folder_index:05d}_{file_index:03d}{suffix}"


def _group_by_parent(paths: Iterable[Path]) -> dict[Path, List[Path]]:
    grouped: dict[Path, List[Path]] = {}
    for path in paths:
        grouped.setdefault(path.parent, []).append(path)
    return grouped


def scan_directory(base_dir: Path) -> List[RenamePlan]:
    paths = sorted(p for p in base_dir.glob("**/*") if p.is_file())
    grouped = _group_by_parent(paths)
    plans: List[RenamePlan] = []
    for folder, files in grouped.items():
        files.sort()
        folder_index = _folder_index(folder.relative_to(base_dir))
        for idx, file in enumerate(files, start=1):
            suffix = file.suffix.lower()
            normalized = _normalize_name(folder_index, idx, suffix)
            dest = folder / normalized
            if file.name != normalized:
                plans.append(RenamePlan(source=file, destination=dest))
    return plans


def apply(plans: Iterable[RenamePlan], preview: bool = True) -> List[Tuple[Path, Path]]:
    executed: List[Tuple[Path, Path]] = []
    for plan in plans:
        if preview:
            logger.info("预览改名 %s -> %s", plan.source.name, plan.destination.name)
            continue
        plan.destination.parent.mkdir(parents=True, exist_ok=True)
        if plan.destination.exists():
            logger.warning("目标已存在，跳过 %s", plan.destination)
            continue
        plan.source.rename(plan.destination)
        executed.append((plan.source, plan.destination))
        logger.info("改名 %s -> %s", plan.source.name, plan.destination.name)
    return executed


def _folder_index(rel_path: Path) -> int:
    parts = list(rel_path.parts)
    if not parts:
        return 0
    first = parts[0]
    match = FILE_PATTERN.match(first)
    if match:
        return int(match.group("folder"))
    digits = [int(part) for part in parts if part.isdigit()]
    return digits[0] if digits else 0
