"""生成 assets/app.ico（用程序内主题图标，256/64/48/32/16 多尺寸）。"""
import sys
from pathlib import Path

ROOT = Path(r"D:\py\private_bike")
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
from bike.theme import make_app_icon

pm = make_app_icon().pixmap(256, 256)
out_dir = ROOT / "assets"
out_dir.mkdir(exist_ok=True)
png = out_dir / "app_256.png"
pm.save(str(png))

from PIL import Image
im = Image.open(png).convert("RGBA")
ico = out_dir / "app.ico"
im.save(ico, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon:", ico, ico.stat().st_size)
png.unlink()
