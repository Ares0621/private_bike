"""验证内置行者登录窗口能否正常打开（QtWebEngine）。"""
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

from bike.xingzhe_ui import XingzheLoginWindow  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


w = XingzheLoginWindow()
w.resize(880, 760)
w.show()
wait(9000)

info = {}
w.view.page().runJavaScript(
    "(() => document.title + ' | ' + location.href)()",
    lambda r: info.setdefault("page", r))
wait(1500)
print("page:", info.get("page"))
print("cookies collected:", len(w.cookies()), sorted(w.cookies().keys())[:8])
print("label:", w.lbl.text())
w.grab().save(os.path.join(ROOT, "data", "_xz_login.png"))
print("shot saved")
w.close()
print("done")
