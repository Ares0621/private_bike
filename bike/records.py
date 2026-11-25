"""个人最佳与里程碑：全部由骑行记录现算，不新增数据表。

- bests：单项纪录（最长距离、最长时长、最大爬升、最高均速、最高极速、单月最大里程…）
- badges：可累积的阶梯成就，每个阶梯都能算出「第一次达成是哪天」（用时间正序累计值逐条判定）
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

# 阶梯定义：(key, 名称, 单位, 阶梯列表, 口径)
# 口径 cum = 累计型（沿时间累加）；max = 单次/单月极值型；streak = 连续天数型
TIERS = [
    ("total_km", "累计里程", "km", (100, 500, 1000, 2000, 5000, 10000), "cum"),
    ("rides", "骑行次数", "次", (10, 50, 100, 200, 500), "cum"),
    ("total_elev", "累计爬升", "m", (1000, 5000, 10000, 20000, 50000), "cum"),
    ("single_km", "单次距离", "km", (30, 50, 100, 150, 200), "max"),
    ("single_elev", "单次爬升", "m", (300, 500, 1000, 2000), "max"),
    ("single_speed", "单次均速", "km/h", (18, 20, 22, 25, 30), "max"),
    ("streak", "连续骑行", "天", (3, 7, 14, 30, 100), "streak"),
    ("month_km", "单月里程", "km", (100, 200, 300, 500, 1000), "max"),
    ("active_months", "活跃月份", "个月", (6, 12, 24, 36), "cum"),
]


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _num(v) -> float:
    return float(v) if v is not None else 0.0


def _fmt(v: float, unit: str) -> str:
    if unit == "km/h":
        return f"{v:.1f}"
    if unit == "m":
        return f"{v:,.0f}"
    if unit in ("次", "天", "个月"):
        return f"{v:,.0f}"
    return f"{v:,.1f}"


def _short(d: date | None) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


# ----------------------------------------------------------------- 单项纪录
def _bests(rides: list[dict]) -> list[dict]:
    out: list[dict] = []

    def pick(item, value: float, sub: str = ""):
        if value and value > 0:
            out.append({
                "label": item,
                "value": value,
                "sub": sub,
                "date": (row.get("start_time") or "")[:10],
                "title": row.get("title") or "",
                "ride_id": row.get("id"),
            })

    # 最长距离
    row = max(rides, key=lambda r: _num(r.get("distance_m")) or 0)
    pick("单次最长距离", _num(row.get("distance_m")) / 1000.0, "km")
    # 最长时长
    row = max(rides, key=lambda r: _num(r.get("duration_s")) or 0)
    pick("单次最长时长", _num(row.get("duration_s")) / 3600.0, "h")
    # 最大爬升
    row = max(rides, key=lambda r: _num(r.get("elev_gain_m")) or 0)
    pick("单次累计爬升", _num(row.get("elev_gain_m")), "m")
    # 最快均速（只算 10km 以上，短距离均速没有可比性）
    long_rides = [r for r in rides if _num(r.get("distance_m")) >= 10000 and _num(r.get("avg_speed")) > 0]
    if long_rides:
        row = max(long_rides, key=lambda r: _num(r.get("avg_speed")))
        pick("最快平均速度", _num(row.get("avg_speed")) * 3.6, "km/h")
    # 极速
    row = max(rides, key=lambda r: _num(r.get("max_speed")) or 0)
    pick("单次最高速度", _num(row.get("max_speed")) * 3.6, "km/h")
    # 最大消耗
    row = max(rides, key=lambda r: _num(r.get("calories")) or 0)
    pick("单次最大消耗", _num(row.get("calories")), "kcal")

    # 单月口径
    months: dict[str, dict] = {}
    for r in rides:
        st = r.get("start_time") or ""
        if len(st) < 7:
            continue
        ym = st[:7]
        m = months.setdefault(ym, {"dist": 0.0, "elev": 0.0, "rides": 0, "moving": 0.0,
                                   "max_ride": 0.0, "title": ""})
        m["dist"] += _num(r.get("distance_m"))
        m["elev"] += _num(r.get("elev_gain_m"))
        m["rides"] += 1
        m["moving"] += _num(r.get("moving_s"))
        d = _num(r.get("distance_m"))
        if d > m["max_ride"]:
            m["max_ride"] = d
            m["title"] = r.get("title") or ""
    if months:
        ym = max(months, key=lambda k: months[k]["dist"])
        out.append({"label": "单月最大里程", "value": months[ym]["dist"] / 1000.0, "sub": "km",
                    "date": ym, "title": f"{months[ym]['rides']} 次骑行", "ride_id": None})
        ym = max(months, key=lambda k: months[k]["rides"])
        out.append({"label": "单月最多骑行", "value": float(months[ym]["rides"]), "sub": "次",
                    "date": ym, "title": f"{months[ym]['dist'] / 1000:.1f} km", "ride_id": None})

    # 年度里程
    years: dict[str, float] = {}
    for r in rides:
        st = r.get("start_time") or ""
        if len(st) >= 4:
            years[st[:4]] = years.get(st[:4], 0.0) + _num(r.get("distance_m"))
    if years:
        y = max(years, key=lambda k: years[k])
        out.append({"label": "年度最大里程", "value": years[y] / 1000.0, "sub": "km",
                    "date": y, "title": f"{y} 年", "ride_id": None})

    # 连续骑行天数
    streak, streak_end = _streak(rides)
    if streak:
        out.append({"label": "最长连续骑行", "value": float(streak), "sub": "天",
                    "date": _short(streak_end), "title": f"截至 {_short(streak_end)}",
                    "ride_id": None})
    return out


def _dates(rides: list[dict]) -> list[date]:
    ds = []
    for r in rides:
        d = _dt(r.get("start_time"))
        if d:
            ds.append(d.date())
    return sorted(ds)


def _streak(rides: list[dict]) -> tuple[int, date | None]:
    ds = _dates(rides)
    best, best_end = 0, None
    cur, prev = 1, None
    for d in ds:
        if prev is not None:
            if d == prev:
                continue
            if d - prev == timedelta(days=1):
                cur += 1
            else:
                cur = 1
        prev = d
        if cur > best:
            best, best_end = cur, d
    return best, best_end


# ----------------------------------------------------------------- 里程碑
def _cum_series(rides: list[dict], field: str) -> list[tuple[datetime, float]]:
    """时间正序的累计序列 (时间, 到这一刻的累计值)。"""
    rows = []
    for r in rides:
        t = _dt(r.get("start_time"))
        v = _num(r.get(field))
        if t is None:
            continue
        rows.append((t, v))
    rows.sort(key=lambda x: x[0])
    acc, out = 0.0, []
    for t, v in rows:
        acc += v
        out.append((t, acc))
    return out


def _max_series(rides: list[dict], field: str, scale: float = 1.0) -> list[tuple[datetime, float]]:
    rows = []
    for r in rides:
        t = _dt(r.get("start_time"))
        v = _num(r.get(field))
        if t is None or v <= 0:
            continue
        if field == "avg_speed" and _num(r.get("distance_m")) < 10000:
            continue
        rows.append((t, v * scale))
    rows.sort(key=lambda x: x[0])
    return rows


def _streak_series(rides: list[dict]) -> list[tuple[datetime, float]]:
    ds = _dates(rides)
    out, cur, prev = [], 0, None
    for d in ds:
        if prev is not None and d == prev:
            continue
        cur = cur + 1 if (prev is not None and d - prev == timedelta(days=1)) else 1
        prev = d
        out.append((datetime.combine(d, datetime.min.time()), float(cur)))
    return out


def _month_series(rides: list[dict], key: str) -> list[tuple[datetime, float]]:
    months: dict[str, dict] = {}
    for r in rides:
        st = r.get("start_time") or ""
        if len(st) < 7:
            continue
        m = months.setdefault(st[:7], {"dist": 0.0, "rides": 0})
        m["dist"] += _num(r.get("distance_m"))
        m["rides"] += 1
    rows = [(datetime.strptime(ym, "%Y-%m"), (v["dist"] / 1000.0 if key == "dist" else float(v["rides"])))
            for ym, v in months.items()]
    rows.sort(key=lambda x: x[0])
    return rows


def _tier_dates(series: list[tuple[datetime, float]], tiers) -> list[tuple[float, date | None]]:
    """每个阶梯第一次达到的日期（series 需按时间正序；max 型直接用各条记录的值判定）。"""
    out, idx = [], 0
    for tier in tiers:
        hit = None
        while idx < len(series):
            t, v = series[idx]
            if v >= tier:
                hit = t.date()
                break
            idx += 1
        out.append((tier, hit))
        if hit is None:
            idx = len(series)
    return out


def compute(db) -> dict:
    rides = db.list_rides()
    totals = {
        "rides": len(rides),
        "km": sum(_num(r.get("distance_m")) for r in rides) / 1000.0,
        "elev": sum(_num(r.get("elev_gain_m")) for r in rides),
        "moving_h": sum(_num(r.get("moving_s")) for r in rides) / 3600.0,
        "days": len(set(_dates(rides))),
        "years": sorted({(r.get("start_time") or "0000")[:4] for r in rides if r.get("start_time")}),
    }
    streak, _e = _streak(rides)

    series_map = {
        "total_km": _cum_series(rides, "distance_m"),
        "rides": _cum_series([dict(r, _one=1.0) for r in rides], "_one"),
        "total_elev": _cum_series(rides, "elev_gain_m"),
        "single_km": _max_series(rides, "distance_m"),
        "single_elev": _max_series(rides, "elev_gain_m"),
        "single_speed": _max_series(rides, "avg_speed"),
        "streak": _streak_series(rides),
        "month_km": _month_series(rides, "dist"),
        "active_months": [(d, float(i)) for i, (d, _v) in
                          enumerate(_month_series(rides, "rides"), 1)],
    }
    # 单位换算：累计里程、单次里程按 km 展示；其它按原单位
    scale_map = {"total_km": 1 / 1000.0, "single_km": 1 / 1000.0,
                 "single_speed": 3.6}   # 库里速度是 m/s

    badges = []
    for key, name, unit, tiers, kind in TIERS:
        raw = series_map[key]
        scale = scale_map.get(key, 1.0)
        series = [(t, v * scale) for t, v in raw]
        cur = max((v for _t, v in series), default=0.0)
        tds = _tier_dates(series, tiers)
        achieved = [(tier, d) for tier, d in tds if d is not None]
        nxt = next((tier for tier, d in tds if d is None), None)
        badges.append({
            "key": key, "name": name, "unit": unit, "kind": kind,
            "current": cur, "tiers": tiers, "achieved": achieved, "next": nxt,
            "ratio": (cur / nxt if nxt else 1.0),
        })

    return {
        "totals": totals, "streak": streak,
        "bests": _bests(rides),
        "badges": badges,
    }
