# -*- coding: utf-8 -*-
"""
drop_autonumber_daemon.py
原有功能: 自动编号 + Like-Saver 本地服务 + 监听
新增功能: 每次保存/重命名图片时自动更新 images.json 索引文件
"""

import os
import re
import csv
import time
import json
import threading
import traceback
from pathlib import Path
from typing import List, Tuple, Optional, Set
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# ============ 基础配置 ============
DEFAULT_BASE = r"C:\Users\Solarigin\Pictures\X"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

FOLDER_NUM_WIDTH = 5  # 文件夹编号位数 -> 00001_
FILE_NUM_WIDTH = 3  # 图片编号位数 -> _001
ASSIGN_MODE = "append"  # append(续尾) / fill(补洞)
FILE_SORT_MODE = "name"  # name / mtime / exif（exif 需 Pillow）
CONFLICT_DIRS = "dedup"  # 目录冲突：skip / dedup
CONFLICT_FILES = "skip"  # 文件冲突：skip / dedup

WATCH = True  # 默认监听模式
SCAN_INTERVAL = 2.0  # 扫描间隔秒
STABILITY_CHECKS = 3  # 稳定性检查次数
PREVIEW = False  # 预览（不落盘）

# 通知后端：auto / winsdk / win10toast / burnttoast / none
DEFAULT_NOTIFY_BACKEND = "auto"

# Like-Saver（本地 HTTP）默认开启
LIKE_SAVER_ENABLED = True
LIKE_SAVER_PORT = 38999
LIKE_SAVER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
XL_MARKER = ".xlikes"  # 仅作标识，不拦截改名

