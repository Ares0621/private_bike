"""功能检查：导入多个月记录 → 叠加对比截图 → 月度统计窗口截图。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["PB_DB"] = str(ROOT / "data" / "_feature.db")

from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication

from bike.mainwindow import MainWindow
from bike.parsers import load_ride
from bike.theme import QSS


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
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

    files = [str(ROOT / "sample" / "demo_ride.gpx")]
    files += sorted(str(p) for p in (ROOT / "sample" / "demo_rides").glob("*.gpx"))
    for f in files:
        ride = load_ride(f)
        if not win.db.exists(ride.fingerprint):
            win.db.add_ride(ride)
    win.refresh_list()
    print("rides:", win.db.count())
    print("years:", win.db.years())
    print("monthly:", [(r["ym"], r["rides"], round((r["dist"] or 0) / 1000, 1))
                       for r in win.db.stats_by_month()])

    win.list.blockSignals(True)
    win.list.clearSelection()
    for i in range(min(3, win.list.count())):
        win.list.item(i).setSelected(True)
    win.list.blockSignals(False)
    win._selected_ids = []
    win._on_selection_changed()
    print("stack:", win.stack.currentIndex(), "compare rows:", win.cmp_table.rowCount())

    wait(16000)
    win.grab().save(str(ROOT / "data" / "_compare.png"))

    win.show_monthly()
    win.monthly_dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.monthly_dialog.resize(1060, 760)
    win.monthly_dialog.show()
    wait(2500)
    win.monthly_dialog.grab().save(str(ROOT / "data" / "_monthly.png"))
    print("monthly rows:", win.monthly_dialog.table.rowCount())

    win.close()
    app.quit()


if __name__ == "__main__":
    main()
