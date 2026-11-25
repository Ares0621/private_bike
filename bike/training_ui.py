"""训练计划窗口：选目标 / 周次数 / 计划周期 → 按历史数据生成周课表，可导出。"""
import os
from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame,
                             QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from . import training
from .charts import MonthlyBarChart
from .config import DATA_DIR
from .theme import QSS
from .widgets import StatCard

COLUMNS = ("周次", "日期", "课程", "时长", "目标距离", "强度区间", "怎么骑")

GOAL_ITEMS = (
    ("按数据自动安排", "auto"),
    ("提升耐力 / 长距离", "endurance"),
    ("提升速度 / 爬坡", "speed"),
    ("规律骑行 / 减脂", "health"),
)

WINDOW_ITEMS = (("近 30 天", 30), ("近 90 天", 90), ("近 180 天", 180), ("全部记录", 365))


class TrainingPlanDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.plan = None

        self.setWindowTitle("训练计划")
        self.resize(1080, 780)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("训练任务")
        title.setObjectName("RideTitle")
        head.addWidget(title)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("Dim")
        head.addSpacing(10)
        head.addWidget(self.lbl_summary, 1)
        root.addLayout(head)

        # ---------------- 参数行 ----------------
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(QLabel("数据范围"))
        self.cmb_window = QComboBox()
        for label, days in WINDOW_ITEMS:
            self.cmb_window.addItem(label, days)
        self.cmb_window.setCurrentIndex(1)
        self.cmb_window.setFixedWidth(110)
        bar.addWidget(self.cmb_window)

        bar.addSpacing(6)
        bar.addWidget(QLabel("训练目标"))
        self.cmb_goal = QComboBox()
        for label, key in GOAL_ITEMS:
            self.cmb_goal.addItem(label, key)
        self.cmb_goal.setFixedWidth(160)
        bar.addWidget(self.cmb_goal)

        bar.addSpacing(6)
        bar.addWidget(QLabel("每周次数"))
        self.cmb_per_week = QComboBox()
        for n in (2, 3, 4, 5):
            self.cmb_per_week.addItem(f"每周 {n} 次", n)
        self.cmb_per_week.setCurrentIndex(1)
        self.cmb_per_week.setFixedWidth(110)
        bar.addWidget(self.cmb_per_week)

        bar.addWidget(QLabel("计划周期"))
        self.cmb_weeks = QComboBox()
        for n in (4, 6, 8):
            self.cmb_weeks.addItem(f"{n} 周", n)
        self.cmb_weeks.setFixedWidth(90)
        bar.addWidget(self.cmb_weeks)

        bar.addStretch(1)
        self.btn_gen = QPushButton("重新生成")
        self.btn_gen.clicked.connect(self.regenerate)
        bar.addWidget(self.btn_gen)
        root.addLayout(bar)

        # ---------------- 主体 ----------------
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        left = QFrame()
        left.setObjectName("Panel")
        left.setMinimumWidth(320)
        left.setMaximumWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(10)

        cap = QLabel("能力画像")
        cap.setObjectName("SectionTitle")
        ll.addWidget(cap)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.cards = {}
        for i, (key, label) in enumerate([
            ("km_week", "周骑量"), ("freq", "每周次数"), ("base", "均速基准"),
            ("typical", "典型单次"), ("longest", "最长单次"), ("climb", "爬坡密度"),
        ]):
            card = StatCard(label)
            grid.addWidget(card, i // 2, i % 2)
            self.cards[key] = card
        ll.addLayout(grid)

        cap2 = QLabel("诊断")
        cap2.setObjectName("SectionTitle")
        ll.addWidget(cap2)
        self.lbl_notes = QLabel("")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setObjectName("Dim")
        self.lbl_notes.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        ll.addWidget(self.lbl_notes, 1)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 0, 0, 0)
        rl.setSpacing(8)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True)
        rl.addWidget(self.table, 1)

        chart_cap = QLabel("每周计划里程")
        chart_cap.setObjectName("SectionTitle")
        rl.addWidget(chart_cap)
        self.chart = MonthlyBarChart()
        self.chart.setMinimumHeight(150)
        self.chart.setMaximumHeight(200)
        rl.addWidget(self.chart)
        split.addWidget(right)
        split.setSizes([360, 700])
        root.addWidget(split, 1)

        # ---------------- 底部 ----------------
        foot = QHBoxLayout()
        self.lbl_hint = QLabel("提示：强度用「目标均速区间 + 说话测试」控制；改目标或周次数会立即重算。")
        self.lbl_hint.setObjectName("Dim")
        foot.addWidget(self.lbl_hint, 1)
        self.btn_md = QPushButton("导出 Markdown")
        self.btn_md.clicked.connect(lambda: self.export("md"))
        self.btn_csv = QPushButton("导出 CSV")
        self.btn_csv.clicked.connect(lambda: self.export("csv"))
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        foot.addWidget(self.btn_md)
        foot.addWidget(self.btn_csv)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)

        for w in (self.cmb_window, self.cmb_goal, self.cmb_per_week, self.cmb_weeks):
            w.currentIndexChanged.connect(self.regenerate)

    # ------------------------------------------------------ 生成
    def regenerate(self):
        try:
            prof = training.build_profile(self.db, self.cmb_window.currentData())
            self.plan = training.build_plan(
                prof,
                weeks=self.cmb_weeks.currentData(),
                per_week=self.cmb_per_week.currentData(),
                goal=self.cmb_goal.currentData(),
            )
        except Exception as exc:  # noqa: BLE001
            self.lbl_summary.setText(f"生成失败：{exc}")
            self.table.setRowCount(0)
            return
        self._fill(prof)

    def _fill(self, prof):
        plan = self.plan
        total_km = sum(plan["week_km"].values())
        goal_text = plan["goal_label"]
        if self.cmb_goal.currentData() == "auto":
            goal_text = f"自动安排 → {goal_text}"
        self.lbl_summary.setText(
            f"{goal_text} · {plan['weeks']} 周 · 每周 {plan['per_week']} 次 · "
            f"合计约 {total_km:.0f} km · 从 {plan['start'].strftime('%Y-%m-%d')} 开始")

        self.cards["km_week"].set(f"{prof.km_per_week:g} km", f"近 {prof.window_days} 天周均")
        self.cards["freq"].set(f"{prof.rides_per_week:g} 次", f"近 {prof.window_days} 天")
        self.cards["base"].set(f"{prof.base_speed:g} km/h", f"{prof.speed_p25:g}~{prof.speed_p75:g} 区间")
        self.cards["typical"].set(f"{prof.typical_min:.0f} 分钟", f"约 {prof.typical_km:g} km")
        self.cards["longest"].set(f"{prof.longest_km:g} km", "历史最长单次")
        self.cards["climb"].set(f"{prof.elev_per_km:g} m/km", "平路为主" if prof.elev_per_km < 4 else "有起伏")

        self.lbl_notes.setText("<br>".join(
            f"<div style='margin-bottom:8px'>• {n}</div>" for n in prof.notes))

        rows = plan["sessions"]
        self.table.setRowCount(len(rows))
        for i, s in enumerate(rows):
            structure = s.structure.replace(" → ", "\n→ ")
            values = (f"第 {s.week} 周", training.session_date(plan, s), s.title,
                      f"{s.duration_min} 分钟", f"{s.distance_km:g} km", s.zone, structure)
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                if j == 2:
                    item.setForeground(Qt.GlobalColor.white)
                if j in (3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                elif j == 6:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.table.setItem(i, j, item)
        self.table.resizeRowsToContents()

        self.chart.set_data([{"label": f"第{w}周", "value": plan["week_km"].get(w, 0)}
                             for w in range(1, plan["weeks"] + 1)])

    # ------------------------------------------------------ 导出
    def export(self, kind: str):
        if not self.plan:
            return
        stamp = date.today().strftime("%Y%m%d")
        default = os.path.join(str(DATA_DIR), f"训练计划_{stamp}.{kind}")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出训练计划", default,
            "Markdown (*.md)" if kind == "md" else "CSV (*.csv)")
        if not path:
            return
        text = training.plan_to_markdown(self.plan) if kind == "md" else training.plan_to_csv(self.plan)
        try:
            with open(path, "w", encoding="utf-8-sig" if kind == "csv" else "utf-8") as f:
                f.write(text)
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self.lbl_hint.setText(f"已导出：{path}")

    def refresh(self):
        self.regenerate()
