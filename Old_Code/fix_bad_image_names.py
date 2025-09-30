# -*- coding: utf-8 -*-
"""
修复历史错误导致的图片命名 + 文件夹自动补编号
规则：
- 目录名：若已有编号（00001_Name），保持不动；若无编号，自动补编号（递增）
- 目录内图片：已规范的文件（{folder.name}_NNN.ext）保持不动
- 非规范的文件，按“当前已存在的最大 NNN”往后递增编号改名
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Optional

# ========== 默认配置 ==========
DEFAULT_BASE = r"C:\Users\Solarigin\Pictures\X"
DEFAULT_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"}

# ========== 工具 ==========
def log(msg: str):
    print(msg)

def ensure_list_subfolders(base: Path, recursive: bool = False) -> List[Path]:
    res: List[Path] = []
    if recursive:
        for p in base.rglob("*"):
            if p.is_dir():
                res.append(p)
    else:
        with os.scandir(base) as it:
            for e in it:
                if e.is_dir():
                    res.append(Path(e.path))
    return res

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
    mode = (mode or "name").lower()
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

# ========== 新增：规范化文件夹名 ==========
def normalize_folder_names(base: Path, preview: bool = False) -> None:
    """为没有编号的文件夹补编号"""
    folders = sorted([p for p in base.iterdir() if p.is_dir()], key=lambda x: x.name.lower())
    pat = re.compile(r"^(\d{5})_(.+)$")

    # 找到已有最大编号
    max_idx = 0
    for f in folders:
        m = pat.match(f.name)
        if m:
            max_idx = max(max_idx, int(m.group(1)))

    # 给未编号的补编号
    for f in folders:
        if not pat.match(f.name):
            max_idx += 1
            new_name = f"{max_idx:05d}_{f.name}"
            dst = f.parent / new_name
            if preview:
                log(f"[预览] 文件夹重命名: {f.name} -> {new_name}")
            else:
                os.rename(f, dst)
                log(f"📂 文件夹已重命名: {f.name} -> {new_name}")

# ========== 核心：规范化单个目录 ==========
def normalize_folder(folder: Path, image_exts: set, width: int, sort_mode: str, preview: bool) -> Tuple[int, int]:
    imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in image_exts]
    if not imgs:
        return (0, 0)

    pat = re.compile(rf'^{re.escape(folder.name)}_(\d{{{width}}})$', re.IGNORECASE)

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
        return (len(conforming), 0)

    max_idx = max([idx for _, idx in conforming], default=0)
    nonconforming = sort_images(nonconforming, sort_mode)

    changed = 0
    for src in nonconforming:
        while True:
            max_idx += 1
            dst = folder / f"{folder.name}_{max_idx:0{width}d}{src.suffix.lower()}"
            if not dst.exists():
                break
        if preview:
            log(f"[预览] {src.name} -> {dst.name}")
        else:
            os.rename(src, dst)
            log(f"[已改名] {src.name} -> {dst.name}")
        changed += 1

    return (len(conforming), changed)

# ========== CLI ==========
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="修复历史图片命名（保持文件夹编号与已存在编号不变）")
    p.add_argument("--base", type=str, default=DEFAULT_BASE, help="根目录（包含多个已编号文件夹）")
    p.add_argument("--width", type=int, default=3, help="图片编号位数（默认 3 → _001）")
    p.add_argument("--sort", type=str, default="name", choices=["name", "mtime", "exif"], help="给新编号的图片确定顺序")
    p.add_argument("--recursive", action="store_true", help="递归处理所有子目录（默认只处理一层子目录）")
    p.add_argument("--ext", type=str, default=",".join(sorted(DEFAULT_IMAGE_EXTS)), help="图片后缀，逗号分隔（默认常见格式）")
    p.add_argument("--preview", action="store_true", help="预览模式（只打印计划，不落盘）")
    return p

def main():
    args = build_parser().parse_args()
    base = Path(args.base)
    if not base.exists():
        log(f"❌ 路径不存在：{base}")
        return

    # 先规范化文件夹名
    normalize_folder_names(base, preview=args.preview)

    image_exts = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                  for e in args.ext.split(",") if e.strip()}

    folders = ensure_list_subfolders(base, recursive=args.recursive)
    if not folders:
        log("⚠️ 未发现子目录（可用 --recursive 递归处理）")
        return

    total_conforming = 0
    total_changed = 0
    handled = 0

    for folder in folders:
        imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in image_exts]
        if not imgs:
            continue

        handled += 1
        log(f"\n📁 处理目录：{folder}")
        c, ch = normalize_folder(folder, image_exts, args.width, args.sort, args.preview)
        total_conforming += c
        total_changed += ch

        if ch == 0:
            log("✅ 无需修改（均已规范）")
        else:
            log(f"✅ 完成：调整 {ch} 个（已规范 {c} 个保留）")

    if handled == 0:
        log("ℹ️ 没有找到包含图片的子目录。")
    else:
        if args.preview:
            log(f"\n🔍 预览结束：目录 {handled} 个，已规范 {total_conforming}，计划调整 {total_changed}。")
        else:
            log(f"\n🎉 完成：目录 {handled} 个，已规范 {total_conforming}，实际调整 {total_changed}。")

if __name__ == "__main__":
    main()
