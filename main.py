"""程序入口：python main.py（打包后为 exe 启动）。"""
import os
import sys

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from bike.config import APP_NAME, DATA_DIR, ROOT, ensure_dirs
from bike.theme import QSS, make_app_icon


def _icon() -> QIcon:
    ico = ROOT / "assets" / "app.ico"
    if ico.exists():
        return QIcon(str(ico))
    return make_app_icon()


def main():
    ensure_dirs()
    # 内置网页登录窗口（QtWebEngine）要求，必须在创建 QApplication 之前设置
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName("私人骑行数据")
    app.setWindowIcon(_icon())
    app.setStyleSheet(QSS)

    from bike.mainwindow import MainWindow  # 延迟导入，保证 QApplication 先创建

    win = MainWindow()
    win.show()

    # 打包自检：PB_SELFCHECK=1 时离屏跑一遍并截图后自动退出（用来验证 exe 没缺依赖）
    if os.environ.get("PB_SELFCHECK"):
        from PyQt6.QtCore import QTimer
        win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        out = DATA_DIR / "_exe_check.png"
        log = DATA_DIR / "_exe_check.txt"

        def _shot():
            web_ok = False
            err = ""
            try:
                from PyQt6.QtWebEngineWidgets import QWebEngineView
                view = QWebEngineView()
                view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
                view.resize(400, 300)
                view.setHtml("<p>WebEngine ok</p>")
                view.grab()
                view.deleteLater()
                web_ok = True
            except Exception as exc:  # noqa: BLE001
                err = repr(exc)
            win.resize(1460, 940)
            win.grab().save(str(out))
            log.write_text(f"rides={win.list.count()} webengine={web_ok} err={err}\n",
                           encoding="utf-8")
            app.quit()

        QTimer.singleShot(9000, _shot)
        app.exec()
        return

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
