"""用正式库 data/bike.db 截一张单条详情图（只读，不导入）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication

from bike.mainwindow import MainWindow
from bike.theme import QSS


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


app = QApplication(sys.argv)
app.setStyleSheet(QSS)
win = MainWindow()
win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
win.resize(1460, 940)
win.show()
wait(16000)
win.grab().save(str(ROOT / "data" / "_real.png"))
print("rides:", win.list.count(), "stack:", win.stack.currentIndex())
win.close()
app.quit()
