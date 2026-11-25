"""截图验证：主窗口 + 行者同步对话框（用正式库，只读不改数据）。"""
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

from bike.mainwindow import MainWindow  # noqa: E402
from bike.xingzhe_ui import XingzheSyncDialog  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


win = MainWindow()
win.resize(1460, 940)
win.show()
wait(14000)   # 等瓦片下载
win.grab().save(os.path.join(ROOT, "data", "_xz_main.png"))
print("main shot ok, rides:", win.db.count())

dlg = XingzheSyncDialog(win.db, win)
dlg.resize(660, 520)
dlg.show()
wait(1200)
dlg.grab().save(os.path.join(ROOT, "data", "_xz_dialog.png"))
print("dialog shot ok")

dlg.close()
win.close()
print("done")
