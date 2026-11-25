"""月度统计窗口：汇总卡片 + 月度里程柱状图 + 月度明细表 + CSV 导出。"""
import csv
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QGridLayout,
                             QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout)

from .charts import MonthlyBarChart, fmt_duration
from .widgets import StatCard

COLUMNS = ("月份", "次数", "里程 (km)", "骑行时长", "爬升 (m)", "均速 (km/h)", "均心率")


class MonthlyStatsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("月度统计 · PrivateBike")
        self.resize(1060, 760)
        self._rows: list[dict] = []
        self._build()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("月度统计")
        title.setObjectName("RideTitle")
        head.addWidget(title)
        head.addSpacing(12)
        self.cmb_year = QComboBox()
        self.cmb_year.setFixedWidth(130)
        self.cmb_year.currentIndexChanged.connect(lambda _: self.refresh())
        head.addWidget(self.cmb_year)
        head.addStretch(1)
        self.btn_export = QPushButton("导出 CSV")
        self.btn_export.clicked.connect(self.export_csv)
        head.addWidget(self.btn_export)
        root.addLayout(head)

        cards = QGridLayout()
        cards.setSpacing(8)
        self.cards = {}
        for i, (key, label) in enumerate([
            ("dist", "总里程"), ("rides", "骑行次数"), ("time", "总骑行时长"),
            ("elev", "总爬升"), ("avg", "月均里程"), ("longest", "最长单次"),
        ]):
            card = StatCard(label)
            cards.addWidget(card, 0, i)
            self.cards[key] = card
        root.addLayout(cards)

        chart_wrap = QHBoxLayout()
        sec = QLabel("月度里程")
        sec.setObjectName("SectionTitle")
        chart_wrap.addWidget(sec)
        chart_wrap.addStretch(1)
        root.addLayout(chart_wrap)

        self.chart = MonthlyBarChart()
        root.addWidget(self.chart, 3)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 4)

    # ---------------------------------------------------------- 数据
    def refresh(self):
        # 年份下拉
        years = self.db.years()
        current = self.cmb_year.currentText()
        self.cmb_year.blockSignals(True)
        self.cmb_year.clear()
        self.cmb_year.addItem("全部年份")
        self.cmb_year.addItems(years)
        if current and current in ["全部年份"] + years:
            self.cmb_year.setCurrentText(current)
        self.cmb_year.blockSignals(False)

        year = None if self.cmb_year.currentIndex() <= 0 else self.cmb_year.currentText()
        rows = self.db.stats_by_month(year)
        self._rows = rows
        self._fill_cards(rows)
        self.chart.set_data([
            {"label": r["ym"] if year is None else r["ym"][5:] + "月",
             "value": (r["dist"] or 0) / 1000.0}
            for r in rows
        ])
        self._fill_table(rows)

    def _fill_cards(self, rows):
        dist = sum((r["dist"] or 0) for r in rows)
        rides = sum((r["rides"] or 0) for r in rows)
        moving = sum((r["moving"] or 0) for r in rows)
        elev = sum((r["elev"] or 0) for r in rows)
        longest = max([(r["longest"] or 0) for r in rows] or [0])
        n = len(rows) or 1

        self.cards["dist"].set(f"{dist / 1000:.0f} km", f"{len(rows)} 个月有记录")
        self.cards["rides"].set(f"{rides} 次", f"平均 {rides / n:.1f} 次/月" if rows else "")
        self.cards["time"].set(fmt_duration(moving), "仅计 >5 km/h 的时段" if rows else "")
        self.cards["elev"].set(f"{elev:.0f} m", "")
        self.cards["avg"].set(f"{dist / 1000 / n:.0f} km", "月均里程" if rows else "")
        self.cards["longest"].set(f"{longest / 1000:.1f} km", "单次最长" if rows else "")

    def _fill_table(self, rows):
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows) + (1 if rows else 0))
        for i, r in enumerate(rows):
            values = [
                r["ym"],
                str(r["rides"] or 0),
                f"{(r['dist'] or 0) / 1000:.1f}",
                fmt_duration(r["moving"] or 0),
                f"{(r['elev'] or 0):.0f}",
                f"{((r['avg_speed'] or 0) * 3.6):.1f}",
                f"{(r['avg_hr'] or 0):.0f}" if r["avg_hr"] else "--",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                                      if j else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(i, j, item)
        if rows:
            total_row = len(rows)
            total = [
                "合计",
                str(sum(r["rides"] or 0 for r in rows)),
                f"{sum((r['dist'] or 0) for r in rows) / 1000:.1f}",
                fmt_duration(sum(r["moving"] or 0 for r in rows)),
                f"{sum((r['elev'] or 0) for r in rows):.0f}",
                "",
                "",
            ]
            for j, v in enumerate(total):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                                      if j else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                self.table.setItem(total_row, j, item)

    # ---------------------------------------------------------- 导出
    def export_csv(self):
        if not self._rows:
            QMessageBox.information(self, "导出", "当前没有可导出的数据")
            return
        default = os.path.join(os.path.expanduser("~"), "骑行月度统计.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出月度统计", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(COLUMNS)
                for r in self._rows:
                    w.writerow([
                        r["ym"], r["rides"] or 0,
                        f"{(r['dist'] or 0) / 1000:.2f}",
                        fmt_duration(r["moving"] or 0),
                        f"{(r['elev'] or 0):.0f}",
                        f"{((r['avg_speed'] or 0) * 3.6):.1f}",
                        f"{(r['avg_hr'] or 0):.0f}" if r["avg_hr"] else "",
                    ])
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"已保存到：\n{path}")
