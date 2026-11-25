"""个人最佳与里程碑窗口：顶部累计卡片 + 单项纪录表 + 阶梯成就墙。"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QFrame, QGridLayout, QSplitter,
                             QHBoxLayout, QHeaderView, QLabel, QProgressBar,
                             QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from . import records as rec
from .theme import QSS
from .widgets import StatCard


class BadgeCard(QFrame):
    """一个里程碑族：名称 + 当前值 + 到下一档的进度 + 已解锁的各档日期。"""

    def __init__(self, data: dict):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(4)

        unit = data["unit"]
        tiers = data["tiers"]
        achieved = data["achieved"]

        head = QHBoxLayout()
        head.setSpacing(6)
        name = QLabel(data["name"])
        name.setObjectName("CardTitle")
        val = QLabel()
        val.setStyleSheet("color:#eaf1f8;font-size:15px;font-weight:600;background:transparent;")
        val.setText(f"{rec._fmt(data['current'], unit)} {unit}")
        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(val)
        lay.addLayout(head)

        got = QLabel(f"已解锁 {len(achieved)}/{len(tiers)} 档")
        got.setObjectName("CardSub")
        lay.addWidget(got)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setValue(int(max(0.0, min(1.0, data["ratio"])) * 100))
        lay.addWidget(bar)

        if data["next"] is not None:
            gap = data["next"] - data["current"]
            nxt = QLabel(f"下一档 {rec._fmt(data['next'], unit)} {unit} · 还差 "
                         f"{rec._fmt(gap, unit)} {unit}")
            nxt.setObjectName("CardSub")
            lay.addWidget(nxt)
        else:
            done = QLabel("全部阶梯已解锁 🎉")
            done.setStyleSheet("color:#7fd18f;background:transparent;font-size:10px;")
            lay.addWidget(done)

        if achieved:
            chips = " · ".join(f"{rec._fmt(t, unit)} ✓ {d.strftime('%y-%m-%d')}"
                               for t, d in achieved)
            c = QLabel(f"<span style='color:#7f8794'>{chips}</span>")
            c.setTextFormat(Qt.TextFormat.RichText)
            c.setWordWrap(True)
            c.setStyleSheet("background:transparent;font-size:10px;")
            lay.addWidget(c)


class RecordsDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("个人最佳与里程碑")
        self.resize(1140, 920)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("个人最佳与里程碑")
        title.setObjectName("RideTitle")
        head.addWidget(title)
        hint = QLabel("全部从本地骑行记录现算：纪录看单项极值，成就看累计阶梯与首次达成日期。")
        hint.setObjectName("Dim")
        head.addWidget(hint)
        head.addStretch(1)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.reload)
        head.addWidget(self.btn_refresh)
        root.addLayout(head)

        # 累计卡片
        self.cards_row = QHBoxLayout()
        self.cards_row.setSpacing(8)
        self.cards = {}
        for key, label in (("km", "累计里程"), ("rides", "骑行次数"), ("elev", "累计爬升"),
                           ("moving_h", "有效时长"), ("days", "骑行天数"), ("streak", "最长连续")):
            card = StatCard(label)
            self.cards[key] = card
            self.cards_row.addWidget(card)
        root.addLayout(self.cards_row)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)

        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        # 单项纪录表
        sec1 = QLabel("单项纪录")
        sec1.setObjectName("SectionTitle")
        tl.addWidget(sec1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["项目", "成绩", "日期", "记录"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 110)
        self.table.setMinimumHeight(220)
        tl.addWidget(self.table)
        split.addWidget(top)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 8, 0, 0)
        bl.setSpacing(6)
        # 成就墙
        sec2 = QLabel("里程碑成就")
        sec2.setObjectName("SectionTitle")
        bl.addWidget(sec2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.badge_host = QWidget()
        self.badge_grid = QGridLayout(self.badge_host)
        self.badge_grid.setContentsMargins(0, 0, 6, 6)
        self.badge_grid.setSpacing(8)
        scroll.setWidget(self.badge_host)
        bl.addWidget(scroll, 1)
        split.addWidget(bottom)
        split.setSizes([472, 320])
        root.addWidget(split, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.close)
        foot.addWidget(close)
        root.addLayout(foot)

        self.reload()

    # ------------------------------------------------------------ 载入
    def reload(self):
        data = rec.compute(self.db)
        t = data["totals"]
        self.cards["km"].set(f"{t['km']:,.1f} km",
                             f"{len(t['years'])} 个年度 · {t['rides']} 条记录")
        self.cards["rides"].set(f"{t['rides']}", "条已完成的骑行")
        self.cards["elev"].set(f"{t['elev']:,.0f} m", "累计爬升")
        self.cards["moving_h"].set(f"{t['moving_h']:,.1f} h", ">5 km/h 的有效时长")
        self.cards["days"].set(f"{t['days']}", "有骑行的天数")
        self.cards["streak"].set(f"{data['streak']}", "天 · 最长连续")

        bests = data["bests"]
        self.table.setRowCount(len(bests))
        for i, b in enumerate(bests):
            self.table.setItem(i, 0, QTableWidgetItem(b["label"]))
            v = QTableWidgetItem(f"{rec._fmt(b['value'], b['sub'])} {b['sub']}")
            v.setForeground(QColor("#ff8a6a"))
            self.table.setItem(i, 1, v)
            self.table.setItem(i, 2, QTableWidgetItem(b["date"]))
            self.table.setItem(i, 3, QTableWidgetItem(b["title"]))
        self.table.resizeRowsToContents()
        need = self.table.horizontalHeader().height() + 4 + sum(
            self.table.rowHeight(i) for i in range(self.table.rowCount()))
        self.table.setMaximumHeight(max(180, min(520, need)))

        while self.badge_grid.count():
            item = self.badge_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        cols = 3
        for i, b in enumerate(data["badges"]):
            self.badge_grid.addWidget(BadgeCard(b), i // cols, i % cols)
