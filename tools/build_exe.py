"""一键打包：PyInstaller 构建 → 瘦身 → 拷入运行数据 → 写使用说明。

用法：python tools/build_exe.py
产物：dist/私人骑行数据/私人骑行数据.exe（整个文件夹可直接分发）
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "私人骑行数据"
INTERNAL = DIST / "_internal"
QT = INTERNAL / "PyQt6" / "Qt6"
NAME = "私人骑行数据"

UNUSED_QT_DLLS = [
    "Qt6Quick3DRuntimeRender.dll", "Qt6Quick3DPhysics.dll", "Qt6Quick3DUtils.dll",
    "Qt6Quick3DAssetImport.dll", "Qt6Quick3DAssetUtils.dll", "Qt6Quick3DEffects.dll",
    "Qt6Quick3DHelpers.dll", "Qt6ShaderTools.dll", "Qt6QuickControls2FluentWinUI3.dll",
    "Qt6QuickControls2Imagine.dll", "Qt6QuickControls2Material.dll",
    "Qt6QuickControls2Universal.dll",
]
UNUSED_RESOURCES = [
    "qtwebengine_devtools_resources.debug.pak", "qtwebengine_resources.debug.pak",
    "qtwebengine_resources_200p.debug.pak", "qtwebengine_resources_100p.debug.pak",
    "v8_context_snapshot.debug.bin",
]


def build():
    icon = ROOT / "assets" / "app.ico"
    if not icon.exists():
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py")], check=True)
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NAME, "--icon", str(icon),
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--hidden-import", "PyQt6.QtWebEngineCore",
        "--exclude-module", "tkinter", "--exclude-module", "transformers",
        "--exclude-module", "torch", "--exclude-module", "matplotlib",
        "--exclude-module", "modelscope",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
        str(ROOT / "main.py"),
    ]
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def _rm(p: Path):
    if p.exists():
        p.unlink()


def slim():
    for name in UNUSED_RESOURCES:
        _rm(QT / "resources" / name)
    loc = QT / "translations" / "qtwebengine_locales"
    if loc.exists():
        for f in loc.iterdir():
            if f.is_file() and f.stem not in ("zh-CN", "en-US"):
                _rm(f)
    tr = QT / "translations"
    if tr.exists():
        for f in tr.iterdir():
            if f.is_file() and "zh_CN" not in f.name:
                _rm(f)
    for name in UNUSED_QT_DLLS:
        _rm(QT / "bin" / name)


def copy_data():
    dd = DIST / "data"
    dd.mkdir(exist_ok=True)
    for name in ("bike.db", "xingzhe_cookies.json"):
        p = ROOT / "data" / name
        if p.exists():
            shutil.copy2(p, dd / name)


def notice():
    src = ROOT / "packaging" / "使用说明.txt"
    if src.exists():
        shutil.copy2(src, DIST / "使用说明.txt")


def main():
    build()
    slim()
    copy_data()
    notice()
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1048576
    print("打包完成：%s（%.0f MB）" % (DIST, total))


if __name__ == "__main__":
    main()
