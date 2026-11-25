"""验证 GCJ 修正后：单条轨迹在高德底图上是否贴合道路。"""
import sys
from pathlib import Path

ROOT = Path(r"D:\py\private_bike")
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap

app = QApplication(sys.argv)

from bike.db import RideDB
from bike.mapview import MapCanvas

db = RideDB(str(ROOT / "data" / "bike.db"))
ride = None
for r in db.list_rides():
    if (r.get("start_time") or "").startswith("2026-11-18") and "下午" in (r.get("title") or ""):
        ride = r
        break
if ride is None:
    ride = db.list_rides()[0]
print("ride:", ride["id"], ride.get("title"))

samples = db.get_samples(ride["id"])
cv = MapCanvas()
cv.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
cv.resize(1000, 640)
cv.show()
cv.set_track(samples, ride.get("title") or "")

loop = QEventLoop()
QTimer.singleShot(12000, loop.quit)
loop.exec()
out = ROOT / "data" / "_map_fixed.png"
cv.grab().save(str(out))
print("zoom", cv._zoom, "saved", out)
cv.close()
