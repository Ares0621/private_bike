"""骑行热力图：把一段时间内的全部轨迹叠到一张深色地图上，重复骑过的路段自动更红。

纯 Qt 绘制（不用 HTML），底图走高德栅格瓦片并缓存到 data/tiles/<style>/...，
输出 QImage，可直接存 PNG 或显示在窗口里。
"""
import math
import os
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath,
                         QPen, QPolygonF, QRadialGradient)

from .config import TILE_DIR, TILE_STYLES
from .coords import is_gcj_style, wgs84_to_gcj02

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
REFERER = "https://www.amap.com/"

TILE = 256
MIN_ZOOM, MAX_ZOOM = 10, 16

# 热度分档：重复次数 -> 档位（1 最冷，越高越红越粗）
BUCKETS = (1, 2, 3, 4, 6, 9, 14, 20)
# 每档颜色（暗红 -> 亮红 -> 微橙）
LEVEL_COLORS = ("#a51414", "#bb1c1c", "#d42323", "#e82b28", "#f43a2e", "#fb4a35",
                "#ff5f3a", "#ff7a45")
LEVEL_WIDTH = (1.35, 1.5, 1.7, 1.95, 2.2, 2.45, 2.7, 3.0)
LEVEL_ALPHA = (205, 214, 222, 230, 236, 242, 248, 252)

BG_COLOR = "#06070a"

# 街道线稿参数（把高德路网瓦片里的描边抽成灰线，黑底上画网格）
LINE_WHITE_MIN = 252  # 最小通道亮度阈值（道路填充是纯白）
LINE_CHROMA_MAX = 4   # 彩度上限（底色偏米黄，彩度更大，会被排除）
LINE_FLOOR = 14       # 线稿底色（近乎纯黑）
LINE_AMP = 132        # 街线亮度
LINE_TEXT_DARK = 170  # 亮度低于它算「有这个像素内容」（文字/图标/楼房）
LINE_TEXT_GUARD = 0   # 高德线稿里的文字处理半径（0=不处理；默认底图已换成 Esri 深灰）
ESRI_ROAD_DELTA = 9   # 比地面（中位亮度）再亮多少才算道路
ESRI_MIN_NEIGHBORS = 2  # 至少几个相邻像素才算路（去掉孤立亮点）
ESRI_THICKEN = 1      # 街道加粗轮数
ESRI_FLOOR = 13       # 底色
ESRI_AMP = 118        # 街道亮度
LINE_THICKEN = 1      # 街线加粗轮数


# ----------------------------------------------------------------- 投影
def _merc_px(lon: float, lat: float, z: int) -> tuple[float, float]:
    """经纬度 -> 世界像素坐标（Web 墨卡托，原点在左上）。"""
    world = TILE * (2 ** z)
    x = (lon + 180.0) / 360.0 * world
    lat_r = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * world
    return x, y


# ----------------------------------------------------------------- 数据筛选
def filter_rides(rides: list[dict], mode: str = "all", year: str | None = None,
                 month: int | None = None) -> list[dict]:
    out = []
    for r in rides:
        st = (r.get("start_time") or "")[:10]
        if len(st) < 7:
            continue
        if mode == "year" and year and st[:4] != str(year):
            continue
        if mode == "month":
            if year and st[:4] != str(year):
                continue
            if month and int(st[5:7]) != int(month):
                continue
        out.append(r)
    return out


def range_label(mode: str, year: str | None, month: int | None) -> str:
    if mode == "year" and year:
        return f"{year} 年度"
    if mode == "month" and month:
        return f"{year or ''} 年 {int(month)} 月".strip()
    return "全部记录"


def load_tracks(db, mode: str = "all", year: str | None = None,
                month: int | None = None, progress=None) -> tuple[list, dict]:
    """读取筛选后的轨迹点，返回 (tracks, 概要)。

    tracks: [(ride_id, [(lon, lat), ...]), ...]
    """
    rides = filter_rides(db.list_rides(), mode, year, month)
    tracks = []
    total_km = 0.0
    skipped = 0
    for n, r in enumerate(rides, 1):
        pts = []
        for s in db.get_samples(r["id"]):
            lon, lat = s.get("lon"), s.get("lat")
            if lon is None or lat is None:
                continue
            pts.append((float(lon), float(lat)))
        if len(pts) < 2:
            skipped += 1
            continue
        tracks.append((r["id"], pts))
        total_km += (r.get("distance_m") or 0.0) / 1000.0
        if progress and n % 5 == 0:
            progress(n, len(rides), f"读取轨迹 {n}/{len(rides)}")
    return tracks, {"rides": len(tracks), "total_km": total_km, "skipped": skipped,
                    "candidates": len(rides)}


