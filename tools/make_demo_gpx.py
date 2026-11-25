"""生成一条演示用的 GPX 骑行记录（成都市区环线），方便没有 FIT 文件时试用。"""
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample" / "demo_ride.gpx"

START = datetime(2026, 11, 22, 1, 6, 0)  # UTC，本地显示 09:06
CENTER = (30.6590, 104.0650)


def track(t):
    """t: 秒，返回 (lat, lon)，市区一圈环线。"""
    a = t / 3600.0 * 2 * math.pi
    lat = CENTER[0] + 0.027 * math.sin(a) + 0.006 * math.sin(3 * a)
    lon = CENTER[1] + 0.035 * math.cos(a) + 0.005 * math.cos(2 * a)
    return lat, lon


def elevation(t):
    a = t / 3600.0 * 2 * math.pi
    return 498 + 26 * math.sin(2 * a + 0.6) + 9 * math.sin(5 * a) + 3 * math.sin(11 * a)


def speed(t):
    a = t / 3600.0 * 2 * math.pi
    return max(6.0, 24 + 9 * math.sin(3 * a + 1.2) + 4 * math.sin(9 * a) + random.uniform(-1.2, 1.2))


def main():
    random.seed(7)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dur = 3600 * 1.2
    step = 3
    pts = []
    t = 0.0
    while t < dur:
        lat, lon = track(t)
        pts.append((t, lat, lon))
        t += step

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="PrivateBike demo" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">',
        "  <trk>",
        "    <name>演示骑行 · 成都环线</name>",
        "    <type>cycling</type>",
        "    <trkseg>",
    ]
    for t, lat, lon in pts:
        ts = START + timedelta(seconds=t)
        v = speed(t) / 3.6
        hr = int(118 + 42 * min(1.0, max(0.0, (speed(t) - 12) / 22)) + random.uniform(-4, 4))
        cad = int(62 + 34 * min(1.0, max(0.0, (speed(t) - 10) / 24)) + random.uniform(-5, 5))
        pw = int(90 + 150 * min(1.0, max(0.0, (speed(t) - 8) / 26)) + random.uniform(-12, 12))
        lines.append(
            f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">'
            f"<ele>{elevation(t):.1f}</ele>"
            f'<time>{ts.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>'
            f'<extensions><gpxtpx:TrackPointExtension>'
            f"<gpxtpx:hr>{hr}</gpxtpx:hr><gpxtpx:cad>{cad}</gpxtpx:cad>"
            f"<gpxtpx:power>{pw}</gpxtpx:power>"
            f"</gpxtpx:TrackPointExtension></extensions></trkpt>"
        )
    lines += ["    </trkseg>", "  </trk>", "</gpx>"]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("written:", OUT, len(pts), "points")


if __name__ == "__main__":
    main()
