"""个人中心：个人资料 / 车辆资料 / 个人能力图（能力图全部由骑行数据自动生成）。"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox,
                             QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from . import athlete as ath
from .charts import RadarChart
from .theme import QSS
from .widgets import StatCard


def _dspin(lo, hi, step, suffix="", decimals=1):
    box = QDoubleSpinBox()
    box.setRange(lo, hi)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setSpecialValueText("未填")
    if suffix:
        box.setSuffix(suffix)
    box.setFixedWidth(150)
    return box


def _ispin(lo, hi, suffix=""):
    box = QSpinBox()
    box.setRange(lo, hi)
    box.setSpecialValueText("未填")
    if suffix:
        box.setSuffix(suffix)
    box.setFixedWidth(150)
    return box


class AthleteDialog(QDialog):
    """个人资料 + 车辆资料 + 自动能力图。"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("个人中心 · 资料与能力图")
        self.resize(1180, 780)
        self.setStyleSheet(QSS)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        # ---------------- 左：资料表单 ----------------
        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(372)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.setSpacing(8)

        title = QLabel("我的资料")
        title.setObjectName("RideTitle")
        ll.addWidget(title)

        hint = QLabel("能力图只用骑行数据自动算；身体 / 车的数据用来换算 BMI、心率区间、"
                      "估算功率与推重比。")
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        ll.addWidget(hint)

        # 个人
        sec1 = QLabel("个人")
        sec1.setObjectName("SectionTitle")
        ll.addWidget(sec1)
        f1 = QFormLayout()
        f1.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        f1.setHorizontalSpacing(10)
        f1.setVerticalSpacing(7)
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("称呼（可空）")
        self.ed_name.setFixedWidth(150)
        self.cmb_sex = QComboBox()
        self.cmb_sex.addItems(["未填", "男", "女"])
        self.cmb_sex.setFixedWidth(150)
        self.sp_year = _ispin(0, 2015)
        self.sp_year.setSpecialValueText("未填")
        self.sp_height = _dspin(0, 230, 0.5, " cm", 1)
        self.sp_weight = _dspin(0, 160, 0.5, " kg", 1)
        self.sp_rhr = _ispin(0, 130, " bpm")
        self.sp_mhr = _ispin(0, 230, " bpm")
        self.sp_ftp = _ispin(0, 600, " W")
        self.sp_goal = _dspin(0, 600, 10, " km/周", 0)
        self.ed_notes = QLineEdit()
        self.ed_notes.setPlaceholderText("伤病史 / 备注（可空）")
        self.ed_notes.setFixedWidth(150)

        f1.addRow("称呼", self.ed_name)
        f1.addRow("性别", self.cmb_sex)
        f1.addRow("出生年份", self.sp_year)
        f1.addRow("身高", self.sp_height)
        f1.addRow("体重", self.sp_weight)
        f1.addRow("静息心率", self.sp_rhr)
        f1.addRow("最大心率", self.sp_mhr)
        f1.addRow("FTP（可选）", self.sp_ftp)
        f1.addRow("周目标里程", self.sp_goal)
        f1.addRow("备注", self.ed_notes)
        ll.addLayout(f1)

        # 车
        sec2 = QLabel("我的公路车")
        sec2.setObjectName("SectionTitle")
        ll.addWidget(sec2)
        f2 = QFormLayout()
        f2.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        f2.setHorizontalSpacing(10)
        f2.setVerticalSpacing(7)
        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("如 Giant TCR / 自组 700C")
        self.ed_model.setFixedWidth(150)
        self.cmb_btype = QComboBox()
        self.cmb_btype.addItems(["公路车", "砾石车", "山地车", "折叠车", "其他"])
        self.cmb_btype.setFixedWidth(150)
        self.sp_bweight = _dspin(0, 30, 0.1, " kg", 1)
        self.ed_wheel = QLineEdit()
        self.ed_wheel.setPlaceholderText("如 700C 28c")
        self.ed_wheel.setFixedWidth(150)
        self.ed_gearing = QLineEdit()
        self.ed_gearing.setPlaceholderText("如 50/34 · 11-28")
        self.ed_gearing.setFixedWidth(150)
        self.ed_bnotes = QLineEdit()
        self.ed_bnotes.setPlaceholderText("如 换了碳刀 / 锁鞋")
        self.ed_bnotes.setFixedWidth(150)

        f2.addRow("车型", self.ed_model)
        f2.addRow("类型", self.cmb_btype)
        f2.addRow("车重", self.sp_bweight)
        f2.addRow("轮组", self.ed_wheel)
        f2.addRow("传动", self.ed_gearing)
        f2.addRow("备注", self.ed_bnotes)
        ll.addLayout(f2)

        ll.addStretch(1)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_save = QPushButton("保存资料")
        self.btn_save.clicked.connect(self.save)
        self.btn_reload = QPushButton("重新读取")
        self.btn_reload.clicked.connect(self.reload)
        brow.addWidget(self.btn_save)
        brow.addWidget(self.btn_reload)
        ll.addLayout(brow)

        self.lbl_saved = QLabel("")
        self.lbl_saved.setObjectName("Dim")
        self.lbl_saved.setWordWrap(True)
        ll.addWidget(self.lbl_saved)
        root.addWidget(left)

        # ---------------- 右：能力图 ----------------
        right = QFrame()
        right.setObjectName("Panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(10)

        head = QHBoxLayout()
        rt = QLabel("个人能力图")
        rt.setObjectName("RideTitle")
        head.addWidget(rt)
        head.addStretch(1)
        self.lbl_overall = QLabel("--")
        self.lbl_overall.setObjectName("Dim")
        head.addWidget(self.lbl_overall)
        rl.addLayout(head)

        self.radar = RadarChart()
        rl.addWidget(self.radar, 1)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.cards = {}
        for i, (key, name) in enumerate([("bmi", "BMI"), ("mhr", "最大心率"),
                                         ("power", "阈值估算功率"), ("wkg", "推重比")]):
            card = StatCard(name)
            grid.addWidget(card, 0, i)
            self.cards[key] = card
        rl.addLayout(grid)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("Dim")
        self.lbl_summary.setWordWrap(True)
        rl.addWidget(self.lbl_summary)

        self.lbl_zones = QLabel("")
        self.lbl_zones.setWordWrap(True)
        self.lbl_zones.setTextFormat(Qt.TextFormat.RichText)
        rl.addWidget(self.lbl_zones)

        self.lbl_tip = QLabel("")
        self.lbl_tip.setObjectName("Dim")
        self.lbl_tip.setWordWrap(True)
        rl.addWidget(self.lbl_tip)

        root.addWidget(right, 1)

        for w in (self.sp_height, self.sp_weight, self.sp_rhr, self.sp_mhr, self.sp_ftp,
                  self.sp_goal, self.sp_bweight):
            w.valueChanged.connect(lambda _v: self.refresh(update_fields=False))
        self.sp_year.valueChanged.connect(lambda _v: self.refresh(update_fields=False))
        self.cmb_sex.currentIndexChanged.connect(lambda _i: self.refresh(update_fields=False))
        self.ed_name.textChanged.connect(lambda _t: self.refresh(update_fields=False))
        self.ed_model.textChanged.connect(lambda _t: self.refresh(update_fields=False))

        self.reload()

    # ------------------------------------------------------------ 读写
    def athlete(self) -> ath.Athlete:
        return ath.Athlete(
            name=self.ed_name.text().strip(),
            sex="" if self.cmb_sex.currentIndex() == 0 else self.cmb_sex.currentText(),
            birth_year=self.sp_year.value() or None,
            height_cm=self.sp_height.value() or None,
            weight_kg=self.sp_weight.value() or None,
            resting_hr=self.sp_rhr.value() or None,
            max_hr=self.sp_mhr.value() or None,
            ftp_w=self.sp_ftp.value() or None,
            weekly_goal_km=self.sp_goal.value() or None,
            notes=self.ed_notes.text().strip(),
        )

    def bike(self) -> ath.Bike:
        return ath.Bike(
            model=self.ed_model.text().strip(),
            bike_type=self.cmb_btype.currentText(),
            weight_kg=self.sp_bweight.value() or None,
            wheel=self.ed_wheel.text().strip(),
            gearing=self.ed_gearing.text().strip(),
            notes=self.ed_bnotes.text().strip(),
            id=getattr(self, "_bike_id", None),
        )

    def reload(self):
        a, b = ath.load(self.db)
        self._bike_id = b.id
        self.ed_name.setText(a.name)
        self.cmb_sex.setCurrentIndex({"男": 1, "女": 2}.get(a.sex, 0))
        self.sp_year.setValue(int(a.birth_year or 0))
        self.sp_height.setValue(a.height_cm or 0)
        self.sp_weight.setValue(a.weight_kg or 0)
        self.sp_rhr.setValue(int(a.resting_hr or 0))
        self.sp_mhr.setValue(int(a.max_hr or 0))
        self.sp_ftp.setValue(int(a.ftp_w or 0))
        self.sp_goal.setValue(a.weekly_goal_km or 0)
        self.ed_notes.setText(a.notes)
        self.ed_model.setText(b.model)
        idx = self.cmb_btype.findText(b.bike_type)
        self.cmb_btype.setCurrentIndex(idx if idx >= 0 else 0)
        self.sp_bweight.setValue(b.weight_kg or 0)
        self.ed_wheel.setText(b.wheel)
        self.ed_gearing.setText(b.gearing)
        self.ed_bnotes.setText(b.notes)
        self.lbl_saved.setText("")
        self.refresh()

    def save(self):
        a = self.athlete()
        b = self.bike()
        self.db.save_athlete({
            "name": a.name, "sex": a.sex, "birth_year": a.birth_year,
            "height_cm": a.height_cm, "weight_kg": a.weight_kg,
            "resting_hr": a.resting_hr, "max_hr": a.max_hr, "ftp_w": a.ftp_w,
            "weekly_goal_km": a.weekly_goal_km, "notes": a.notes,
        })
        new_id = self.db.save_bike({
            "id": self._bike_id, "model": b.model, "bike_type": b.bike_type,
            "weight_kg": b.weight_kg, "wheel": b.wheel, "gearing": b.gearing,
            "notes": b.notes,
        })
        self._bike_id = new_id
        self.lbl_saved.setText("已保存到本机数据库（data/bike.db）。")
        self.refresh()

    # ------------------------------------------------------------ 能力图
    def refresh(self, update_fields: bool = True):
        cap = ath.capability(self.db)
        prof = cap.get("profile")
        items = cap.get("items") or []
        self.radar.set_data(items, None, label="当前")
        self.lbl_overall.setText(f"综合 {cap.get('overall', 0)} / 100 · 依据 "
                                 f"{'近 %d 天' % prof.window_days if prof else '全部'} "
                                 f"{prof.rides if prof else 0} 次骑行" if prof else "综合 --")

        a, b = self.athlete(), self.bike()
        d = ath.derived(prof, a, b, prof.base_speed if prof else None)

        bmi = a.bmi
        self.cards["bmi"].set(f"{bmi:g}" if bmi else "--",
                              a.bmi_note() if bmi else "填身高体重后显示")
        mhr = a.max_hr_est
        self.cards["mhr"].set(f"{mhr:.0f} bpm" if mhr else "--",
                              "实测值" if a.max_hr else ("按年龄估算" if mhr else "填年龄或最大心率"))
        self.cards["power"].set(f"≈ {d['power_threshold']:.0f} W",
                                f"均速 {d['speed']:g} km/h 的 1.1 倍")
        self.cards["wkg"].set(f"{d['w_per_kg']:.2f} W/kg",
                              f"按体重 {'%.0f' % a.weight_kg if a.weight_kg else '65(默认)'} kg"
                              f" + 车 {b.mass:g} kg 估算")

        self.lbl_summary.setText(cap.get("summary", ""))
        zones = a.hr_zones()
        if zones:
            rows = "　".join(f"<b>{c}</b> {n} {r}" for c, n, r, _u in zones)
            self.lbl_zones.setText(f"<span style='color:#8d95a1'>心率区间（按最大心率百分比）："
                                   f"</span><br>{rows}")
        else:
            self.lbl_zones.setText("<span style='color:#8d95a1'>填写年龄（或最大心率）后，"
                                   "这里会给出 Z1~Z5 心率区间。</span>")

        tips = [a.resting_note()]
        if a.weekly_goal_km:
            tips.append(f"周目标 {a.weekly_goal_km:g} km")
        if b.model or b.weight_kg:
            tips.append(f"车：{b.model or '未填型号'}（{b.bike_type}，{b.mass:g} kg）")
        if not d["weight_known"]:
            tips.append("未填体重时按 65 kg 估算功率，填上更准。")
        self.lbl_tip.setText(" · ".join(t for t in tips if t))


class CapabilityCompareDialog(QDialog):
    """导入 / 同步之后：能力图前后对比。"""

    def __init__(self, before: dict, after: dict, added: int = 0, note: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("能力图变化")
        self.resize(800, 720)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        title = QLabel("个人能力图 · 前后对比")
        title.setObjectName("RideTitle")
        root.addWidget(title)

        cap_before = before.get("items") or []
        cap_after = after.get("items") or []
        n_new = added or 0
        sub = QLabel((f"{note}　新增 {n_new} 条记录" if n_new else note) or
                     "用导入前后的历史数据各算一次能力图，看这次新增把哪一项推动了。")
        sub.setObjectName("Dim")
        sub.setWordWrap(True)
        root.addWidget(sub)

        self.radar = RadarChart()
        self.radar.set_data(cap_after, cap_before or None, label="导入后", base_label="导入前")
        root.addWidget(self.radar, 1)

        self.lbl_overall = QLabel("")
        self.lbl_overall.setWordWrap(True)
        root.addWidget(self.lbl_overall)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["维度", "导入前", "导入后", "变化"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(40 + 34 * max(6, len(cap_after)))
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        root.addWidget(self.table)

        foot = QHBoxLayout()
        self.lbl_note = QLabel(after.get("summary", ""))
        self.lbl_note.setObjectName("Dim")
        self.lbl_note.setWordWrap(True)
        foot.addWidget(self.lbl_note, 1)
        btn = QPushButton("关闭")
        btn.clicked.connect(self.close)
        foot.addWidget(btn)
        root.addLayout(foot)

        self._fill(cap_before, cap_after, before.get("overall", 0), after.get("overall", 0))

    def _fill(self, before, after, s0, s1):
        if s1 and s0:
            diff = s1 - s0
            arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
            color = "#4ec9b0" if diff > 0 else ("#ff6b6b" if diff < 0 else "#8d95a1")
            self.lbl_overall.setText(
                f"综合评分 <b>{s0}</b> → <span style='color:{color}'><b>{s1}</b> "
                f"（{arrow}{abs(diff)}）</span> / 100")
        elif s1:
            self.lbl_overall.setText(f"综合评分 <b>{s1}</b> / 100（首次生成，暂无对比基线）")
        else:
            self.lbl_overall.setText("暂无能力数据")

        bmap = {i["key"]: i for i in before}
        rows = after or before
        self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            b = bmap.get(item["key"])
            cells = [item["label"],
                     f"{b['score']}" if b else "--",
                     f"{item['score']}",
                     ]
            if b:
                d = item["score"] - b["score"]
                cells.append(("+" if d > 0 else "") + str(d))
            else:
                cells.append("新增")
            for c, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if c:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 3:
                    if text.startswith("+"):
                        cell.setForeground(QColor("#4ec9b0"))
                    elif text.startswith("-"):
                        cell.setForeground(QColor("#ff6b6b"))
                self.table.setItem(r, c, cell)


def show_compare(parent, before: dict, after: dict, added: int = 0, note: str = ""):
    dlg = CapabilityCompareDialog(before, after, added, note, parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