# ----------------------------------------------------------------- 瓦片
def _tile_path(style: str, z: int, x: int, y: int):
    return TILE_DIR / style / str(z) / str(x) / f"{y}.png"


def _fetch_one(style: str, z: int, x: int, y: int) -> QImage | None:
    path = _tile_path(style, z, x, y)
    if path.exists() and path.stat().st_size > 600:
        img = QImage(str(path))
        if not img.isNull():
            return img
    sub = random.randint(1, 4)
    tmpl = TILE_STYLES.get(style, TILE_STYLES["road"])
    url = tmpl.format(s=sub, x=x, y=y, z=z)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Referer": REFERER, "Accept": "image/*,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 600:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f"{path.stem}.{random.getrandbits(24)}.tmp"
        tmp.write_bytes(data)
        try:
            os.replace(tmp, path)
        except OSError:
            tmp.unlink(missing_ok=True)
        img = QImage()
        if img.loadFromData(data) and not img.isNull():
            return img
    except Exception:  # noqa: BLE001
        return None
    return None


def _build_base(w: int, h: int, z: int, origin_x: float, origin_y: float,
                style: str, progress=None) -> QImage:
    """拼底图：dark = Esri 深灰街道（无地名）；line = 高德路网线稿；sat = 卫星图压暗。"""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(BG_COLOR))

    tx0 = int(origin_x // TILE)
    tx1 = int((origin_x + w) // TILE) + 1
    ty0 = int(origin_y // TILE)
    ty1 = int((origin_y + h) // TILE) + 1
    keys = [(x, y) for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1)]
    tile_style = {"dark": "esri_dark", "line": "road", "sat": "sat"}.get(style, "esri_dark")

    total = len(keys)
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(_fetch_one, tile_style, z, x, y) for x, y in keys]
        tiles = []
        for fu in futures:
            tiles.append(fu.result())
            done += 1
            if progress and done % 8 == 0:
                progress(done, total, f"下载底图瓦片 {done}/{total}")

    # 先把瓦片不透明地拼到临时图上，再整体压暗一次：
    # 这样相邻瓦片即使有重叠也不会叠加出亮边
    tmp = QImage(w, h, QImage.Format.Format_RGB32)
    tmp.fill(QColor("#000000"))
    q = QPainter(tmp)
    for (x, y), til in zip(keys, tiles):
        if til is None or til.isNull():
            continue
        q.drawImage(int(x * TILE - origin_x), int(y * TILE - origin_y), til)
    q.end()

    if style == "dark":
        base_img = _esri_darken(tmp)
    elif style == "line":
        base_img = _line_ink(tmp)
    else:
        base_img = _desaturate_darken(tmp, gray=0.72, dim=0.52)

    p = QPainter(img)
    p.drawImage(0, 0, base_img)
    if style == "sat":
        p.setOpacity(0.18)
        p.setBrush(QColor(BG_COLOR))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, w, h)
    p.end()
    return img


def _blur3(x: np.ndarray) -> np.ndarray:
    px = np.pad(x, 1, mode="edge")
    acc = np.zeros_like(x)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            acc += px[dy:dy + x.shape[0], dx:dx + x.shape[1]]
    return acc / 9.0


def _sobel(x: np.ndarray) -> np.ndarray:
    px = np.pad(x, 1, mode="edge")
    gx = (px[:-2, 2:] + 2 * px[1:-1, 2:] + px[2:, 2:]) - (px[:-2, :-2] + 2 * px[1:-1, :-2] + px[2:, :-2])
    gy = (px[2:, :-2] + 2 * px[2:, 1:-1] + px[2:, 2:]) - (px[:-2, :-2] + 2 * px[:-2, 1:-1] + px[:-2, 2:])
    return np.hypot(gx, gy) / 4.0


def _esri_darken(src: QImage) -> QImage:
    """Esri 深灰底图 → 纯街道线稿。

    Esri 的「深灰画布」本身已经是暗底，地面亮度约 60、路网约 75~105、水体更暗；
    地名字形是细碎的笔画像素，亮度落在路网区间里但不连续。这里直接按亮度取「比地面亮」
    的像素当道路，统一涂成同一种灰，地面/水体/地名都不画 —— 于是只剩街道网。
    """
    img = src.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    buf = img.constBits()
    buf.setsize(img.sizeInBytes())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :3]
    px = arr.astype(np.float32)
    lum = px[:, :, 2] * 0.299 + px[:, :, 1] * 0.587 + px[:, :, 0] * 0.114

    thr = float(np.median(lum)) + ESRI_ROAD_DELTA   # 地面≈中位数，道路比它更亮
    road = lum >= thr
    if ESRI_MIN_NEIGHBORS > 0:
        # 去掉孤立亮点（建筑描边碎屑），保留成线的像素
        around = np.zeros(road.shape, dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                around += np.roll(np.roll(road, dy, 0), dx, 1).astype(np.int16)
        road = road & (around >= ESRI_MIN_NEIGHBORS)
    if ESRI_THICKEN > 0:
        road = _dilate(road, ESRI_THICKEN)
    gray = ESRI_FLOOR + ESRI_AMP * road.astype(np.float32)
    res = np.dstack([gray * 0.99, gray, gray * 1.01, np.full_like(gray, 255)]).astype(np.uint8)
    return QImage(np.ascontiguousarray(res).data, w, h, w * 4,
                  QImage.Format.Format_RGB32).copy()


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """正方形结构元膨胀（r 圈），用 numpy 平移取最大值实现。"""
    out = mask
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            out = out | np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    """正方形结构元腐蚀（r 圈）。"""
    out = mask
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            out = out & np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def _line_ink(src: QImage) -> QImage:
    """把路网瓦片变成「只有街道」的线稿，不保留任何文字/图标。

    做法：高德的道路填充是纯白且几乎无彩度（底色是微米黄），所以先按「最小通道 ≥ 250
    且彩度 ≤ 4」取出道路；再用亮度 < 205 的像素（文字、图标、楼房）膨胀出「禁区」，
    把落在禁区里的道路像素（也就是文字描边、图标白框）一起挖掉；最后把线加粗一圈。
    """
    img = src.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    buf = img.constBits()
    buf.setsize(img.sizeInBytes())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :3]
    b, g, r = arr[:, :, 0].astype(np.int16), arr[:, :, 1].astype(np.int16), arr[:, :, 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    chroma = mx - mn
    import numpy as _np
    lum = r * 0.299 + g * 0.587 + b * 0.114

    road = (mn >= LINE_WHITE_MIN) & (chroma <= LINE_CHROMA_MAX)
    if LINE_TEXT_GUARD > 0:
        texty = _dilate(lum < LINE_TEXT_DARK, LINE_TEXT_GUARD)
        # 文字区域内把道路「闭合」补回来：先膨胀再收缩，跨过文字留下的缺口
        closed = _erode(_dilate(road, LINE_TEXT_GUARD + 1), LINE_TEXT_GUARD + 1)
        road = (road & ~texty) | (closed & texty)
    if LINE_THICKEN > 0:
        road = _dilate(road, LINE_THICKEN)

    gray = LINE_FLOOR + LINE_AMP * road.astype(np.float32)
    res = np.dstack([gray, gray, gray, np.full_like(gray, 255)]).astype(np.uint8)
    return QImage(_np.ascontiguousarray(res).data, w, h, w * 4,
                  QImage.Format.Format_RGB32).copy()


def _desaturate_darken(src: QImage, gray: float = 0.72, dim: float = 0.52) -> QImage:
    """卫星图底图处理：往灰度方向拉 `gray` 比例，再整体乘 `dim` 压暗。"""
    img = src.convertToFormat(QImage.Format.Format_RGB32)
    w, h = img.width(), img.height()
    buf = img.constBits()
    buf.setsize(img.sizeInBytes())
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4).copy()
    px = arr[:, :w, :3].astype(np.float32)          # 内存里是 BGRA
    lum = px[:, :, 2] * 0.299 + px[:, :, 1] * 0.587 + px[:, :, 0] * 0.114
    lum = lum[:, :, None]
    out = (px * (1.0 - gray) + lum * gray) * dim
    arr[:, :w, :3] = np.clip(out, 0, 255).astype(np.uint8)
    arr = np.ascontiguousarray(arr)
    out_img = QImage(arr.data, w, h, img.bytesPerLine(), QImage.Format.Format_RGB32)
    return out_img.copy()


# ----------------------------------------------------------------- 热度
def _heat_counts(sx: np.ndarray, sy: np.ndarray, cols: int, rows: int,
                 cell: float, tracks: list, z: int, origin_x: float,
                 origin_y: float) -> np.ndarray:
    """每个格子被多少条不同骑行经过（同一条骑重复经过同格只算一次）。"""
    grid = np.zeros((rows, cols), dtype=np.int32)
    for _rid, pts in tracks:
        lons = np.fromiter((p[0] for p in pts), dtype=np.float64, count=len(pts))
        lats = np.fromiter((p[1] for p in pts), dtype=np.float64, count=len(pts))
        px, py = _merc_px_arr(lons, lats, z)
        cx = ((px - origin_x) / cell).astype(np.int32)
        cy = ((py - origin_y) / cell).astype(np.int32)
        np.clip(cx, 0, cols - 1, out=cx)
        np.clip(cy, 0, rows - 1, out=cy)
        flat = np.unique(cy * cols + cx)
        np.add.at(grid.reshape(-1), flat, 1)
    return grid


def _merc_px_arr(lons: np.ndarray, lats: np.ndarray, z: int):
    world = TILE * (2 ** z)
    x = (lons + 180.0) / 360.0 * world
    lat_r = np.radians(lats)
    y = (1.0 - np.log(np.tan(lat_r) + 1.0 / np.cos(lat_r)) / np.pi) / 2.0 * world
    return x, y


def _level_of(count: int) -> int:
    lv = 0
    for i, b in enumerate(BUCKETS):
        if count >= b:
            lv = i
    return lv


# ----------------------------------------------------------------- 主入口
@dataclass
class HeatSpec:
    mode: str = "all"
    year: str | None = None
    month: int | None = None
    style: str = "dark"        # dark / sat
    target_px: int = 1500      # 目标画布宽度
    detail: int = 1            # 线宽倍率
    show_title: bool = True
    subtitle: str = ""


@dataclass
class HeatResult:
    image: QImage
    stats: dict
    meta: dict = field(default_factory=dict)


def render(db, spec: HeatSpec, progress=None) -> HeatResult:
    tracks, info = load_tracks(db, spec.mode, spec.year, spec.month, progress)
    if not tracks:
        raise ValueError("这个时间范围内没有带 GPS 轨迹的骑行记录")

    # 底图坐标系对齐：高德瓦片（sat / line）是 GCJ-02，Esri 是 WGS-84
    tile_style = {"dark": "esri_dark", "line": "road", "sat": "sat"}.get(spec.style, "esri_dark")
    coord_name = "WGS-84"
    if is_gcj_style(tile_style):
        coord_name = "GCJ-02"
        conv = []
        for rid, pts in tracks:
            conv.append((rid, [(g[1], g[0]) for g in
                             (wgs84_to_gcj02(p[1], p[0]) for p in pts)]))
        tracks = conv

    # 1) 范围与缩放级别
    lons = [p[0] for _i, pts in tracks for p in pts]
    lats = [p[1] for _i, pts in tracks for p in pts]
    lon0, lon1 = min(lons), max(lons)
    lat0, lat1 = min(lats), max(lats)
    # 缩放级别：按「总像素预算」逐级下降，保证整条轨迹完整落进画布且不被缩放裁掉
    budget_px = int(6_500_000 * (spec.target_px / 1200.0) ** 2)
    budget_px = min(budget_px, 30_000_000)
    max_side = min(int(spec.target_px * 3.0), 8000)
    z = MAX_ZOOM
    while z > MIN_ZOOM:
        x0, y1 = _merc_px(lon0, lat0, z)
        x1, y0 = _merc_px(lon1, lat1, z)
        span_x, span_y = x1 - x0, y1 - y0
        pad = max(56.0, 0.07 * max(span_x, span_y))
        cand_w = int(span_x + 2 * pad)
        cand_h = int(span_y + 2 * pad)
        if max(cand_w, cand_h) <= max_side and cand_w * cand_h <= budget_px:
            break
        z -= 1
    x0, y1 = _merc_px(lon0, lat0, z)
    x1, y0 = _merc_px(lon1, lat1, z)
    span_x, span_y = x1 - x0, y1 - y0
    pad = max(56.0, 0.07 * max(span_x, span_y))
    ox, oy = x0 - pad, y0 - pad
    w = int(span_x + 2 * pad)
    h = int(span_y + 2 * pad)
    w, h = max(w, 600), max(h, 600)

    # 底部留白放署名与统计
    foot = 64
    canvas_h = h + foot

    if progress:
        progress(0, 3, "拼底图…")
    base = _build_base(w, h, z, ox, oy, spec.style, progress)

    # 2) 热度网格
    cell = 8.0
    cols = max(1, int(math.ceil(w / cell)))
    rows = max(1, int(math.ceil(h / cell)))
    if progress:
        progress(1, 3, "累计热度…")
    grid = _heat_counts(None, None, cols, rows, cell, tracks, z, ox, oy)

    # 3) 逐点取热度、按档位画线
    if progress:
        progress(2, 3, "绘制轨迹…")
    chains: dict[int, list[QPolygonF]] = {}
    max_repeat = int(grid.max()) if grid.size else 0
    for _rid, pts in tracks:
        lons_np = np.fromiter((p[0] for p in pts), dtype=np.float64, count=len(pts))
        lats_np = np.fromiter((p[1] for p in pts), dtype=np.float64, count=len(pts))
        px, py = _merc_px_arr(lons_np, lats_np, z)
        cx = np.clip(((px - ox) / cell).astype(np.int32), 0, cols - 1)
        cy = np.clip(((py - oy) / cell).astype(np.int32), 0, rows - 1)
        cnt = grid[cy, cx]
        levels = np.array([_level_of(int(c)) for c in cnt], dtype=np.int8)
        xs = px - ox
        ys = py - oy
        i = 0
        n = len(xs)
        while i < n - 1:
            lv = int(levels[i])
            j = i
            while j < n - 2 and int(levels[j + 1]) == lv:
                j += 1
            stop = min(j + 1, n - 1)
            poly = QPolygonF([QPointF(float(xs[k]), float(ys[k]))
                              for k in range(i, stop + 1)])
            chains.setdefault(lv, []).append(poly)
            i = stop

    img = QImage(w, canvas_h, QImage.Format.Format_RGB32)
    img.fill(QColor(BG_COLOR))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.drawImage(0, 0, base)
    vig = QRadialGradient(QPointF(w / 2, h * 0.45), max(w, h) * 0.75)
    vig.setColorAt(0.0, QColor(0, 0, 0, 0))
    vig.setColorAt(0.55, QColor(0, 0, 0, 18))
    vig.setColorAt(1.0, QColor(0, 0, 0, 170))
    p.fillRect(QRectF(0, 0, w, h), vig)

    wk = max(1.0, min(1.9, max(w, h) / 1900.0))     # 大画布按比例加粗，导出的细线不至于看不见

    # 先画一层很淡的整体轨迹，让没被重复的路段也有存在感
    p.setPen(QPen(QColor(150, 32, 32, 110), 2.4 * spec.detail * wk))
    for lv in sorted(chains):
        for poly in chains[lv]:
            p.drawPolyline(poly)

    # 再按档位从冷到热叠上去
    for lv in sorted(chains):
        color = QColor(LEVEL_COLORS[lv])
        alpha = LEVEL_ALPHA[lv]
        color.setAlpha(alpha)
        width = LEVEL_WIDTH[lv] * spec.detail * wk
        glow = QColor(LEVEL_COLORS[lv])
        glow.setAlpha(70 if lv >= 4 else 42)
        p.setPen(QPen(glow, width * (3.2 if lv >= 4 else 2.4)))
        for poly in chains[lv]:
            p.drawPolyline(poly)
        p.setPen(QPen(color, width))
        for poly in chains[lv]:
            p.drawPolyline(poly)
    p.end()

    # 4) 文字：标题 + 底部统计
    if spec.show_title or True:
        p = QPainter(img)
        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(QColor("#ffffff"))
        title = spec.subtitle or range_label(spec.mode, spec.year, spec.month)
        p.drawText(QPointF(22, 34), f"{title} 骑行热力图")

        small = QFont("Microsoft YaHei UI", 8)
        p.setFont(small)
        fm = QFontMetrics(small)
        stat = (f"总里程 {info['total_km']:.1f} km · 骑行 {info['rides']} 次 · "
                f"最高重复 {max_repeat} 次")
        p.setPen(QColor("#c9ced6"))
        p.drawText(QPointF(22, canvas_h - 26), stat)

        brand = QFont("Microsoft YaHei UI", 9)
        brand.setBold(True)
        p.setFont(brand)
        p.setPen(QColor("#ff4a3d"))
        p.drawText(QPointF(22, canvas_h - 8), "PrivateBike")

        p.setFont(small)
        p.setPen(QColor("#8b929c"))
        base_name = {"esri_dark": "Esri 深灰街道", "road": "高德路网", "sat": "高德卫星"}[tile_style]
        right = f"{base_name} · {coord_name} · z{z} · {w}×{h}"
        p.drawText(QPointF(w - 22 - fm.horizontalAdvance(right), canvas_h - 8), right)
        p.end()

    return HeatResult(image=img, stats={
        "rides": info["rides"], "total_km": info["total_km"],
        "max_repeat": max_repeat, "width": w, "height": canvas_h,
        "zoom": z, "skipped": info["skipped"], "candidates": info["candidates"],
    }, meta={"zoom": z, "bbox": (lon0, lat0, lon1, lat1), "coord": coord_name,
             "tile": tile_style})
