"""Qt 原生地图画布：高德瓦片 + 轨迹（单条按速度着色 / 多条叠加对比），支持拖动缩放。"""
import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from .config import (COLOR_BG, DEFAULT_CENTER, DEFAULT_ZOOM, MAX_ZOOM, MIN_ZOOM,
                     TILE_SIZE, TRACK_FAST, TRACK_MID, TRACK_SINGLE, TRACK_SLOW)
from .coords import wgs84_to_gcj02
from .tiles import TileManager

M_PER_PX_EQ = 156543.03392


def latlon_to_world(lat: float, lon: float, z: int):
    size = float(TILE_SIZE) * (2 ** z)
    x = (lon + 180.0) / 360.0 * size
    lat_r = math.radians(max(min(lat, 85.05), -85.05))
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * size
    return x, y


def world_to_latlon(x: float, y: float, z: int):
    size = float(TILE_SIZE) * (2 ** z)
    lon = x / size * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi - 2.0 * math.pi * y / size)))
    return lat, lon


def _lerp(c1, c2, k):
    return QColor(int(c1[0] + (c2[0] - c1[0]) * k),
                  int(c1[1] + (c2[1] - c1[1]) * k),
                  int(c1[2] + (c2[2] - c1[2]) * k))


class MapCanvas(QWidget):
    COLOR_BUCKETS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.tiles = TileManager("road", self)
        self.tiles.tile_loaded.connect(self._on_tile)

        self._zoom = DEFAULT_ZOOM
        self._center = DEFAULT_CENTER
        self._tracks: list[dict] = []
        self._colors: list[QColor] = []
        self._color_speed = True
        self._drag_start = None
        self._drag_center = None
        self._hover = None
        self._hint = "导入骑行记录后，这里会显示轨迹地图"

    # ---------------------------------------------------------- 数据
    @staticmethod
    def _filter(samples):
        """高德瓦片是 GCJ-02，这里把 GPS 原始坐标（WGS-84）转成 GCJ-02，避免整体偏移。"""
        out = []
        for s in samples:
            lat, lon = s.get("lat"), s.get("lon")
            if lat is None or lon is None:
                continue
            glat, glon = wgs84_to_gcj02(float(lat), float(lon))
            if glat == lat and glon == lon:
                out.append(s)
            else:
                d = dict(s)
                d["lat"], d["lon"] = glat, glon
                out.append(d)
        return out

    def set_track(self, samples, label: str = ""):
        pts = self._filter(samples)
        self._tracks = [{"pts": pts, "color": None, "label": label}]
        self._build_colors()
        self._reset_view(pts)

    def set_compare(self, items: list[dict]):
        """items: [{"samples": [...], "color": QColor, "label": str}, ...]"""
        self._tracks = []
        for it in items:
            pts = self._filter(it.get("samples") or [])
            if pts:
                self._tracks.append({
                    "pts": pts,
                    "color": it.get("color") or QColor(*TRACK_SINGLE),
                    "label": it.get("label") or "",
                })
        self._colors = []
        if self._tracks:
            self.fit_track()
        else:
            self._center = DEFAULT_CENTER
            self._zoom = DEFAULT_ZOOM
        self.update()

    def _reset_view(self, pts):
        if pts:
            self.fit_track()
        else:
            self._center = DEFAULT_CENTER
            self._zoom = DEFAULT_ZOOM
        self.update()

    def _build_colors(self):
        pts = self._tracks[0]["pts"] if self._tracks else []
        speeds = sorted(s.get("speed") for s in pts if s.get("speed"))
        if not speeds:
            self._colors = [QColor(*TRACK_SINGLE)] * len(pts)
            return
        lo = speeds[min(len(speeds) - 1, int(len(speeds) * 0.05))]
        hi = speeds[min(len(speeds) - 1, int(len(speeds) * 0.95))]
        if hi <= lo:
            hi = lo + 1.0
        self._colors = []
        for s in pts:
            v = s.get("speed")
            k = 0.5 if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))
            self._colors.append(self._bucket_color(min(self.COLOR_BUCKETS - 1, int(k * self.COLOR_BUCKETS))))

    def _bucket_color(self, b: int) -> QColor:
        k = (b + 0.5) / self.COLOR_BUCKETS
        if k < 0.5:
            return _lerp(TRACK_SLOW, TRACK_MID, k / 0.5)
        return _lerp(TRACK_MID, TRACK_FAST, (k - 0.5) / 0.5)

    def clear(self, hint: str = "导入骑行记录后，这里会显示轨迹地图"):
        self._hint = hint
        self._tracks = []
        self._colors = []
        self._center = DEFAULT_CENTER
        self._zoom = DEFAULT_ZOOM
        self.update()

    def set_color_by_speed(self, enabled: bool):
        self._color_speed = enabled
        self.update()

    def set_style(self, style: str):
        self.tiles.set_style(style)
        self.update()

    # ---------------------------------------------------------- 视图
    @property
    def zoom(self) -> int:
        return self._zoom

    def zoom_in(self):
        self._zoom_at(min(MAX_ZOOM, self._zoom + 1), QPointF(self.width() / 2, self.height() / 2))

    def zoom_out(self):
        self._zoom_at(max(MIN_ZOOM, self._zoom - 1), QPointF(self.width() / 2, self.height() / 2))

    def _world_origin(self):
        cx, cy = latlon_to_world(self._center[0], self._center[1], self._zoom)
        return cx - self.width() / 2.0, cy - self.height() / 2.0

    def _to_screen(self, lat, lon, origin=None):
        ox, oy = origin if origin else self._world_origin()
        wx, wy = latlon_to_world(lat, lon, self._zoom)
        return QPointF(wx - ox, wy - oy)

    def _screen_to_latlon(self, pos: QPointF):
        ox, oy = self._world_origin()
        return world_to_latlon(pos.x() + ox, pos.y() + oy, self._zoom)

    def _zoom_at(self, new_zoom: int, anchor: QPointF):
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        if new_zoom == self._zoom:
            return
        lat, lon = self._screen_to_latlon(anchor)
        self._zoom = new_zoom
        wx, wy = latlon_to_world(lat, lon, new_zoom)
        cx = wx - anchor.x() + self.width() / 2.0
        cy = wy - anchor.y() + self.height() / 2.0
        self._center = world_to_latlon(cx, cy, new_zoom)
        self.update()

    def fit_track(self):
        all_pts = [p for tr in self._tracks for p in tr["pts"]]
        if not all_pts:
            return
        lat_min = min(p["lat"] for p in all_pts)
        lat_max = max(p["lat"] for p in all_pts)
        lon_min = min(p["lon"] for p in all_pts)
        lon_max = max(p["lon"] for p in all_pts)
        self._center = ((lat_min + lat_max) / 2.0, (lon_min + lon_max) / 2.0)

        w = max(120, self.width() - 48)
        h = max(120, self.height() - 48)
        for z in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
            x1, y1 = latlon_to_world(lat_max, lon_min, z)
            x2, y2 = latlon_to_world(lat_min, lon_max, z)
            if abs(x2 - x1) <= w and abs(y2 - y1) <= h:
                self._zoom = z
                break
        else:
            self._zoom = MIN_ZOOM
        self.update()

    # ---------------------------------------------------------- 绘制
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(COLOR_BG))
        self._draw_tiles(p)
        if any(tr["pts"] for tr in self._tracks):
            self._draw_tracks(p)
        else:
            self._draw_empty(p)
        self._draw_hud(p)
        p.end()

    def _draw_tiles(self, p: QPainter):
        z = self._zoom
        n = 1 << z
        ox, oy = self._world_origin()
        tx0 = math.floor(ox / TILE_SIZE)
        tx1 = math.floor((ox + self.width()) / TILE_SIZE)
        ty0 = math.floor(oy / TILE_SIZE)
        ty1 = math.floor((oy + self.height()) / TILE_SIZE)
        for tx in range(max(0, tx0), min(n - 1, tx1) + 1):
            for ty in range(max(0, ty0), min(n - 1, ty1) + 1):
                rect = QRectF(tx * TILE_SIZE - ox, ty * TILE_SIZE - oy, TILE_SIZE, TILE_SIZE)
                pm = self.tiles.pixmap(z, tx, ty)
                if pm is not None and not pm.isNull():
                    p.drawPixmap(rect, pm, QRectF(pm.rect()))
                else:
                    p.fillRect(rect, QColor("#20242a"))
                    self.tiles.request(z, tx, ty)

    def _draw_tracks(self, p: QPainter):
        origin = self._world_origin()
        single = len(self._tracks) == 1 and self._tracks[0]["color"] is None

        if single:
            tr = self._tracks[0]
            pts = [self._to_screen(s["lat"], s["lon"], origin) for s in tr["pts"]]
            casing = QPainterPath()
            casing.moveTo(pts[0])
            for pt in pts[1:]:
                casing.lineTo(pt)
            p.setPen(QPen(QColor(0, 0, 0, 170), 8))
            p.drawPath(casing)

            if self._color_speed and self._colors:
                buckets: dict[int, QPainterPath] = {}
                for i in range(len(pts) - 1):
                    c = self._colors[i]
                    path = buckets.get(c.rgb())
                    if path is None:
                        path = QPainterPath()
                        buckets[c.rgb()] = path
                    path.moveTo(pts[i])
                    path.lineTo(pts[i + 1])
                for rgb, path in buckets.items():
                    p.setPen(QPen(QColor.fromRgb(rgb), 4))
                    p.drawPath(path)
            else:
                p.setPen(QPen(QColor(*TRACK_SINGLE), 4))
                p.drawPath(casing)

            for pt, color, label in ((pts[0], QColor("#39d353"), "起"), (pts[-1], QColor("#ff5d5d"), "终")):
                p.setPen(QPen(Qt.GlobalColor.white, 2))
                p.setBrush(color)
                p.drawEllipse(pt, 6, 6)
                p.setPen(QColor("#ffffff"))
                f = QFont("Microsoft YaHei UI", 8)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QPointF(pt.x() + 9, pt.y() - 7), label)
            return

        # 多条叠加
        for tr in self._tracks:
            pts = [self._to_screen(s["lat"], s["lon"], origin) for s in tr["pts"]]
            if len(pts) < 2:
                if pts:
                    p.setPen(QPen(Qt.GlobalColor.white, 2))
                    p.setBrush(tr["color"])
                    p.drawEllipse(pts[0], 4, 4)
                continue
            path = QPainterPath()
            path.moveTo(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.setPen(QPen(QColor(0, 0, 0, 120), 5.5))
            p.drawPath(path)
            p.setPen(QPen(tr["color"], 3.2))
            p.drawPath(path)
            p.setPen(QPen(Qt.GlobalColor.white, 1.5))
            p.setBrush(tr["color"])
            p.drawEllipse(pts[0], 4, 4)

        self._draw_legend(p)

    def _draw_legend(self, p: QPainter):
        items = self._tracks[:8]
        f = QFont("Microsoft YaHei UI", 8)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = min(230, max(fm.horizontalAdvance(tr["label"] or "--") for tr in items) + 46)
        h = len(items) * 18 + 14
        box = QRectF(12, 30, w, h)
        p.setPen(QPen(QColor(255, 255, 255, 36), 1))
        p.setBrush(QColor(16, 19, 23, 220))
        p.drawRoundedRect(box, 8, 8)
        for i, tr in enumerate(items):
            y = box.top() + 12 + i * 18
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tr["color"])
            p.drawRoundedRect(QRectF(box.left() + 10, y - 3, 14, 4), 2, 2)
            p.setPen(QColor("#dfe3e8"))
            txt = fm.elidedText(tr["label"] or "--", Qt.TextElideMode.ElideRight, int(w - 40))
            p.drawText(QPointF(box.left() + 30, y + 2), txt)

    def _draw_empty(self, p: QPainter):
        f = QFont("Microsoft YaHei UI", 10)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(self._hint) + 40
        chip = QRectF((self.width() - w) / 2, self.height() / 2 - 20, w, 40)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(18, 21, 26, 215))
        p.drawRoundedRect(chip, 10, 10)
        p.setPen(QColor("#dfe3e8"))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, self._hint)

    def _draw_hud(self, p: QPainter):
        f = QFont("Microsoft YaHei UI", 8)
        p.setFont(f)

        m_per_px = M_PER_PX_EQ * math.cos(math.radians(self._center[0])) / (2 ** self._zoom)
        target = 110.0
        nice = min([5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000],
                   key=lambda m: abs(m / m_per_px - target))
        px = nice / m_per_px
        x, y = 14.0, self.height() - 20.0
        p.setPen(QPen(QColor(255, 255, 255, 220), 3))
        p.drawLine(QPointF(x, y), QPointF(x + px, y))
        p.drawLine(QPointF(x, y - 4), QPointF(x, y + 2))
        p.drawLine(QPointF(x + px, y - 4), QPointF(x + px, y + 2))
        label = f"{nice / 1000:g} km" if nice >= 1000 else f"{nice:g} m"
        p.setPen(QColor("#ffffff"))
        p.drawText(QPointF(x, y - 7), label)

        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QPointF(self.width() - 70, self.height() - 8), "© 高德地图")

        p.setPen(QColor(200, 210, 225))
        txt = f"{self._hover[0]:.5f}, {self._hover[1]:.5f}" if self._hover else f"Z{self._zoom}"
        p.drawText(QPointF(14, 18), txt)

    # ---------------------------------------------------------- 交互
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_center = latlon_to_world(self._center[0], self._center[1], self._zoom)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_start is not None:
            dx = pos.x() - self._drag_start.x()
            dy = pos.y() - self._drag_start.y()
            self._center = world_to_latlon(self._drag_center[0] - dx,
                                           self._drag_center[1] - dy, self._zoom)
            self._hover = None
            self.update()
        else:
            self._hover = self._screen_to_latlon(pos)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._drag_center = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self._zoom_at(self._zoom + (1 if delta > 0 else -1), event.position())
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._zoom_at(self._zoom + 1, event.position())

    def _on_tile(self, key: str):
        self.update()

    def sizeHint(self):
        return QSize(900, 520)
