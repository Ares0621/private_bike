"""截取单条骑行详情页（回归检查）。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PB_DB"] = str(ROOT / "data" / "_single.db")

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication

from bike.mainwindow import MainWindow
from bike.parsers import load_ride
from bike.theme import QSS


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


db_file = Path(os.environ["PB_DB"])
for suf in ("", "-wal", "-shm"):
    p = Path(str(db_file) + suf)
    if p.exists():
        p.unlink()

app = QApplication(sys.argv)
app.setStyleSheet(QSS)

win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.resize(1460, 940)
win.show()

for f in [str(ROOT / "sample" / "demo_ride.gpx")]:
    ride = load_ride(f)
    if not win.db.exists(ride.fingerprint):
        win.db.add_ride(ride)
win.refresh_list()
wait(16000)
win.grab().save(str(ROOT / "data" / "_single.png"))
print("stack:", win.stack.currentIndex(), "rows:", win.list.count())
win.close()
app.quit()
