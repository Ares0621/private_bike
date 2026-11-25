"""自绘数据曲线：左列海拔/速度/心率，右列踏频/功率，共享时间或距离轴。"""
import bisect

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QPolygonF)
from PyQt6.QtWidgets import (QLabel, QSizePolicy, QVBoxLayout, QWidget)

PANELS = (
    ("海拔", "alt", QColor("#9aa7b4"), "m", True),
    ("速度", "speed", QColor("#4ec9b0"), "km/h", False),
    ("心率", "hr", QColor("#ff6b6b"), "bpm", False),
    ("踏频", "cadence", QColor("#ffc55c"), "rpm", False),
    ("功率", "power", QColor("#6fc3ff"), "W", False),
)
COL1_KEYS = ("alt", "speed", "hr")
COL2_KEYS = ("cadence", "power")

BG = QColor("#171a1e")
TEXT_DIM = QColor("#8d95a1")
TEXT_VAL = QColor("#78808c")


def fmt_duration(sec) -> str:
    if not sec:
        return "0:00"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_x(v: float, mode: str) -> str:
    if mode == "distance":
        return f"{v:.0f} km" if v >= 10 else f"{v:.1f} km"
    return fmt_duration(v)


class RideChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self._samples: list[dict] = []
        self._mode = "time"
        self._xs: list[float] = []
        self._min = 0.0
        self._max = 1.0
        self._hover = None
        self._panels = []
        self._cols = []

    # -------------------------------------------------------- 数据
    def set_samples(self, samples: list[dict], mode: str = "time"):
        self._samples = samples or []
        self._mode = mode
        self._hover = None
        self._prepare()
        self.update()

    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._mode = mode
        self._hover = None
        self._prepare()
        self.update()

    def _prepare(self):
        if self._mode == "distance":
            self._xs = [(s.get("dist") or 0.0) / 1000.0 for s in self._samples]
        else:
            self._xs = [float(s.get("t") or 0.0) for s in self._samples]
        self._min = 0.0
        self._max = (self._xs[-1] if self._xs else 0.0) or 1.0

        panels = []
        for title, key, color, unit, filled in PANELS:
            vals = [s.get(key) for s in self._samples if s.get(key) is not None]
            if key == "speed":
                vals = [v * 3.6 for v in vals]
            if not vals:
                continue
            vals.sort()
            lo, hi = (vals[0], vals[-1]) if key == "alt" else (
                vals[int(len(vals) * 0.02)], vals[int(len(vals) * 0.98)])
            if hi - lo < 1e-6:
                hi = lo + 1.0
            pad = (hi - lo) * 0.12
            panels.append((title, key, color, unit, filled, lo - pad, hi + pad))
        self._panels = panels

    # -------------------------------------------------------- 布局
    def _layout(self):
        w, h = self.width(), self.height()
        top, bottom = 12, 30
        x0, x1 = 54, w - 14
        c1 = [p for p in self._panels if p[1] in COL1_KEYS]
        c2 = [p for p in self._panels if p[1] in COL2_KEYS]
        cols = []
        if c2 and c1:
            half = max(120.0, (x1 - x0 - 44) / 2)
            cols.append({"panels": c1, "left": x0, "right": x0 + half, "top": top, "bottom": h - bottom})
            cols.append({"panels": c2, "left": x0 + half + 44, "right": x1, "top": top, "bottom": h - bottom})
        else:
            cols.append({"panels": c1 or c2, "left": x0, "right": x1, "top": top, "bottom": h - bottom})
        for c in cols:
            n = len(c["panels"]) or 1
            hh = (c["bottom"] - c["top"] - 8 * (n - 1)) / n
            c["heights"] = hh
        return cols

    # -------------------------------------------------------- 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), BG)

        if not self._samples or not self._panels:
            p.setPen(TEXT_DIM)
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "选择一条骑行记录查看数据曲线")
            p.end()
            return

        cols = self._layout()
        self._cols = cols
        small = QFont("Microsoft YaHei UI", 8)
        p.setFont(small)
        fm = QFontMetrics(small)

        # 竖向网格与 X 轴刻度
        step = self._pick_step()
        ticks = []
        v = 0.0
        while v <= self._max + 1e-9:
            ticks.append(v)
            v += step
        for tv in ticks:
            label = fmt_x(tv, self._mode)
            for c in cols:
                x = c["left"] + (tv - self._min) / (self._max - self._min) * (c["right"] - c["left"])
                p.setPen(QPen(QColor(255, 255, 255, 22), 1))
                p.drawLine(QPointF(x, c["top"]), QPointF(x, c["bottom"]))
                p.setPen(TEXT_DIM)
                p.drawText(QPointF(x - fm.horizontalAdvance(label) / 2, self.height() - 10), label)

        # 面板
        for c in cols:
            for i, panel in enumerate(c["panels"]):
                title, key, color, unit, filled, lo, hi = panel
                ptop = c["top"] + i * (c["heights"] + 8)
                rect = QRectF(c["left"], ptop + 15, c["right"] - c["left"], c["heights"] - 15)
                self._draw_panel(p, rect, panel, fm, small)

        p.setFont(small)
        p.setPen(TEXT_DIM)
        axis = "距离 (km)" if self._mode == "distance" else "时间"
        p.drawText(QPointF(self.width() - 54, self.height() - 10), axis)

        if self._hover is not None:
            self._draw_hover(p, cols)
        p.end()

    def _draw_panel(self, p: QPainter, rect: QRectF, panel, fm, font):
        title, key, color, unit, filled, lo, hi = panel

        p.setFont(font)
        p.setPen(color.lighter(120))
        p.drawText(QPointF(rect.left(), rect.top() - 3), f"{title} {unit}")

        for k in (1.0, 0.5, 0.0):
            y = rect.bottom() - k * rect.height()
            p.setPen(QPen(QColor(255, 255, 255, 26), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            txt = f"{lo + (hi - lo) * k:.0f}"
            p.setPen(TEXT_VAL)
            p.drawText(QPointF(rect.left() - 6 - fm.horizontalAdvance(txt), y + 4), txt)

        poly = self._series(key, rect, lo, hi)
        if poly is None:
            return
        if filled:
            area = QPainterPath()
            area.moveTo(QPointF(poly[0].x(), rect.bottom()))
            for pt in poly:
                area.lineTo(pt)
            area.lineTo(QPointF(poly[-1].x(), rect.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            grad.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 120))
            grad.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 12))
            p.fillPath(area, grad)
        p.setPen(QPen(color, 1.6))
        p.drawPolyline(poly)

    def _series(self, key, rect, lo, hi):
        poly = QPolygonF()
        span = self._max - self._min or 1.0
        for xv, s in zip(self._xs, self._samples):
            v = s.get(key)
            if v is None:
                continue
            if key == "speed":
                v *= 3.6
            sx = rect.left() + (xv - self._min) / span * rect.width()
            sy = rect.bottom() - (v - lo) / (hi - lo) * rect.height()
            sy = max(rect.top() - 6, min(rect.bottom() + 6, sy))
            poly.append(QPointF(sx, sy))
        return poly if len(poly) > 1 else None

    def _draw_hover(self, p: QPainter, cols):
        idx = self._hover
        s = self._samples[idx]
        xv = self._xs[idx]
        c0 = cols[0]
        span = self._max - self._min or 1.0
        sx = c0["left"] + (xv - self._min) / span * (c0["right"] - c0["left"])

        p.setPen(QPen(QColor(255, 255, 255, 80), 1, Qt.PenStyle.DashLine))
        for c in cols:
            p.drawLine(QPointF(sx, c["top"]), QPointF(sx, c["bottom"]))

        for c in cols:
            for i, panel in enumerate(c["panels"]):
                title, key, color, unit, filled, lo, hi = panel
                v = s.get(key)
                if v is None:
                    continue
                if key == "speed":
                    v *= 3.6
                rect = QRectF(c["left"], c["top"] + i * (c["heights"] + 8) + 15,
                              c["right"] - c["left"], c["heights"] - 15)
                sy = rect.bottom() - (v - lo) / (hi - lo) * rect.height()
                sy = max(rect.top(), min(rect.bottom(), sy))
                p.setPen(QPen(Qt.GlobalColor.white, 1))
                p.setBrush(color)
                p.drawEllipse(QPointF(sx, sy), 3, 3)

        lines = [fmt_x(xv, self._mode) +
                 (f"  {fmt_duration(s.get('t'))}" if self._mode == "distance" else "")]
        for panel in self._panels:
            title, key, color, unit, filled, lo, hi = panel
            v = s.get(key)
            if v is None:
                continue
            if key == "speed":
                v *= 3.6
            lines.append(f"{title} {v:.0f} {unit}")

        f = QFont("Microsoft YaHei UI", 8)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = max(fm.horizontalAdvance(t) for t in lines) + 18
        h = len(lines) * 15 + 6
        box = QRectF(self.width() - w - 16, 8, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(18, 21, 25, 225))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor("#dfe3e8"))
        for i, t in enumerate(lines):
            p.drawText(QPointF(box.left() + 9, box.top() + 16 + i * 15), t)

    def _pick_step(self):
        span = self._max - self._min
        cand = ([0.2, 0.5, 1, 2, 5, 10, 20, 40, 100] if self._mode == "distance"
                else [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800])
        for c in cand:
            if span / c <= 6:
                return c
        return cand[-1]

    # -------------------------------------------------------- 交互
    def mouseMoveEvent(self, event):
        if not self._xs or not self._cols:
            return
        c0 = self._cols[0]
        x = event.position().x()
        if x < c0["left"] or x > self._cols[-1]["right"]:
            if self._hover is not None:
                self._hover = None
                self.update()
            return
        v = self._min + (x - c0["left"]) / max(1, c0["right"] - c0["left"]) * (self._max - self._min)
        idx = bisect.bisect_left(self._xs, v)
        idx = min(idx, len(self._xs) - 1)
        if idx > 0 and abs(self._xs[idx - 1] - v) < abs(self._xs[idx] - v):
            idx -= 1
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def sizeHint(self):
        return QSize(800, 320)