LOG_DIR = Path(__file__).with_name("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "drop_autonumber.log"
REPORT_CSV = ""  # 可设为路径写映射报告

# 隐藏/系统目录过滤（仅一级子目录）
IGNORE_HIDDEN_PREFIX = True
IGNORE_SYSNAMES = {"system volume information", "$recycle.bin"}

# 正则
RE_NUMBERED = re.compile(r'^(?P<num>\d{5})_(?P<base>.+)$')
RE_STRIP_PREFIX = re.compile(r'^(?:\d{5}_)+')


# ============ 日志 ============
def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


# ============ 通知（可选后端） ============
class Notifier:
    def __init__(self, prefer: str = "auto"):
        self.backend = None
        self._n = None
        self._xml = None
        self.toaster = None

        prefer = (prefer or "auto").lower()

        def try_winsdk():
            try:
                from winsdk.windows.ui import notifications as _n  # type: ignore
                from winsdk.windows.data import xml as _xml  # type: ignore
                self._n = _n
                self._xml = _xml
                self.app_id = "DropAutoNumber.Python.App"
                self.backend = "winsdk"
                return True
            except Exception:
                return False

        def try_win10toast():
            try:
                from win10toast import ToastNotifier  # type: ignore
                self.toaster = ToastNotifier()
                self.backend = "win10toast"
                return True
            except Exception:
                return False

        if prefer == "winsdk":
            ok = try_winsdk() or try_win10toast() or True
            if not ok: self.backend = "burnttoast"
        elif prefer == "win10toast":
            ok = try_win10toast() or try_winsdk() or True
            if not ok: self.backend = "burnttoast"
        elif prefer == "burnttoast":
            self.backend = "burnttoast"
        elif prefer == "none":
            self.backend = "none"
        else:
            # auto: winsdk -> win10toast -> burnttoast
            if not try_winsdk():
                if not try_win10toast():
                    self.backend = "burnttoast"

        log(f"Notifier backend = {self.backend} (prefer={prefer})")

    def notify(self, title: str, message: str, duration: int = 5):
        if self.backend == "none":
            return
        log(f"NOTIFY: {title} | {message}")
        try:
            if self.backend == "winsdk" and self._n and self._xml:
                doc = self._xml.dom.XmlDocument()
                doc.load_xml(
                    f"<toast><visual><binding template='ToastGeneric'>"
                    f"<text>{title}</text><text>{message}</text>"
                    f"</binding></visual></toast>"
                )
                self._n.ToastNotificationManager.create_toast_notifier(self.app_id) \
                    .show(self._n.ToastNotification(doc))
                return

            if self.backend == "win10toast" and self.toaster:
                self.toaster.show_toast(title, message, duration=duration, threaded=False)
                return

            if self.backend == "burnttoast":
                import shutil, subprocess
                if shutil.which("powershell"):
                    safe_title = str(title).replace("'", "''")
                    safe_msg = str(message).replace("'", "''")
                    ps = (
                        "if (Get-Module -ListAvailable -Name BurntToast) "
                        f"{{ New-BurntToastNotification -Text '{safe_title}', '{safe_msg}' }}"
                    )
                    subprocess.Popen(
                        ["powershell", "-NoProfile", "-Command", ps],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                return

        except Exception as e:
            log(f"notify error: {e}")


notifier: Notifier  # set in main()


# ============ 基础工具 ============
def list_subfolders_once(base: Path) -> List[Path]:
    res = []
    sysnames = {s.lower() for s in IGNORE_SYSNAMES}
    with os.scandir(base) as it:
        for e in it:
            if e.is_dir():
                name = e.name
                if IGNORE_HIDDEN_PREFIX and name.startswith("."):
                    continue
                if name.lower() in sysnames:
                    continue
                res.append(Path(e.path))
    return res


def list_loose_images(base: Path) -> List[Path]:
    files = []
    with os.scandir(base) as it:
        for e in it:
            if e.is_file():
                p = Path(e.path)
                if p.suffix.lower() in IMAGE_EXTS:
                    files.append(p)
    return files


def strip_chain_prefix(name: str) -> str:
    return RE_STRIP_PREFIX.sub("", name)


def ensure_unique_temp(path: Path, suffix: str) -> Path:
    tmp = path.with_name(path.name + suffix)
    i = 1
    while tmp.exists():
        tmp = path.with_name(path.name + f"{suffix}{i}")
        i += 1
    return tmp


def dedup_target(target: Path) -> Path:
    if not target.exists():
        return target
    i = 1
    stem, suf = target.stem, target.suffix
    alt = target.with_name(f"{stem}_{i}{suf}")
    while alt.exists():
        i += 1
        alt = target.with_name(f"{stem}_{i}{suf}")
    return alt


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return -1


def wait_stable(paths: List[Path], interval: float, checks: int) -> None:
    if checks <= 0:
        return
    for _ in range(checks):
        sizes1 = [file_size(p) for p in paths]
        time.sleep(interval)
        sizes2 = [file_size(p) for p in paths]
        if sizes1 != sizes2:
            time.sleep(interval)
            return wait_stable(paths, interval, checks)
    return


# ============ EXIF（可选） ============
def get_exif_ts(p: Path) -> Optional[float]:
    try:
        from PIL import Image, ExifTags  # type: ignore
        key = {v: k for k, v in ExifTags.TAGS.items()}
        with Image.open(p) as im:
            ex = im.getexif()
            if not ex:
                return None
            from datetime import datetime
            for name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                tag = key.get(name)
                if tag is None:
                    continue
                val = ex.get(tag)
                if isinstance(val, str):
                    try:
                        return datetime.strptime(val, "%Y:%m:%d %H:%M:%S").timestamp()
                    except Exception:
                        pass
    except Exception:
        return None
    return None


def sort_images(files: List[Path], mode: str) -> List[Path]:
    if mode == "mtime":
        return sorted(files, key=lambda p: (p.stat().st_mtime, p.name.lower()))
    if mode == "exif":
        def key(p: Path):
            ts = get_exif_ts(p)
            if ts is not None:
                return (0, ts, p.name.lower())
            return (1, p.stat().st_mtime, p.name.lower())

        return sorted(files, key=key)
    return sorted(files, key=lambda p: p.name.lower())


# ============ 新增：自动更新 images.json ============
def update_gallery_index():
    """
    扫描 DEFAULT_BASE（你的图库根）并写入 images.json。
    每个条目：{path, folder, name, mtime}，path 为相对路径（/ 分隔）。
    """
    try:
        base = Path(DEFAULT_BASE)
        items = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                try:
                    m = int(p.stat().st_mtime)
                except Exception:
                    m = 0
                rel = p.relative_to(base).as_posix()
                folder = rel.split('/')[-2] if '/' in rel else ''
                items.append({'path': rel, 'folder': folder, 'name': p.name, 'mtime': m})
        out = base / "images.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        log(f"[Gallery] images.json 已更新（{len(items)} 条） -> {out}")
    except Exception as e:
        log(f"[Gallery] 更新 images.json 失败: {e}")


# ============ 编号策略 ============
def collect_existing_numbers(base: Path) -> Tuple[Set[int], List[Tuple[Path, int, str]], List[Path]]:
    used: Set[int] = set()
    numbered = []
    unnumbered = []
    for f in list_subfolders_once(base):
        m = RE_NUMBERED.match(f.name)
        if m:
            n = int(m.group("num"))
            b = m.group("base")
            numbered.append((f, n, b))
            used.add(n)
        else:
            unnumbered.append(f)
    return used, numbered, unnumbered


def next_number_append(used: Set[int]) -> int:
    return (max(used) + 1) if used else 1


def next_number_fill(used: Set[int]) -> int:
    n = 1
    while n in used:
        n += 1
    return n


def assign_number(used: Set[int], mode: str) -> int:
    if mode == "fill":
        n = next_number_fill(used)
    else:
        n = next_number_append(used)
    used.add(n)
    return n


# ============ 图片批量重命名/统一命名 ============
def normalize_xlikes_folder(folder: Path, file_num_width: int, sort_mode: str, conflict_policy: str) -> int:
    """
    仅把不符合“{folder.name}_NNN.ext”模式的文件改名为下一个连续编号；
    已符合规范的保留原编号。返回调整数量。
    """
    imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not imgs:
        return 0

    pat = re.compile(rf'^{re.escape(folder.name)}_(\d{{{file_num_width}}})$', re.IGNORECASE)

    conforming: List[Tuple[Path, int]] = []
    nonconforming: List[Path] = []
    for p in imgs:
        m = pat.fullmatch(p.stem)
        if m:
            try:
                conforming.append((p, int(m.group(1))))
            except Exception:
                nonconforming.append(p)
        else:
            nonconforming.append(p)

    if not nonconforming:
        return 0

    max_idx = max([idx for _, idx in conforming], default=0)
    nonconforming = sort_images(nonconforming, sort_mode)

    changed = 0
    for src in nonconforming:
        while True:
            max_idx += 1
            dst = folder / f"{folder.name}_{max_idx:0{file_num_width}d}{src.suffix.lower()}"
            if not dst.exists():
                break
        try:
            os.rename(src, dst)
            log(f"[XLikes统一命名] {src.name} -> {dst.name}")
            changed += 1
        except Exception as e:
            log(f"[XLikes统一命名] 改名失败：{src.name} -> {e}")

    if changed:
        notifier.notify("X点赞命名已统一", f"{folder.name}：调整 {changed} 个")
        # 非 preview 模式下更新 images.json
        try:
            update_gallery_index()
        except Exception as e:
            log(f"[Gallery] 更新 images.json 失败: {e}")
    return changed


def current_max_index(folder: Path, file_num_width: int) -> int:
    """扫描 {folder.name}_NNN.* 的最大 NNN。"""
    pat = re.compile(rf'^{re.escape(folder.name)}_(\d{{{file_num_width}}})$', re.IGNORECASE)
    max_idx = 0
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            m = pat.fullmatch(p.stem)
            if m:
                try:
                    idx = int(m.group(1))
                    if idx > max_idx:
                        max_idx = idx
                except Exception:
                    pass
    return max_idx


def rename_images_in_folder(folder: Path, preview: bool, file_num_width: int,
                            conflict_policy: str, sort_mode: str,
                            report_rows: List[Tuple[str, str, str]]) -> None:
    # 防呆：宽度必须是 int
    try:
        file_num_width = int(file_num_width)
    except Exception:
        log(f"⚠️ file_num_width 非数字：{file_num_width}，已回退为默认 {FILE_NUM_WIDTH}")
        file_num_width = FILE_NUM_WIDTH

    imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not imgs:
        return
    imgs = sort_images(imgs, sort_mode)

    plan = []
    for i, src in enumerate(imgs, 1):
        dst_name = f"{folder.name}_{i:0{file_num_width}d}{src.suffix.lower()}"
        dst = folder / dst_name
        if src == dst:
            continue
        plan.append((src, dst))
    if not plan:
        log(f"📁 [{folder.name}] 图片阶段：无需修改")
        return

    log(f"=== 图片阶段 [{folder.name}]：{len(plan)} 个需改名 ===")
    for s, d in plan:
        log(f"{s.name}  ->  {d.name}")

    if preview:
        log("🔍 预览模式：未对图片做改动\n")
        notifier.notify("图片预览完成", f"{folder.name} 将重命名 {len(plan)} 个文件")
        return

    temps = []
    for s, _ in plan:
        tmp = ensure_unique_temp(s, ".__renametmp__")
        log(f"[改名] {s.name}  ->  {tmp.name}")
        os.rename(s, tmp)
        temps.append(tmp)
    for tmp, (_, final_dst) in zip(temps, plan):
        target = final_dst
        if target.exists():
            if conflict_policy == "skip":
                base_original = tmp.with_name(tmp.name.split(".__renametmp__")[0])
                back = base_original
                k = 1
                while back.exists():
                    back = base_original.with_name(base_original.stem + f"_keep{k}" + base_original.suffix)
                    k += 1
                os.rename(tmp, back)
                log(f"[跳过] 目标存在：{target.name} -> 回退 {back.name}")
                continue
            else:
                target = dedup_target(target)
        os.rename(tmp, target)
        log(f"[已改名] {tmp.name} -> {target.name}")
    notifier.notify("图片重命名完成", f"{folder.name} 共处理 {len(plan)} 个文件")

    # 更新 images.json（若非预览）
    try:
        if not preview:
            update_gallery_index()
    except Exception as e:
        log(f"[Gallery] 更新 images.json 失败: {e}")


# ============ 处理入口对象 ============
def handle_unumbered_folder(base: Path, folder: Path, used: Set[int],
                            mode: str, preview: bool, dir_conflict: str,
                            file_conflict: str, file_num_width: int,
                            sort_mode: str, report_rows: List[Tuple[str, str, str]]) -> None:
    base_name = strip_chain_prefix(folder.name) or folder.name
    n = assign_number(used, mode)
    final_name = f"{n:0{FOLDER_NUM_WIDTH}d}_{base_name}"
    final_path = base / final_name

    if RE_NUMBERED.match(folder.name):
        log(f"ℹ️ 已编号目录跳过：{folder.name}")
        return

    if folder == final_path:
        log(f"ℹ️ 目录已是目标名：{folder.name}")
    else:
        log(f"=== 目录阶段：{folder.name} -> {final_name}")
        if preview:
            log("🔍 预览模式：未对目录做改动\n")
            notifier.notify("目录预览完成", f"{folder.name} -> {final_name}")
        else:
            tmp = ensure_unique_temp(folder, ".__renametmp__")
            os.rename(folder, tmp)
            target = final_path
            if target.exists():
                if dir_conflict == "skip":
                    log(f"[跳过] 目标已存在：{target.name}（目录阶段）")
                    notifier.notify("目录重命名跳过", f"{final_name} 已存在")
                    return
                else:
                    target = dedup_target(target)
            os.rename(tmp, target)
            folder = target
            notifier.notify("目录重命名完成", f"{folder.name}")

    rename_images_in_folder(folder, preview, file_num_width, file_conflict, sort_mode, report_rows)

    # rename_images_in_folder 内已会更新 images.json（非 preview），这里不必重复调用


def handle_loose_image(base: Path, img: Path, used: Set[int], mode: str,
                       preview: bool, dir_conflict: str, file_conflict: str,
                       file_num_width: int, sort_mode: str,
                       report_rows: List[Tuple[str, str, str]]) -> None:
    base_name = strip_chain_prefix(img.stem) or img.stem
    n = assign_number(used, mode)
    folder_name = f"{n:0{FOLDER_NUM_WIDTH}d}_{base_name}"
    folder_path = base / folder_name

    log(f"=== 打包单图：{img.name} -> {folder_name}\\")
    if preview:
        notifier.notify("单图预览完成", f"{img.name} 将打包至 {folder_name}")
        return

    target_folder = folder_path
    if target_folder.exists():
        if dir_conflict == "skip":
            log(f"[跳过] 目标文件夹已存在：{target_folder.name}")
            notifier.notify("打包跳过", f"{target_folder.name} 已存在")
            return
        else:
            target_folder = dedup_target(target_folder)
    target_folder.mkdir(parents=True, exist_ok=True)

    dst_single = target_folder / img.name
    if dst_single.exists():
        if file_conflict == "skip":
            log(f"[跳过] 目标内已存在同名文件：{dst_single.name}")
        else:
            dst_single = dedup_target(dst_single)
            log(f"[去重] 调整目标文件名：{dst_single.name}")
    os.rename(img, dst_single)

    # ✅ 修复点：这里参数必须是 (folder, preview, file_num_width, conflict_policy, sort_mode, report_rows)
    rename_images_in_folder(target_folder, preview, file_num_width, file_conflict, sort_mode, report_rows)

    notifier.notify("单图打包完成", f"{folder_name}")

    # rename_images_in_folder 已负责更新 images.json（若非 preview）


# ============ 批处理 & 监听 ============
def process_once(base: Path, assign_mode: str, preview: bool, file_sort: str,
                 conflict_dirs: str, conflict_files: str,
                 report_csv: str) -> None:
    if not base.exists():
        notifier.notify("路径不存在", str(base))
        log(f"❌ 路径不存在：{base}")
        return

    report_rows: List[Tuple[str, str, str]] = []
    try:
        pending = list_loose_images(base)
        wait_stable(pending, interval=SCAN_INTERVAL, checks=STABILITY_CHECKS)

        used, numbered, unnumbered = collect_existing_numbers(base)

        # 先散图
        for img in list_loose_images(base):
            handle_loose_image(base, img, used, assign_mode, preview,
                               conflict_dirs, conflict_files, FILE_NUM_WIDTH, file_sort, report_rows)

        # 再未编号目录
        unnumbered_sorted = sorted(unnumbered, key=lambda p: strip_chain_prefix(p.name).lower())
        for folder in unnumbered_sorted:
            handle_unumbered_folder(base, folder, used, assign_mode, preview,
                                    conflict_dirs, conflict_files, FILE_NUM_WIDTH, file_sort, report_rows)

        if report_csv:
            try:
                with open(report_csv, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["TYPE", "FROM", "TO"])
                    w.writerows(report_rows)
                log(f"📝 报告已写入：{report_csv}（{len(report_rows)} 条）")
            except Exception as e:
                log(f"⚠️ 报告写入失败：{e}")

        notifier.notify("批处理完成", f"{base}")
        log("🎉 完成（预览）" if preview else "🎉 完成（已落盘）")

        # 最后一次性更新 images.json（若非 preview）
        try:
            if not preview:
                update_gallery_index()
        except Exception as e:
            log(f"[Gallery] 更新 images.json 失败: {e}")

    except Exception:
        err = traceback.format_exc()
        notifier.notify("运行错误", "请查看日志")
        log(err)


def watch_loop(base: Path, assign_mode: str, preview: bool, file_sort: str,
               conflict_dirs: str, conflict_files: str, report_csv: str) -> None:
    if not base.exists():
        notifier.notify("路径不存在", str(base))
        log(f"❌ 路径不存在：{base}")
        return

    notifier.notify("开始监听", f"{base}")
    log(f"👀 监听中：{base}")

    seen_dirs = set(p.name for p in list_subfolders_once(base))
    seen_imgs = set(p.name for p in list_loose_images(base))
    used, _, _ = collect_existing_numbers(base)

    report_rows: List[Tuple[str, str, str]] = []

    try:
        while True:
            time.sleep(SCAN_INTERVAL)
            curr_dirs = set(p.name for p in list_subfolders_once(base))
            curr_imgs = set(p.name for p in list_loose_images(base))
            new_dirs = [base / n for n in (curr_dirs - seen_dirs)]
            new_imgs = [base / n for n in (curr_imgs - seen_imgs)]

            if not new_dirs and not new_imgs:
                seen_dirs, seen_imgs = curr_dirs, curr_imgs
                continue

            wait_stable(new_dirs + new_imgs, interval=SCAN_INTERVAL, checks=STABILITY_CHECKS)

            # 新散图
            for img in [p for p in new_imgs if p.suffix.lower() in IMAGE_EXTS]:
                handle_loose_image(base, img, used, assign_mode, preview,
                                   conflict_dirs, conflict_files, FILE_NUM_WIDTH, file_sort, report_rows)

            # 新目录（仅未编号）
            for d in new_dirs:
                if RE_NUMBERED.match(d.name):
                    log(f"ℹ️ 新增目录已编号，保持：{d.name}")
                    continue
                handle_unumbered_folder(base, d, used, assign_mode, preview,
                                        conflict_dirs, conflict_files, FILE_NUM_WIDTH, file_sort, report_rows)

            seen_dirs = set(p.name for p in list_subfolders_once(base))
            seen_imgs = set(p.name for p in list_loose_images(base))

            if report_csv:
                try:
                    with open(report_csv, "w", newline="", encoding="utf-8-sig") as f:
                        w = csv.writer(f)
                        w.writerow(["TYPE", "FROM", "TO"])
                        w.writerows(report_rows)
                except Exception as e:
                    log(f"⚠️ 报告写入失败：{e}")
    except KeyboardInterrupt:
        notifier.notify("已停止监听", f"{base}")
        log("🛑 监听已停止")


# ============ Like-Saver（合入版） ============
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(s: str) -> str:
    return SAFE_NAME_RE.sub("_", s or "")


def ext_from_url(u: str) -> str:
    parsed = urlparse(u)
    q = {}
    if parsed.query:
        for kv in parsed.query.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                q[k] = v
    fmt = q.get("format")
    if fmt:
        return "." + fmt.lower()
    path = parsed.path
    if "." in path:
        return "." + path.rsplit(".", 1)[-1].lower()
    return ".jpg"


def download(url: str, to_file: Path, timeout=30):
    to_file.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": LIKE_SAVER_UA})
    with urlopen(req, timeout=timeout) as resp, open(to_file, "wb") as f:
        f.write(resp.read())


def resolve_author_folder(base: Path, author: str) -> Path:
    """
    若已存在形如 00001_author 的编号目录，则返回它；
    否则使用 base/author（新建），等待外层 watcher 之后自动编号。
    同时放置 XL_MARKER 标记。
    """
    clean = safe_name(author)
    candidates = list_subfolders_once(base)
    for p in candidates:
        if strip_chain_prefix(p.name).lower() == clean.lower():
            (p / XL_MARKER).touch(exist_ok=True)
            return p
    new_dir = base / clean
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / XL_MARKER).touch(exist_ok=True)
    return new_dir


class LikeSaverHandler(BaseHTTPRequestHandler):
    # 静默日志
    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        if self.path != "/save":
            self.send_error(404);
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
            data = self.rfile.read(n)
            payload = json.loads(data.decode("utf-8", "ignore"))
            author = safe_name(payload.get("author"))
            tweet_id = safe_name(str(payload.get("tweetId")))
            images = [str(u) for u in (payload.get("images") or []) if str(u).startswith("http")]
            if not author or not tweet_id or not images:
                self.send_error(400, "invalid payload");
                return

            dest_dir = resolve_author_folder(LIKE_BASE_DIR, author)

            # 直接按“目录名_递增编号”命名保存
            idx = current_max_index(dest_dir, FILE_NUM_WIDTH)
            saved = 0
            for url in images:
                ext = ext_from_url(url)
                while True:
                    idx += 1
                    dst = dest_dir / f"{dest_dir.name}_{idx:0{FILE_NUM_WIDTH}d}{ext}"
                    if not dst.exists():
                        break
                try:
                    download(url, dst)
                    saved += 1
                    log(f"[LikeSaver] 保存 -> {dst.name}")
                except Exception as e:
                    log(f"[LikeSaver] 下载失败：{url} -> {e}")

            # 兜底标准化（历史遗留）
            changed = normalize_xlikes_folder(dest_dir, FILE_NUM_WIDTH, FILE_SORT_MODE, CONFLICT_FILES)

            notifier.notify("已保存点赞图片", f"{author} / {tweet_id}：{saved} 成功；规范化 {changed} 个")
            log(f"[LikeSaver] {author}/{tweet_id} -> saved={saved}, normalized={changed}")

            # 更新 images.json（已保存/修改图片时）
            try:
                update_gallery_index()
            except Exception as e:
                log(f"[Gallery] 更新 images.json 失败: {e}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "saved": saved}).encode("utf-8"))

        except Exception as e:
            notifier.notify("点赞保存出错", str(e))
            log(f"[LikeSaver] error: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))


def start_like_saver(port: int, base: Path):
    global LIKE_BASE_DIR
    LIKE_BASE_DIR = base
    srv = ThreadingHTTPServer(("127.0.0.1", port), LikeSaverHandler)
    t = threading.Thread(target=srv.serve_forever, name="LikeSaver", daemon=True)
    t.start()
    log(f"[LikeSaver] 监听 http://127.0.0.1:{port}/save → {base}")
    notifier.notify("点赞保存器已启动", f"127.0.0.1:{port}")


# ============ CLI ============
def build_parser() -> 'argparse.ArgumentParser':
    import argparse
    p = argparse.ArgumentParser(description="投放即编号 + 点赞保存（后台常驻 + Windows 通知）")
    p.add_argument("--base", type=str, default=DEFAULT_BASE, help="目标路径")
    p.add_argument("--watch", action="store_true", default=WATCH, help="持续监听模式（默认开）")
    p.add_argument("--once", action="store_true", help="只处理当前待办后退出")
    p.add_argument("--preview", action="store_true", default=PREVIEW, help="预览模式（不落盘）")
    p.add_argument("--no-preview", dest="preview", action="store_false", help="关闭预览，执行改名/移动")

    p.add_argument("--assign", type=str, default=ASSIGN_MODE, choices=["append", "fill"], help="编号策略")
    p.add_argument("--file-sort", type=str, default=FILE_SORT_MODE, choices=["name", "mtime", "exif"], help="图片排序")
    p.add_argument("--conflict-dirs", type=str, default=CONFLICT_DIRS, choices=["skip", "dedup"], help="目录冲突策略")
    p.add_argument("--conflict-files", type=str, default=CONFLICT_FILES, choices=["skip", "dedup"], help="文件冲突策略")
    p.add_argument("--interval", type=float, default=SCAN_INTERVAL, help="监听扫描间隔秒")
    p.add_argument("--stability", type=int, default=STABILITY_CHECKS, help="稳定性检查次数")
    p.add_argument("--report-csv", type=str, default=REPORT_CSV, help="映射报告 CSV（留空=不生成）")

    # 通知
    p.add_argument("--notify-backend", type=str, default=DEFAULT_NOTIFY_BACKEND,
                   choices=["auto", "winsdk", "win10toast", "burnttoast", "none"],
                   help="通知后端选择（默认 auto）")
    p.add_argument("--notify-test", action="store_true", help="启动时立即弹一条测试通知")

    # Like-Saver
    p.add_argument("--like-saver", action="store_true", default=LIKE_SAVER_ENABLED, help="启用点赞保存器（默认开）")
    p.add_argument("--no-like-saver", dest="like_saver", action="store_false", help="禁用点赞保存器")
    p.add_argument("--like-port", type=int, default=LIKE_SAVER_PORT, help="点赞保存器端口（默认 38999）")

    return p


def main():
    args = build_parser().parse_args()
    base = Path(args.base)

    global notifier
    notifier = Notifier(prefer=args.notify_backend)

    if args.notify_test:
        notifier.notify("脚本已启动", f"监听：{base}")
        time.sleep(0.2)

    # 覆盖间隔和稳定性参数
    global SCAN_INTERVAL, STABILITY_CHECKS
    SCAN_INTERVAL = args.interval
    STABILITY_CHECKS = args.stability

    # 启动 Like-Saver（先于 watch_loop）
    if args.like_saver:
        start_like_saver(args.like_port, base)

    if args.once:
        process_once(base, args.assign, args.preview, args.file_sort,
                     args.conflict_dirs, args.conflict_files, args.report_csv)
    else:
        watch_loop(base, args.assign, args.preview, args.file_sort,
                   args.conflict_dirs, args.conflict_files, args.report_csv)


if __name__ == "__main__":
    main()
