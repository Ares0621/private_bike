"""骑行文件解析：FIT（码表主格式，字段最全）与 GPX（轨迹+海拔）。"""
import hashlib
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import metrics

SEMICIRCLE_TO_DEG = 180.0 / (2 ** 31)

SPORT_CN = {
    "cycling": "骑行", "road_cycling": "公路骑行", "mountain_cycling": "山地骑行",
    "indoor_cycling": "室内骑行", "e_biking": "电助力骑行", "running": "跑步",
    "walking": "步行", "hiking": "徒步", "swimming": "游泳", "generic": "运动",
}


@dataclass
class Ride:
    source_path: str
    source_format: str
    fingerprint: str
    title: str
    sport: str
    start_time: datetime | None
    samples: list = field(default_factory=list)
    session: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    @property
    def point_count(self) -> int:
        return len(self.samples)

    @property
    def has_gps(self) -> bool:
        return any(s.get("lat") is not None for s in self.samples)


def _fingerprint(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return dt.astimezone().replace(tzinfo=None)


def load_ride(path: str) -> Ride:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fit":
        ride = parse_fit(path)
    elif ext == ".gpx":
        ride = parse_gpx(path)
    else:
        raise ValueError(f"不支持的文件类型：{ext}（仅支持 .fit / .gpx）")
    ride.fingerprint = _fingerprint(path)
    ride.stats = metrics.compute_stats(ride.samples, ride.session)
    return ride


# ---------------------------------------------------------------- FIT
def parse_fit(path: str) -> Ride:
    import fitparse

    fit = fitparse.FitFile(path)
    session = {}
    for msg in fit.get_messages("session"):
        session = msg.get_values()
        break

    raw = []
    for msg in fit.get_messages("record"):
        v = msg.get_values()
        if v.get("timestamp") is None:
            continue
        raw.append(v)

    start = _to_local(session.get("start_time")) or (_to_local(raw[0]["timestamp"]) if raw else None)
    samples = []
    for v in raw:
        ts = _to_local(v.get("timestamp"))
        t = (ts - start).total_seconds() if (ts and start) else None
        lat = v.get("position_lat")
        lon = v.get("position_long")
        samples.append({
            "t": t,
            "lat": lat * SEMICIRCLE_TO_DEG if lat is not None else None,
            "lon": lon * SEMICIRCLE_TO_DEG if lon is not None else None,
            "alt": v.get("enhanced_altitude") if v.get("enhanced_altitude") is not None else v.get("altitude"),
            "speed": v.get("enhanced_speed") if v.get("enhanced_speed") is not None else v.get("speed"),
            "hr": v.get("heart_rate"),
            "cadence": v.get("cadence"),
            "power": v.get("power"),
            "dist": v.get("distance"),
        })

    sport_raw = str(session.get("sport") or "cycling").lower()
    return Ride(
        source_path=path,
        source_format="FIT",
        fingerprint="",
        title=os.path.splitext(os.path.basename(path))[0],
        sport=SPORT_CN.get(sport_raw, "骑行"),
        start_time=start,
        samples=samples,
        session=session,
    )


# ---------------------------------------------------------------- GPX
def _ext_value(point, names):
    for el in point.extensions or []:
        nodes = list(el.iter()) + [el]
        for node in nodes:
            tag = node.tag.split("}")[-1].lower() if isinstance(node.tag, str) else ""
            if tag in names and node.text:
                try:
                    return float(node.text)
                except ValueError:
                    continue
    return None


def parse_gpx(path: str) -> Ride:
    import gpxpy

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        gpx = gpxpy.parse(f)

    points = []
    for track in gpx.tracks:
        for seg in track.segments:
            points.extend(seg.points)
    if not points:
        for route in gpx.routes:
            points.extend(route.points)

    start = None
    for p in points:
        if p.time:
            start = _to_local(p.time)
            break

    samples = []
    prev = None
    for p in points:
        t = (_to_local(p.time) - start).total_seconds() if (p.time and start) else None
        step = metrics.haversine(prev.latitude, prev.longitude, p.latitude, p.longitude) if prev else 0.0
        samples.append({
            "t": t,
            "lat": p.latitude,
            "lon": p.longitude,
            "alt": p.elevation,
            "speed": None,
            "hr": _ext_value(p, {"hr", "heartrate", "heart_rate"}),
            "cadence": _ext_value(p, {"cad", "cadence"}),
            "power": _ext_value(p, {"power", "watts"}),
            "dist": None,
            "_step": step,
        })
        prev = p

    sport_raw = (gpx.tracks[0].type if gpx.tracks and gpx.tracks[0].type else "cycling")
    ride = Ride(
        source_path=path,
        source_format="GPX",
        fingerprint="",
        title=os.path.splitext(os.path.basename(path))[0],
        sport=SPORT_CN.get(str(sport_raw).lower(), "骑行"),
        start_time=start,
        samples=samples,
        session={},
    )
    for s in ride.samples:
        s.pop("_step", None)
    return ride