class CompareChart(QWidget):
    """多条骑行叠加：横轴为累计距离，纵轴为所选指标。"""

    METRICS = (
        ("速度 (km/h)", "speed", 3.6),
        ("海拔 (m)", "alt", 1.0),
        ("心率 (bpm)", "hr", 1.0),
        ("踏频 (rpm)", "cadence", 1.0),
        ("功率 (W)", "power", 1.0),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._series: list[dict] = []
        self._metric = "speed"

    def set_series(self, series: list[dict]):
        self._series = series or []
        self.update()

    def set_metric(self, key: str):
        self._metric = key
        self.update()

    @property
    def metric_key(self) -> str:
        # 不能命名为 metric：QPaintDevice::metric 是 Qt 虚函数，
        # 覆盖后 Qt 内部会拿到字符串，导致布局/样式计算时原生崩溃。
        return self._metric

    def _converted(self, samples):
        mult = next((m for _, k, m in self.METRICS if k == self._metric), 1.0)
        out = []
        for s in samples:
            v = s.get(self._metric)
            if v is None:
                continue
            out.append(((s.get("dist") or 0.0) / 1000.0, v * mult))
        return out

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), BG)

        if not self._series:
            p.setPen(TEXT_DIM)
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "按住 Ctrl 多选几条骑行，即可叠加对比")
            p.end()
            return

        left, right, top, bottom = 54, 12, 26, 28
        plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
        small = QFont("Microsoft YaHei UI", 8)
        p.setFont(small)
        fm = QFontMetrics(small)
        p.setPen(TEXT_DIM)
        p.drawText(QPointF(plot.left() + 2, top - 10), "累计距离 (km)")

        data = [self._converted(tr["samples"]) for tr in self._series]
        data = [d for d in data if d]
        if not data:
            p.setPen(TEXT_DIM)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "所选记录没有该指标数据")
            p.end()
            return

        x_max = max(d[-1][0] for d in data) or 1.0
        vals = sorted(v for d in data for _, v in d)
        if self._metric == "alt":
            lo, hi = vals[0], vals[-1]
        else:
            lo, hi = vals[int(len(vals) * 0.02)], vals[int(len(vals) * 0.98)]
        if hi - lo < 1e-6:
            hi = lo + 1.0
        pad = (hi - lo) * 0.12
        lo, hi = lo - pad, hi + pad

        # 网格与坐标
        for k in (1.0, 0.75, 0.5, 0.25, 0.0):
            y = plot.bottom() - k * plot.height()
            p.setPen(QPen(QColor(255, 255, 255, 26), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            txt = f"{lo + (hi - lo) * k:.0f}"
            p.setPen(TEXT_VAL)
            p.drawText(QPointF(plot.left() - 6 - fm.horizontalAdvance(txt), y + 4), txt)

        step = next((c for c in (0.5, 1, 2, 5, 10, 20, 30, 50, 100) if x_max / c <= 7), 100)
        v = 0.0
        while v <= x_max + 1e-9:
            x = plot.left() + v / x_max * plot.width()
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(TEXT_DIM)
            label = f"{v:g}"
            p.drawText(QPointF(x - fm.horizontalAdvance(label) / 2, self.height() - 10), label)
            v += step

        # 曲线
        for tr, d in zip(self._series, data):
            path = QPainterPath()
            first = True
            for dist, val in d:
                x = plot.left() + dist / x_max * plot.width()
                y = plot.bottom() - (val - lo) / (hi - lo) * plot.height()
                y = max(plot.top(), min(plot.bottom(), y))
                if first:
                    path.moveTo(QPointF(x, y))
                    first = False
                else:
                    path.lineTo(QPointF(x, y))
            p.setPen(QPen(tr.get("color") or QColor("#4da3ff"), 1.8))
            p.drawPath(path)

        # 图例
        items = self._series[:8]
        f = QFont("Microsoft YaHei UI", 8)
        p.setFont(f)
        fm2 = QFontMetrics(f)
        w = min(240, max(fm2.horizontalAdvance(tr.get("label") or "--") for tr in items) + 48)
        h = len(items) * 17 + 12
        box = QRectF(self.width() - w - 20, top + 6, w, h)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(QColor(16, 19, 23, 210))
        p.drawRoundedRect(box, 7, 7)
        for i, tr in enumerate(items):
            y = box.top() + 12 + i * 17
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tr.get("color") or QColor("#4da3ff"))
            p.drawRoundedRect(QRectF(box.left() + 10, y - 3, 14, 4), 2, 2)
            p.setPen(QColor("#dfe3e8"))
            txt = fm2.elidedText(tr.get("label") or "--", Qt.TextElideMode.ElideRight, int(w - 42))
            p.drawText(QPointF(box.left() + 30, y + 2), txt)
        p.end()

    def sizeHint(self):
        return QSize(800, 260)


class MonthlyBarChart(QWidget):
    """月度里程柱状图。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._items: list[dict] = []

    def set_data(self, items: list[dict]):
        self._items = items or []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), BG)

        if not self._items:
            p.setPen(TEXT_DIM)
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "还没有骑行记录")
            p.end()
            return

        left, right, top, bottom = 54, 16, 22, 46
        plot = QRectF(left, top, self.width() - left - right, self.height() - top - bottom)
        small = QFont("Microsoft YaHei UI", 8)
        p.setFont(small)
        fm = QFontMetrics(small)

        values = [it["value"] for it in self._items]
        vmax = max(values) or 1.0
        nice_max = vmax * 1.15
        for k in (1.0, 0.75, 0.5, 0.25, 0.0):
            y = plot.bottom() - k * plot.height()
            p.setPen(QPen(QColor(255, 255, 255, 26), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            txt = f"{nice_max * k:.0f}"
            p.setPen(TEXT_VAL)
            p.drawText(QPointF(plot.left() - 6 - fm.horizontalAdvance(txt), y + 4), txt)

        p.setPen(TEXT_DIM)
        p.drawText(QPointF(14, top - 8), "里程 km")

        n = len(self._items)
        slot = plot.width() / n
        bar_w = min(46.0, slot * 0.62)
        for i, it in enumerate(self._items):
            cx = plot.left() + slot * (i + 0.5)
            h = it["value"] / nice_max * plot.height()
            rect = QRectF(cx - bar_w / 2, plot.bottom() - h, bar_w, max(2.0, h))
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, QColor("#4da3ff"))
            grad.setColorAt(1, QColor("#2b6fb0"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawRoundedRect(rect, 4, 4)

            p.setPen(QColor("#cfd7e0"))
            txt = f"{it['value']:.0f}"
            p.drawText(QPointF(cx - fm.horizontalAdvance(txt) / 2, rect.top() - 5), txt)

            p.setPen(TEXT_DIM)
            label = it["label"]
            if n > 14 and i % 2:
                label = ""
            p.drawText(QPointF(cx - fm.horizontalAdvance(label) / 2, self.height() - 26), label)
        p.end()

    def sizeHint(self):
        return QSize(900, 260)


class RadarChart(QWidget):
    """个人能力雷达图：六边形网格 + 当前能力面（可选叠加「之前」的灰色虚线面）。

    实现上不重写 paintEvent，而是把整张图渲染成 QPixmap 交给内部 QLabel 显示，
    这样在 Qt6 / Python 3.14 的若干组合下不会触发绘制层原生崩溃。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self._items: list[dict] = []
        self._base: list[dict] = []
        self._base_label = "之前"
        self._label = "当前"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._label_widget = QLabel(self)
        self._label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                                         QSizePolicy.Policy.Expanding)
        lay.addWidget(self._label_widget)

    def set_data(self, items: list[dict], baseline: list[dict] | None = None,
                 label: str = "当前", base_label: str = "之前"):
        self._items = items or []
        self._base = baseline or []
        self._label = label
        self._base_label = base_label
        self._render()

    def sizeHint(self):
        return QSize(520, 360)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def _render(self):
        w = self.width() or self.sizeHint().width()
        h = self.height() or self.sizeHint().height()
        if w < 8 or h < 8:
            return
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            self._draw(p, w, h)
        finally:
            p.end()
        self._label_widget.setPixmap(pm)

    def _draw(self, p, w, h):
        import math

        p.fillRect(0, 0, w, h, BG)
        n = len(self._items)
        if not n:
            p.setPen(TEXT_DIM)
            p.setFont(QFont("Microsoft YaHei UI", 10))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                       "还没有骑行数据，能力图会在导入 / 同步后自动生成")
            return

        cx = w / 2
        cy = h / 2 + 8
        R = min(w / 2 - 64, h / 2 - 52)
        angles = [math.pi / 2 - i * 2 * math.pi / n for i in range(n)]

        def pt(i, ratio):
            a = angles[i]
            return QPointF(cx + math.cos(a) * R * ratio, cy - math.sin(a) * R * ratio)

        # 网格环
        for ring in (0.2, 0.4, 0.6, 0.8, 1.0):
            poly = QPolygonF([pt(i, ring) for i in range(n)])
            p.setPen(QPen(QColor(255, 255, 255, 30 if ring == 1.0 else 18), 1,
                          Qt.PenStyle.DashLine if ring < 1.0 else Qt.PenStyle.SolidLine))
            p.drawPolygon(poly)

        small = QFont("Microsoft YaHei UI", 8)
        p.setFont(small)
        fm = QFontMetrics(small)

        # 轴线
        for i in range(n):
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawLine(QPointF(cx, cy), pt(i, 1.0))

        # 基准面（之前）
        if self._base and len(self._base) == n:
            poly = QPolygonF([pt(i, max(0.02, self._base[i]["score"] / 100)) for i in range(n)])
            p.setPen(QPen(QColor(150, 160, 172), 1.4, Qt.PenStyle.DashLine))
            p.setBrush(QColor(150, 160, 172, 22))
            p.drawPolygon(poly)

        # 当前面
        poly = QPolygonF([pt(i, max(0.02, it["score"] / 100)) for i, it in enumerate(self._items)])
        p.setPen(QPen(QColor("#4da3ff"), 2))
        p.setBrush(QColor(77, 163, 255, 70))
        p.drawPolygon(poly)

        # 顶点 + 轴标签
        for i, item in enumerate(self._items):
            a = angles[i]
            score_pt = pt(i, max(0.02, item["score"] / 100))
            p.setPen(QPen(Qt.GlobalColor.white, 1))
            p.setBrush(QColor("#4da3ff"))
            p.drawEllipse(score_pt, 3, 3)

            lx = cx + math.cos(a) * (R + 20)
            ly = cy - math.sin(a) * (R + 20)
            txt = f"{item['label']} {item['score']}"
            tw = fm.horizontalAdvance(txt)
            if abs(math.cos(a)) < 0.2:
                lx -= tw / 2
            elif math.cos(a) < 0:
                lx -= tw
            p.setPen(QColor("#dfe3e8"))
            p.drawText(QPointF(lx, ly + 4), txt)

            sub = item.get("text") or ""
            w2 = fm.horizontalAdvance(sub)
            sx = lx if abs(math.cos(a)) >= 0.2 else lx + (tw - w2) / 2
            sy = ly + (16 if math.sin(a) >= 0 else -10)
            p.setPen(TEXT_VAL)
            p.drawText(QPointF(sx, sy), sub)

        # 图例
        legend = [(self._label, QColor("#4da3ff"), False)]
        if self._base:
            legend.insert(0, (self._base_label, QColor(150, 160, 172), True))
        lf = QFont("Microsoft YaHei UI", 8)
        p.setFont(lf)
        fm2 = QFontMetrics(lf)
        x = 14
        y = 20
        for text, color, dashed in legend:
            p.setPen(QPen(color, 1.6,
                          Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(x, y - 4), QPointF(x + 18, y - 4))
            p.setPen(TEXT_DIM)
            p.drawText(QPointF(x + 24, y), text)
            x += 24 + fm2.horizontalAdvance(text) + 18
        p.setPen(TEXT_DIM)
        p.drawText(QPointF(14, h - 12), "网格刻度：内圈 60 / 外圈 100（满分）")
