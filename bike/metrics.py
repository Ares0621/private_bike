"""骑行数据清洗与统计计算（距离、爬升、有效骑行时间、速度/心率/踏频/功率等）。"""
import math

R_EARTH = 6371000.0

# 有效骑行时间（用时）只统计瞬时速度超过该阈值的时段，红绿灯/推车/休息不计入
MOVING_MIN_SPEED_KMH = 5.0
MOVING_MIN_SPEED = MOVING_MIN_SPEED_KMH / 3.6


def haversine(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _smooth(values, window=3):
    """滑动平均，忽略 None。"""
    out = []
    n = len(values)
    half = max(0, window // 2)
    for i in range(n):
        acc, cnt = 0.0, 0
        for j in range(max(0, i - half), min(n, i + half + 1)):
            v = values[j]
            if v is not None:
                acc += v
                cnt += 1
        out.append(acc / cnt if cnt else None)
    return out


def _pct(values, q):
    if not values:
        return None
    vals = sorted(values)
    k = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))
    return vals[k]


def normalize(samples):
    """补齐时间、距离、速度，剔除异常跳点，就地修改并返回样本列表。"""
    if not samples:
        return samples

    # 时间序列：去重、单调
    last_t = None
    for s in samples:
        t = s.get("t")
        if t is None:
            t = (last_t or 0.0)
        if last_t is not None and t < last_t:
            t = last_t
        s["t"] = t
        last_t = t

    # 地理距离
    geo = [0.0]
    prev = None
    for s in samples:
        lat, lon = s.get("lat"), s.get("lon")
        if prev is not None and lat is not None and lon is not None:
            step = haversine(prev[0], prev[1], lat, lon)
            dt = (s["t"] - prev[2]) if prev[2] is not None else 1
            # 过滤 GPS 漂移：瞬时速度 > 120km/h 视为跳点
            if dt > 0 and step / max(dt, 0.1) > 33.0:
                step = 0.0
            geo.append(geo[-1] + step)
        else:
            geo.append(geo[-1])
        prev = (lat, lon, s["t"]) if lat is not None and lon is not None else prev

    # 距离字段（FIT 自带 distance）
    has_dist = any(s.get("dist") for s in samples)
    if not has_dist:
        for s, d in zip(samples, geo):
            s["dist"] = d
    else:
        for s, d in zip(samples, geo):
            if s.get("dist") is None:
                s["dist"] = d

    # 速度：缺失则用距离差推导
    for i, s in enumerate(samples):
        if s.get("speed") is not None:
            continue
        if i == 0:
            s["speed"] = None
            continue
        dt = s["t"] - samples[i - 1]["t"]
        dd = (s.get("dist") or 0) - (samples[i - 1].get("dist") or 0)
        s["speed"] = dd / dt if dt > 0.5 else None

    speeds = _smooth([s.get("speed") for s in samples], 3)
    for s, v in zip(samples, speeds):
        s["speed"] = v
    return samples


def moving_time(samples):
    """有效骑行时间：只累计瞬时速度 > 5 km/h 的时段。

    返回 (有效秒数, 该时段内的里程米)。红绿灯、推车、休息、
    以及信号中断的长间隔（dt>30s）都不计入。
    """
    moving = 0.0
    fast_dist = 0.0
    for a, b in zip(samples, samples[1:]):
        dt = b["t"] - a["t"]
        sp = b.get("speed") or 0.0
        if 0 < dt <= 30 and sp > MOVING_MIN_SPEED:
            moving += dt
            fast_dist += max(0.0, (b.get("dist") or 0.0) - (a.get("dist") or 0.0))
    return moving, fast_dist


def compute_stats(samples, session=None) -> dict:
    """计算骑行统计。返回 dict（均为 SI 单位：米、秒、m/s）。"""
    session = session or {}
    samples = normalize(samples)
    stats = {
        "duration_s": 0.0, "moving_s": 0.0, "distance_m": 0.0,
        "elev_gain_m": 0.0, "elev_loss_m": 0.0,
        "avg_speed": 0.0, "max_speed": 0.0,
        "avg_hr": None, "max_hr": None,
        "avg_cadence": None, "max_cadence": None,
        "avg_power": None, "max_power": None, "calories": None,
    }
    if not samples:
        return stats

    t0, t1 = samples[0]["t"], samples[-1]["t"]
    stats["duration_s"] = max(0.0, t1 - t0)
    stats["distance_m"] = max((s.get("dist") or 0.0) for s in samples)

    # 有效骑行时间：只累计速度 > 5 km/h 的时段（信号丢失的长间隔也不计入）
    moving, fast_dist = moving_time(samples)
    stats["moving_s"] = moving or stats["duration_s"]

    # 爬升 / 下降（1m 迟滞，过滤高程噪声）
    gain = loss = 0.0
    ref = None
    for s in samples:
        alt = s.get("alt")
        if alt is None:
            continue
        if ref is None:
            ref = alt
            continue
        diff = alt - ref
        if diff >= 1.0:
            gain += diff
            ref = alt
        elif diff <= -1.0:
            loss += -diff
            ref = alt
    stats["elev_gain_m"] = gain
    stats["elev_loss_m"] = loss

    # 均速也只按 >5 km/h 的时段算：该时段内的距离 / 该时段内的时间
    if moving > 0:
        stats["avg_speed"] = fast_dist / moving
    elif stats["moving_s"] > 0:
        stats["avg_speed"] = stats["distance_m"] / stats["moving_s"]
    sp_vals = [s["speed"] for s in samples if s.get("speed") and s["speed"] > 0.2]
    stats["max_speed"] = _pct(sp_vals, 0.995) or 0.0

    for key, skey in (("hr", "hr"), ("cadence", "cadence"), ("power", "power")):
        vals = [s.get(skey) for s in samples if s.get(skey)]
        vals = [v for v in vals if v > 0]
        if vals:
            avg = sum(vals) / len(vals)
            hi = _pct(vals, 0.995)
            stats[f"avg_{key}"] = avg
            stats[f"max_{key}"] = hi

    # 卡路里：优先用设备记录，其次由功率功推算（kJ ≈ W·s/1000，1kcal≈4.184kJ，人体效率约 24%）
    cal = session.get("total_calories")
    if cal:
        stats["calories"] = float(cal)
    elif stats["avg_power"] and stats["moving_s"]:
        work_kj = stats["avg_power"] * stats["moving_s"] / 1000.0
        stats["calories"] = work_kj / 4.184 / 0.24

    # 设备给出的总距离/爬升更可信（计划轨迹可能缺 GPS）
    if session.get("total_distance"):
        stats["distance_m"] = float(session["total_distance"])
    if session.get("total_ascent"):
        stats["elev_gain_m"] = float(session["total_ascent"])
    return stats
