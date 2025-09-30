from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.config import CONFIG
from ..core.logger import get_logger

logger = get_logger(__name__)


TASK_NAME = "SocialImageArchiver"


def create_task(executable: Path) -> None:
    command = [
        "schtasks",
        "/Create",
        "/SC",
        "ONLOGON",
        "/TN",
        TASK_NAME,
        "/TR",
        str(executable),
    ]
    logger.info("创建计划任务: %s", command)
    subprocess.run(command, check=False)


def delete_task() -> None:
    command = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    logger.info("删除计划任务")
    subprocess.run(command, check=False)
