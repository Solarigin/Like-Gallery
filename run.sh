#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR="$ROOT_DIR/sia-desktop"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN=${PYTHON:-python3}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERROR] 未找到 Python 解释器：$PYTHON_BIN" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] 创建虚拟环境 $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip wheel
python -m pip install -e "$APP_DIR"

PORT=$(python - <<'PY'
from sia.core.config import CONFIG
print(CONFIG.get().port)
PY
)

python - <<'PY'
from pathlib import Path
from sia.core.config import CONFIG

cfg = CONFIG.get()
cfg.base_dir.mkdir(parents=True, exist_ok=True)
images = cfg.base_dir / "images.json"
if not images.exists():
    images.write_text("[]", encoding="utf-8")
print(f"图库目录: {cfg.base_dir}")
print(f"索引文件: {images}")
PY

echo "[INFO] 启动服务：http://127.0.0.1:${PORT}"
exec uvicorn sia.server.api:app --host 0.0.0.0 --port "$PORT"
