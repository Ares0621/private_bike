"""打印最佳/里程碑数据 + 截窗口图。"""
import sys
from pathlib import Path

ROOT = Path(r"D:\py\private_bike")
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from bike.db import RideDB
from bike import records as rec

db = RideDB(str(ROOT / "data" / "bike.db"))
data = rec.compute(db)
print("totals:", data["totals"], "streak:", data["streak"])
for b in data["bests"]:
    print("  %-10s %8.1f %-6s %s %s" % (b["label"], b["value"], b["sub"], b["date"], b["title"]))
print("badges:")
for g in data["badges"]:
    print("  %-10s cur=%.1f next=%s got=%d/%d  %s"
          % (g["name"], float(g["current"]), g["next"], len(g["achieved"]), len(g["tiers"]),
             [(t, d.isoformat()) for t, d in g["achieved"]]))

from bike.records_ui import RecordsDialog
from bike.theme import QSS
app.setStyleSheet(QSS)
dlg = RecordsDialog(db)
dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
dlg.resize(1140, 920)
dlg.show()
loop = QEventLoop()
QTimer.singleShot(1500, loop.quit)
loop.exec()
dlg.grab().save(str(ROOT / "data" / "_records.png"))
print("saved _records.png")
dlg.close()

