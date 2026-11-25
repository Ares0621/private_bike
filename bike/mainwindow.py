"""主窗口：骑行清单（支持多选叠加对比）、地图、单条详情、对比面板。"""
import os

from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox,
                             QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QProgressBar, QPushButton, QSplitter,
                             QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from .charts import CompareChart, RideChart, fmt_duration
from .config import APP_TITLE, COMPARE_COLORS
from .athlete import capability as cap_snapshot
from .athlete_ui import AthleteDialog, show_compare
from .db import RideDB
from .dialogs import MonthlyStatsDialog
from .heatmap_ui import HeatmapDialog
from .records_ui import RecordsDialog
from .mapview import MapCanvas
from .parsers import load_ride
from .theme import QSS, make_app_icon
from .training_ui import TrainingPlanDialog
from .widgets import StatCard
from .xingzhe_ui import XingzheSyncDialog

COMPARE_COLUMNS = ("骑行", "日期", "距离 (km)", "骑行时长", "均速 (km/h)", "爬升 (m)",
                   "均心率", "均踏频", "均功率", "消耗 (kcal)")
MAX_COMPARE = 8


class RideItemWidget(QWidget):
    def __init__(self, meta: dict):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        title = QLabel(meta.get("title") or "未命名骑行")
        title.setObjectName("RideItemTitle")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        sub = QLabel(self._subtitle(meta))
        sub.setObjectName("RideItemSub")
        sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lay.addWidget(title)
        lay.addWidget(sub)

    @staticmethod
    def _subtitle(meta: dict) -> str:
        dist = (meta.get("distance_m") or 0) / 1000.0
        dur = fmt_duration(meta.get("moving_s") or meta.get("duration_s") or 0)
        spd = (meta.get("avg_speed") or 0) * 3.6
        elev = meta.get("elev_gain_m") or 0
        date = (meta.get("start_time") or "")[:10]
        return f"{date} · {dist:.1f} km · {dur} · 均速 {spd:.1f} · ↑{elev:.0f}m"


class ImportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(list, list)

    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = paths

    def run(self):
        rides, errors = [], []
        total = len(self.paths)
        for i, path in enumerate(self.paths):
            self.progress.emit(i, total, os.path.basename(path))
            try:
                rides.append(load_ride(path))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{os.path.basename(path)} → {exc}")
        self.done.emit(rides, errors)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(make_app_icon())
        self.resize(1460, 940)
        # main.py 已给 QApplication 设过样式表时不再重复设置
        if not QApplication.instance().styleSheet():
            self.setStyleSheet(QSS)
        self.db = RideDB()
        self.worker = None
        self.monthly_dialog = None
        self.xingzhe_dialog = None
        self.training_dialog = None
        self.heatmap_dialog = None
        self.records_dialog = None
        self.athlete_dialog = None
        self.cap_compare = None
        self._cap_before = None
        self._current_id = None
        self._selected_ids: list[int] = []

        self._build_menu()
        self._build_ui()
        self._build_statusbar()
        self.refresh_list()

    # ------------------------------------------------------ 菜单
    def _build_menu(self):
        m = self.menuBar()
        m.setStyleSheet("QMenuBar { background:#1b1e23; } QMenuBar::item { padding:5px 10px; }"
                        "QMenuBar::item:selected { background:#252b33; }"
                        "QMenu { background:#1e2227; border:1px solid #333b45; }"
                        "QMenu::item { padding:5px 18px; } QMenu::item:selected { background:#21384d; }")
        file_menu = m.addMenu("文件")
        act_import = QAction("导入骑行文件（FIT / GPX）…", self)
        act_import.setShortcut("Ctrl+I")
        act_import.triggered.connect(self.import_files)
        file_menu.addAction(act_import)
        act_xz = QAction("同步行者数据…", self)
        act_xz.setShortcut("Ctrl+Shift+S")
        act_xz.triggered.connect(self.show_xingzhe)
        file_menu.addAction(act_xz)
        act_delete = QAction("移除选中记录", self)
        act_delete.triggered.connect(self.delete_selected)
        file_menu.addAction(act_delete)
        file_menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        stat_menu = m.addMenu("统计")
        act_month = QAction("月度统计…", self)
        act_month.setShortcut("Ctrl+M")
        act_month.triggered.connect(self.show_monthly)
        stat_menu.addAction(act_month)
        act_compare = QAction("对比选中的骑行", self)
        act_compare.triggered.connect(self.compare_selected)
        stat_menu.addAction(act_compare)
        act_plan = QAction("训练计划…", self)
        act_plan.setShortcut("Ctrl+T")
        act_plan.triggered.connect(self.show_training)
        stat_menu.addAction(act_plan)
        act_heat = QAction("骑行热力图…", self)
        act_heat.setShortcut("Ctrl+H")
        act_heat.triggered.connect(self.show_heatmap)
        stat_menu.addAction(act_heat)
        act_records = QAction("个人最佳与里程碑…", self)
        act_records.setShortcut("Ctrl+B")
        act_records.triggered.connect(self.show_records)
        stat_menu.addAction(act_records)

        me_menu = m.addMenu("个人")
        act_athlete = QAction("个人资料 / 能力图…", self)
        act_athlete.setShortcut("Ctrl+P")
        act_athlete.triggered.connect(self.show_athlete)
        me_menu.addAction(act_athlete)

        help_menu = m.addMenu("帮助")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._about)
        help_menu.addAction(act_about)

    # ------------------------------------------------------ 界面
    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter)

        # ---------- 左：清单 ----------
        left = QFrame()
        left.setObjectName("Panel")
        left.setMinimumWidth(300)
        left.setMaximumWidth(410)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(12, 12, 12, 12)
        ll.setSpacing(8)

        head = QLabel("我的骑行")
        head.setObjectName("RideTitle")
        ll.addWidget(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题或日期…")
        self.search.textChanged.connect(lambda _: self.refresh_list())
        ll.addWidget(self.search)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)
        ll.addWidget(self.list, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.btn_import = QPushButton("导入文件")
        self.btn_import.clicked.connect(self.import_files)
        self.btn_xz = QPushButton("行者同步")
        self.btn_xz.setToolTip("登录行者后一键把网上的骑行记录同步到本地")
        self.btn_xz.clicked.connect(self.show_xingzhe)
        self.btn_delete = QPushButton("移除")
        self.btn_delete.clicked.connect(self.delete_selected)
        row1.addWidget(self.btn_import)
        row1.addWidget(self.btn_xz)
        row1.addWidget(self.btn_delete)
        ll.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.btn_compare = QPushButton("叠加对比")
        self.btn_compare.clicked.connect(self.compare_selected)
        self.btn_month = QPushButton("月度统计")
        self.btn_month.clicked.connect(self.show_monthly)
        self.btn_plan = QPushButton("训练计划")
        self.btn_plan.setToolTip("按历史数据选择目标与每周次数，生成训练任务")
        self.btn_plan.clicked.connect(self.show_training)
        row2.addWidget(self.btn_compare)
        row2.addWidget(self.btn_month)
        row2.addWidget(self.btn_plan)
        ll.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)
        self.btn_athlete = QPushButton("个人中心")
        self.btn_athlete.setToolTip("个人资料 / 车辆资料 / 自动能力图")
        self.btn_athlete.clicked.connect(self.show_athlete)
        self.btn_heat = QPushButton("骑行热力图")
        self.btn_heat.setToolTip("按年度 / 月度把所有轨迹叠成热力图，可导出图片")
        self.btn_heat.clicked.connect(self.show_heatmap)
        row3.addWidget(self.btn_athlete)
        row3.addWidget(self.btn_heat)
        ll.addLayout(row3)

        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.btn_records = QPushButton("个人最佳与里程碑")
        self.btn_records.setToolTip("单项纪录（最长/最快/最大爬升）+ 累计阶梯成就与达成日期")
        self.btn_records.clicked.connect(self.show_records)
        row4.addWidget(self.btn_records)
        ll.addLayout(row4)

        hint = QLabel("按住 Ctrl / Shift 多选，可把多条轨迹叠加对比")
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        ll.addWidget(hint)

        self.summary = QLabel("")
        self.summary.setObjectName("Dim")
        ll.addWidget(self.summary)

        splitter.addWidget(left)

        # ---------- 右：地图 + 详情 ----------
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)

        map_box = QWidget()
        ml = QVBoxLayout(map_box)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btn_zoom_out = QPushButton("－")
        self.btn_zoom_out.setFixedWidth(36)
        self.btn_zoom_out.clicked.connect(lambda: self.map.zoom_out())
        self.btn_zoom_in = QPushButton("＋")
        self.btn_zoom_in.setFixedWidth(36)
        self.btn_zoom_in.clicked.connect(lambda: self.map.zoom_in())
        self.btn_fit = QPushButton("适配轨迹")
        self.btn_fit.clicked.connect(lambda: self.map.fit_track())
        self.chk_speed = QCheckBox("按速度着色")
        self.chk_speed.setChecked(True)
        self.chk_speed.toggled.connect(lambda v: self.map.set_color_by_speed(v))
        self.cmb_layer = QComboBox()
        self.cmb_layer.addItems(["标准地图", "卫星地图"])
        self.cmb_layer.setFixedWidth(100)
        self.cmb_layer.currentIndexChanged.connect(
            lambda i: self.map.set_style("road" if i == 0 else "sat"))

        toolbar.addWidget(QLabel("轨迹地图"))
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_fit)
        toolbar.addWidget(self.chk_speed)
        toolbar.addStretch(1)
        toolbar.addWidget(self.cmb_layer)
        ml.addLayout(toolbar)

        self.map = MapCanvas()
        ml.addWidget(self.map, 1)
        right_split.addWidget(map_box)

        detail = QFrame()
        detail.setObjectName("Panel")
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.setSpacing(10)
        self.stack = QStackedWidget()
        dl.addWidget(self.stack)

        # 单条详情页
        page_single = QWidget()
        sl = QVBoxLayout(page_single)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)

        hrow = QHBoxLayout()
        self.lbl_title = QLabel("未选择骑行")
        self.lbl_title.setObjectName("RideTitle")
        self.lbl_meta = QLabel("")
        self.lbl_meta.setObjectName("Dim")
        hrow.addWidget(self.lbl_title)
        hrow.addSpacing(10)
        hrow.addWidget(self.lbl_meta)
        hrow.addStretch(1)
        sl.addLayout(hrow)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.cards = {}
        for i, (key, label) in enumerate([
            ("distance", "距离"), ("duration", "骑行时长"), ("avg_speed", "平均速度"), ("elev", "累计爬升"),
            ("hr", "平均心率"), ("cadence", "平均踏频"), ("power", "平均功率"), ("calories", "消耗"),
        ]):
            card = StatCard(label)
            grid.addWidget(card, i // 4, i % 4)
            self.cards[key] = card
        sl.addLayout(grid)

        chart_bar = QHBoxLayout()
        chart_bar.setSpacing(8)
        chart_title = QLabel("数据曲线")
        chart_title.setObjectName("SectionTitle")
        chart_bar.addWidget(chart_title)
        chart_bar.addStretch(1)
        self.btn_time = QPushButton("按时间")
        self.btn_time.setCheckable(True)
        self.btn_time.setChecked(True)
        self.btn_dist = QPushButton("按距离")
        self.btn_dist.setCheckable(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.btn_time)
        group.addButton(self.btn_dist)
        self.btn_time.clicked.connect(lambda: self.chart.set_mode("time"))
        self.btn_dist.clicked.connect(lambda: self.chart.set_mode("distance"))
        chart_bar.addWidget(self.btn_time)
        chart_bar.addWidget(self.btn_dist)
        sl.addLayout(chart_bar)

        self.chart = RideChart()
        sl.addWidget(self.chart, 1)
        self.stack.addWidget(page_single)

        # 对比页
        page_cmp = QWidget()
        cl = QVBoxLayout(page_cmp)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)

        crow = QHBoxLayout()
        self.lbl_cmp_title = QLabel("叠加对比")
        self.lbl_cmp_title.setObjectName("RideTitle")
        self.lbl_cmp_meta = QLabel("")
        self.lbl_cmp_meta.setObjectName("Dim")
        crow.addWidget(self.lbl_cmp_title)
        crow.addSpacing(10)
        crow.addWidget(self.lbl_cmp_meta)
        crow.addStretch(1)
        cl.addLayout(crow)

        self.cmp_table = QTableWidget(0, len(COMPARE_COLUMNS))
        self.cmp_table.setHorizontalHeaderLabels(COMPARE_COLUMNS)
        self.cmp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cmp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cmp_table.setAlternatingRowColors(True)
        self.cmp_table.verticalHeader().setVisible(False)
        self.cmp_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.cmp_table.setMinimumHeight(120)
        cl.addWidget(self.cmp_table, 0)

        cmp_bar = QHBoxLayout()
        cmp_bar.setSpacing(8)
        cmp_title = QLabel("曲线对比（横轴：累计距离）")
        cmp_title.setObjectName("SectionTitle")
        cmp_bar.addWidget(cmp_title)
        cmp_bar.addStretch(1)
        cmp_bar.addWidget(QLabel("指标"))
        self.cmb_metric = QComboBox()
        for label, key, _ in CompareChart.METRICS:
            self.cmb_metric.addItem(label, key)
        self.cmb_metric.currentIndexChanged.connect(
            lambda _: self.cmp_chart.set_metric(self.cmb_metric.currentData()))
        cmp_bar.addWidget(self.cmb_metric)
        cl.addLayout(cmp_bar)

        self.cmp_chart = CompareChart()
        cl.addWidget(self.cmp_chart, 1)
        self.stack.addWidget(page_cmp)

        right_split.addWidget(detail)
        right_split.setSizes([400, 560])
        splitter.addWidget(right_split)
        splitter.setSizes([310, 1120])

        self.setCentralWidget(central)

    def _build_statusbar(self):
        sb = self.statusBar()
        self.status_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setTextVisible(False)
        self.progress.hide()
        sb.addWidget(self.status_label, 1)
        sb.addPermanentWidget(self.progress)

    # ------------------------------------------------------ 列表
    def refresh_list(self, select_id: int | None = None):
        keep = select_id or self._current_id
        kw = self.search.text().strip()
        rides = self.db.list_rides(kw)

        self.list.blockSignals(True)
        self.list.clear()
        selected_item = None
        for meta in rides:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, meta["id"])
            item.setSizeHint(QSize(240, 52))
            self.list.addItem(item)
            self.list.setItemWidget(item, RideItemWidget(meta))
            if meta["id"] == keep:
                selected_item = item
        self.list.blockSignals(False)

        count = self.db.count()
        total_km = self.db.total_distance() / 1000.0
        self.summary.setText(f"共 {count} 条记录 · 累计 {total_km:.0f} km")

        self._selected_ids = []
        if rides:
            target = selected_item or self.list.item(0)
            self.list.setCurrentItem(target)
            self._on_selection_changed()
        else:
            self._current_id = None
            self.show_empty()

    def _on_selection_changed(self):
        ids = [self.list.item(i).data(Qt.ItemDataRole.UserRole)
               for i in range(self.list.count()) if self.list.item(i).isSelected()]
        if ids == self._selected_ids:
            return
        self._selected_ids = ids
        if not ids:
            self._current_id = None
            self.stack.setCurrentIndex(0)
            self.show_empty()
            return
        self._current_id = ids[-1]
        if len(ids) == 1:
            self.stack.setCurrentIndex(0)
            self.load_detail(ids[0])
        else:
            self.load_compare(ids)

    def show_empty(self):
        self.stack.setCurrentIndex(0)
        self.lbl_title.setText("未选择骑行")
        self.lbl_meta.setText("点击左侧记录查看轨迹与数据")
        for card in self.cards.values():
            card.set("--", "")
        self.chart.set_samples([])
        self.map.clear("导入骑行记录后，这里会显示轨迹地图")

    # ------------------------------------------------------ 单条详情
    def load_detail(self, ride_id: int):
        meta = self.db.get_ride(ride_id)
        if not meta:
            return
        samples = self.db.get_samples(ride_id)

        self.lbl_title.setText(meta.get("title") or "未命名骑行")
        parts = [meta.get("start_time") or "", meta.get("sport") or "",
                 meta.get("source_format") or "", f"{meta.get('point_count') or 0} 点"]
        self.lbl_meta.setText(" · ".join(p for p in parts if p))

        dist_km = (meta.get("distance_m") or 0) / 1000.0
        self.cards["distance"].set(f"{dist_km:.2f} km", f"轨迹 {meta.get('point_count') or 0} 点")
        dur = meta.get("duration_s") or 0
        mov = meta.get("moving_s") or 0
        stop = max(0.0, dur - mov)
        self.cards["duration"].set(
            fmt_duration(mov), f">5km/h · 全程 {fmt_duration(dur)} · 停 {fmt_duration(stop)}")
        spd = (meta.get("avg_speed") or 0) * 3.6
        mx = (meta.get("max_speed") or 0) * 3.6
        self.cards["avg_speed"].set(f"{spd:.1f} km/h", f"最大 {mx:.1f}")
        elev = meta.get("elev_gain_m") or 0
        loss = meta.get("elev_loss_m") or 0
        self.cards["elev"].set(f"{elev:.0f} m", f"下降 {loss:.0f} m")
        hr = meta.get("avg_hr")
        self.cards["hr"].set(f"{hr:.0f} bpm" if hr else "--",
                             f"最大 {meta.get('max_hr') or 0:.0f}" if hr else "无心率数据")
        cad = meta.get("avg_cadence")
        self.cards["cadence"].set(f"{cad:.0f} rpm" if cad else "--",
                                  f"最大 {meta.get('max_cadence') or 0:.0f}" if cad else "无踏频数据")
        pw = meta.get("avg_power")
        self.cards["power"].set(f"{pw:.0f} W" if pw else "--",
                                f"最大 {meta.get('max_power') or 0:.0f}" if pw else "无功率数据")
        cal = meta.get("calories")
        self.cards["calories"].set(f"{cal:.0f} kcal" if cal else "--", "估算" if cal else "无数据")

        self.chart.set_samples(samples, "time" if self.btn_time.isChecked() else "distance")
        if any(s.get("lat") is not None for s in samples):
            self.map.set_track(samples)
        else:
            self.map.clear("该记录没有 GPS 轨迹数据（可能为室内骑行）")

    # ------------------------------------------------------ 叠加对比
    def compare_selected(self):
        ids = self._selected_ids
        if len(ids) < 2:
            self.status_label.setText("请按住 Ctrl / Shift 选中至少两条骑行再对比")
            return
        self.load_compare(ids)

    def load_compare(self, ids: list[int]):
        ids = ids[:MAX_COMPARE]
        metas, series, map_items = [], [], []
        for i, rid in enumerate(ids):
            meta = self.db.get_ride(rid)
            if not meta:
                continue
            samples = self.db.get_samples(rid)
            color = QColor(COMPARE_COLORS[i % len(COMPARE_COLORS)])
            label = f"{(meta.get('start_time') or '')[:10]} {meta.get('title') or ''}".strip()
            metas.append(meta)
            series.append({"label": label, "color": color, "samples": samples})
            map_items.append({"samples": samples, "color": color, "label": label})

        if not metas:
            return

        n = len(metas)
        self.cmp_chart.set_series(series)
        self.cmp_chart.set_metric(self.cmb_metric.currentData() or "speed")
        self.map.set_compare(map_items)

        self.stack.setCurrentIndex(1)
        self.lbl_cmp_title.setText(f"对比 {n} 条骑行")
        note = ""
        if len(ids) < len(self._selected_ids):
            note = f" · 最多同时对比 {MAX_COMPARE} 条"
        self.lbl_cmp_meta.setText(f"日期 / 距离 / 均速 / 爬升 一览{note}")

        self._fill_compare_table(metas, series)

    def _fill_compare_table(self, metas: list[dict], series: list[dict]):
        self.cmp_table.setRowCount(0)
        self.cmp_table.setRowCount(len(metas))
        for i, meta in enumerate(metas):
            values = [
                (meta.get("title") or "未命名") + "  ",
                (meta.get("start_time") or "")[:10],
                f"{(meta.get('distance_m') or 0) / 1000:.2f}",
                fmt_duration(meta.get("moving_s") or 0),
                f"{((meta.get('avg_speed') or 0) * 3.6):.1f}",
                f"{(meta.get('elev_gain_m') or 0):.0f}",
                f"{(meta.get('avg_hr') or 0):.0f}" if meta.get("avg_hr") else "--",
                f"{(meta.get('avg_cadence') or 0):.0f}" if meta.get("avg_cadence") else "--",
                f"{(meta.get('avg_power') or 0):.0f}" if meta.get("avg_power") else "--",
                f"{(meta.get('calories') or 0):.0f}" if meta.get("calories") else "--",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                if j != 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setForeground(series[i]["color"])
                self.cmp_table.setItem(i, j, item)

    # ------------------------------------------------------ 月度统计
    def show_monthly(self):
        if self.monthly_dialog is None:
            self.monthly_dialog = MonthlyStatsDialog(self.db, self)
        self.monthly_dialog.refresh()
        self.monthly_dialog.show()
        self.monthly_dialog.raise_()
        self.monthly_dialog.activateWindow()

    # ------------------------------------------------------ 行者同步
    def show_xingzhe(self):
        if self.xingzhe_dialog is None:
            self.xingzhe_dialog = XingzheSyncDialog(self.db, self)
            self.xingzhe_dialog.synced.connect(self._on_xingzhe_synced)
            self.xingzhe_dialog.sync_started.connect(self._on_xz_sync_start)
        self.xingzhe_dialog.refresh_status()
        self.xingzhe_dialog.show()
        self.xingzhe_dialog.raise_()
        self.xingzhe_dialog.activateWindow()

    def _on_xz_sync_start(self):
        self._cap_before = self._snap_capability()

    def _on_xingzhe_synced(self, added: int):
        if added:
            self.status_label.setText(f"行者同步完成：新增 {added} 条记录")
            self._show_cap_compare(self._cap_before or {}, added, "行者同步")
        if self.monthly_dialog and self.monthly_dialog.isVisible():
            self.monthly_dialog.refresh()
        self.refresh_list(select_id=self._current_id)

    # ------------------------------------------------------ 骑行热力图
    def show_records(self):
        if self.records_dialog is None:
            self.records_dialog = RecordsDialog(self.db, self)
        else:
            self.records_dialog.reload()
        self.records_dialog.show()
        self.records_dialog.raise_()
        self.records_dialog.activateWindow()

    def show_heatmap(self):
        if self.heatmap_dialog is None:
            self.heatmap_dialog = HeatmapDialog(self.db, self)
        else:
            self.heatmap_dialog.reload_years()
        self.heatmap_dialog.show()
        self.heatmap_dialog.raise_()
        self.heatmap_dialog.activateWindow()

    # ------------------------------------------------------ 训练计划
    def show_training(self):
        if self.training_dialog is None:
            self.training_dialog = TrainingPlanDialog(self.db, self)
        self.training_dialog.refresh()
        self.training_dialog.show()
        self.training_dialog.raise_()
        self.training_dialog.activateWindow()

    # ------------------------------------------------------ 个人中心 / 能力图
    def _snap_capability(self) -> dict:
        try:
            return cap_snapshot(self.db)
        except Exception:  # noqa: BLE001
            return {"items": [], "overall": 0, "summary": ""}

    def _show_cap_compare(self, before: dict, added: int, note: str):
        if not added:
            return
        after = self._snap_capability()
        self.cap_compare = show_compare(self, before, after, added, note)

    def show_athlete(self):
        if self.athlete_dialog is None:
            self.athlete_dialog = AthleteDialog(self.db, self)
        else:
            self.athlete_dialog.reload()
        self.athlete_dialog.show()
        self.athlete_dialog.raise_()
        self.athlete_dialog.activateWindow()

    # ------------------------------------------------------ 导入 / 删除
    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择骑行文件", "", "骑行文件 (*.fit *.gpx *.FIT *.GPX);;所有文件 (*.*)")
        if not paths:
            return
        self._start_import(paths)

    def _start_import(self, paths: list[str]):
        self._cap_before = self._snap_capability()
        self.btn_import.setEnabled(False)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.show()
        self.status_label.setText(f"正在解析 0/{len(paths)}…")

        self.worker = ImportWorker(paths)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_import_done)
        self.worker.start()

    def _on_progress(self, i: int, total: int, name: str):
        self.progress.setValue(i)
        self.status_label.setText(f"正在解析 {i + 1}/{total}：{name}")

    def _on_import_done(self, rides, errors):
        self.progress.hide()
        self.btn_import.setEnabled(True)
        added, skipped = [], 0
        last_id = None
        for ride in rides:
            if self.db.exists(ride.fingerprint):
                skipped += 1
                continue
            try:
                last_id = self.db.add_ride(ride)
                added.append(ride)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{ride.title} 入库失败：{exc}")

        msg = f"导入完成：新增 {len(added)} 条"
        if skipped:
            msg += f"，跳过重复 {skipped} 条"
        if errors:
            msg += f"，失败 {len(errors)} 条"
        self.status_label.setText(msg)
        if self.monthly_dialog and self.monthly_dialog.isVisible():
            self.monthly_dialog.refresh()

        self.refresh_list(select_id=last_id or self._current_id)
        if added:
            self._show_cap_compare(self._cap_before or {}, len(added), "手动导入")
        if errors:
            QMessageBox.warning(self, "部分文件导入失败", "\n".join(errors[:10]))
        self.worker = None

    def delete_selected(self):
        ids = self._selected_ids
        if not ids:
            return
        if len(ids) == 1:
            meta = self.db.get_ride(ids[0])
            name = meta.get("title") if meta else "该记录"
            text = f"确定从软件中移除「{name}」吗？"
        else:
            text = f"确定从软件中移除选中的 {len(ids)} 条记录吗？"
        ret = QMessageBox.question(
            self, "移除记录", text + "\n（只删除数据库记录，不会删除原始文件）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ret != QMessageBox.StandardButton.Yes:
            return
        for rid in ids:
            self.db.delete_ride(rid)
        self._current_id = None
        self._selected_ids = []
        self.status_label.setText(f"已移除 {len(ids)} 条记录")
        if self.monthly_dialog and self.monthly_dialog.isVisible():
            self.monthly_dialog.refresh()
        self.stack.setCurrentIndex(0)
        self.refresh_list()

    def _about(self):
        QMessageBox.information(
            self, "关于",
            "私人骑行数据 · PrivateBike\n\n"
            "本地骑行数据管理：导入 FIT / GPX，查看轨迹地图（高德底图）、数据曲线、\n"
            "多记录叠加对比与月度统计。数据全部保存在本机 data/bike.db，不上传。")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        if self.monthly_dialog:
            self.monthly_dialog.close()
        if self.xingzhe_dialog:
            self.xingzhe_dialog.close()
        if self.heatmap_dialog:
            self.heatmap_dialog.close()
        if self.records_dialog:
            self.records_dialog.close()
        if self.training_dialog:
            self.training_dialog.close()
        if self.athlete_dialog:
            self.athlete_dialog.close()
        if self.cap_compare:
            self.cap_compare.close()
        self.db.close()
        super().closeEvent(event)
