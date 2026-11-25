"""热力图自检：一次渲染「全部 / 年度 / 月度」三种范围，另可导出窗口截图。

用法：
    python tools/shot_heatmap.py                # 只出图到 data/heat_samples/
    python tools/shot_heatmap.py --ui           # 额外把热力图窗口截一张 data/_heat_ui.png
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

from bike import heatmap  # noqa: E402
from bike.db import RideDB  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "heat_samples")


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", action="store_true", help="同时截一张热力图窗口")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    db = RideDB()

    years = sorted((str(y) for y in (db.years() or [])), reverse=True)
    if not years:
        print("数据库里还没有记录", flush=True)
        return
    year = years[0]
    months = [int((r.get("start_time") or "")[5:7]) for r in db.list_rides()
              if (r.get("start_time") or "")[:4] == year and (r.get("start_time") or "")[5:7].isdigit()]
    month = max(months) if months else 1
    spec_all = heatmap.HeatSpec(mode="all", target_px=2000)
    spec_year = heatmap.HeatSpec(mode="year", year=year, target_px=2000)
    spec_month = heatmap.HeatSpec(mode="month", year=year, month=month, target_px=2000)
    specs = [("all", spec_all), ("year", spec_year), ("month", spec_month)]
    for name, spec in specs:
        res = heatmap.render(db, spec)
        path = os.path.join(OUT, f"heat_{name}.png")
        ok = res.image.save(path, "PNG")
        print(name, res.stats, "saved", ok, flush=True)

    if args.ui:
        from bike.theme import QSS
        from bike.mainwindow import MainWindow
        app.setStyleSheet(QSS)
        win = MainWindow()
        win.resize(1460, 940)
        win.show()
        wait(1500)
        win.show_heatmap()
        dlg = win.heatmap_dialog
        dlg.generate()
        for _ in range(60):
            wait(1000)
            if dlg.result is not None:
                break
        dlg.grab().save(os.path.join(ROOT, "data", "_heat_ui.png"), "PNG")
        print("ui shot saved", flush=True)
        dlg.close()
        win.close()

    db.close()
    app.quit()


if __name__ == "__main__":
    main()
