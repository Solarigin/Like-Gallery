#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
APP_DIR="$ROOT_DIR/sia-desktop"
VENV_DIR="$ROOT_DIR/.venv"

if [ -n "${PYTHON:-}" ]; then
  IFS=' ' read -r -a PYTHON_BIN <<<"$PYTHON"
else
  PYTHON_BIN=()
  while IFS= read -r candidate; do
    IFS=' ' read -r -a parts <<<"$candidate"
    if "${parts[@]}" -c 'import sys; assert sys.version_info >= (3, 10)' >/dev/null 2>&1; then
      PYTHON_BIN=("${parts[@]}")
      break
    fi
  done <<'CANDIDATES'
python3
python3.12
python3.11
python
py -3.12
py -3.11
py -3.10
py -3
CANDIDATES
fi

if [ ${#PYTHON_BIN[@]} -eq 0 ]; then
  echo "[ERROR] 未找到可用的 Python 3.10+ 解释器，请安装后重试，或者通过设置 PYTHON 环境变量指定解释器。" >&2
  exit 1
fi

PYTHON_DISPLAY="${PYTHON_BIN[*]}"
echo "[INFO] 使用 Python 解释器：$PYTHON_DISPLAY"

if [ ! -d "$VENV_DIR" ]; then
  echo "[INFO] 创建虚拟环境 $VENV_DIR"
  "${PYTHON_BIN[@]}" -m venv "$VENV_DIR"
fi

ACTIVATE_SCRIPT="$VENV_DIR/bin/activate"
if [ ! -f "$ACTIVATE_SCRIPT" ]; then
  ACTIVATE_SCRIPT="$VENV_DIR/Scripts/activate"
  if [ ! -f "$ACTIVATE_SCRIPT" ]; then
    echo "[ERROR] 未找到虚拟环境激活脚本：$VENV_DIR/bin/activate 或 $VENV_DIR/Scripts/activate" >&2
    exit 1
  fi
fi

# shellcheck disable=SC1090
source "$ACTIVATE_SCRIPT"

"${PYTHON_BIN[@]}" -m pip install --upgrade pip wheel
"${PYTHON_BIN[@]}" -m pip install -e "$APP_DIR"

PORT=$("${PYTHON_BIN[@]}" - <<'PY'
from sia.core.config import CONFIG
print(CONFIG.get().port)
PY
)

"${PYTHON_BIN[@]}" - <<'PY'
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
