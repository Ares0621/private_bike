"""截图验证：行者同步对话框的时间范围（默认最近 30 天 / 自定义）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from bike.theme import QSS  # noqa: E402
app.setStyleSheet(QSS)

from bike.db import RideDB  # noqa: E402
from bike.xingzhe_ui import XingzheSyncDialog  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


db = RideDB()
dlg = XingzheSyncDialog(db)
dlg.resize(700, 560)
dlg.show()
wait(900)
dlg.grab().save(os.path.join(ROOT, "data", "_xz_range.png"))
print("30d shot ok ->", dlg.lbl_range.text())

idx = dlg.cmb_range.findData("custom")
dlg.cmb_range.setCurrentIndex(idx)
wait(500)
dlg.grab().save(os.path.join(ROOT, "data", "_xz_range_custom.png"))
print("custom shot ok ->", dlg.lbl_range.text(), "| start enabled:", dlg.dt_start.isEnabled())
print("range:", dlg.current_range())

dlg.close()
print("done")
