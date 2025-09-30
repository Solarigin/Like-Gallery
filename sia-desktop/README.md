# Social Image Archiver (SIA)

Social Image Archiver 将原有的自动编号与图库原型升级为跨平台桌面应用。核心组件包括 PySide6 桌面端、FastAPI 本地服务、严格的下载去重管道与 SQLite 元数据索引。

## 功能概览

- ✅ FastAPI + Uvicorn 提供 `/save`、`/api/items`、`/healthz` 本地接口
- ✅ HMAC-SHA256 验签、Content-Type 白名单、原子写入、指数退避下载器
- ✅ SQLite + SQLAlchemy 记录资产/文件/条目，并导出兼容 `gallery.html` 的 `images.json`
- ✅ PySide6 桌面界面：内嵌图库、任务监控、设置与日志页签
- ✅ Watchdog 文件监听与重命名工具封装
- ✅ Windows 打包脚本（PyInstaller + Inno Setup）

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python -m sia.app
```

首次运行会在 `~/.sia/config.yaml` 生成配置，默认根目录位于 `~/SIA-Gallery`。

## 配置

`src/sia/core/config.py` 定义所有配置字段，实际文件位于 `~/.sia/config.yaml`。关键字段：

- `base_dir`：图库根目录
- `port`：FastAPI 服务端口
- `hmac_key`：`/save` 请求验签密钥
- `download.allowed_types`：允许的 MIME 类型
- `retry_backoff`、`download.max_attempts`：下载重试策略

在设置页修改后立即保存并热更新。

## API 调用示例

```bash
python - <<'PY'
import json
import requests
from sia.server.downloader import compute_signature

payload = {
    "author": "demo",
    "postId": "123",
    "images": ["https://example.com/image.jpg"],
}
body = json.dumps(payload).encode()
secret = "change-me"
headers = {"X-Signature": compute_signature(secret, body)}
resp = requests.post("http://127.0.0.1:18080/save", json=payload, headers=headers)
print(resp.json())
PY
```

## 测试

```bash
pytest
```

## 代码规范

- `ruff`、`black`、`mypy` 配置在 `pyproject.toml`
- 日志配置位于 `src/sia/core/logger.py`

## 打包

Windows 上运行：

```powershell
pip install pyinstaller
pwsh scripts/build_win.ps1
```

`build_win.ps1` 会调用 PyInstaller，并使用 Inno Setup 创建安装包（需预装 Inno Setup）。

## Definition of Done

- Windows 双击 `SIA.exe` 即可启动桌面程序
- 点击“开始监听”后，拖入/点赞保存的图片能够写入图库并自动编号
- Gallery 页签实时展示新增图片，程序重启后配置与索引仍可读取

