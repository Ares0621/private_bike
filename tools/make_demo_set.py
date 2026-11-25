"""生成一组跨月度的演示骑行 GPX，用于测试叠加对比与月度统计。"""
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "sample" / "demo_rides"

# (文件名, UTC开始时间, 中心点, lat半径, lon半径, 时长小时, 均速基准, 随机种子)
SPECS = [
    ("2026-06-14_晨骑_西郊.gpx", datetime(2026, 6, 14, 0, 12), (30.672, 103.985), 0.030, 0.040, 1.2, 20, 11),
    ("2026-07-05_夜骑_城南.gpx", datetime(2026, 7, 5, 10, 40), (30.615, 104.075), 0.026, 0.034, 1.6, 24, 12),
    ("2026-07-21_傍晚_东北.gpx", datetime(2026, 7, 21, 10, 30), (30.700, 104.140), 0.033, 0.042, 1.4, 26, 13),
    ("2026-08-09_长距离_东湖.gpx", datetime(2026, 8, 9, 22, 50), (30.660, 104.155), 0.045, 0.055, 2.4, 22, 14),
    ("2026-09-18_周末_环城.gpx", datetime(2026, 9, 18, 1, 20), (30.640, 104.050), 0.040, 0.050, 2.2, 23, 15),
    ("2026-10-02_爬坡_龙泉.gpx", datetime(2026, 10, 2, 23, 30), (30.735, 104.230), 0.028, 0.036, 1.9, 19, 16),
]


def make(spec):
    name, start, center, rlat, rlon, hours, base_speed, seed = spec
    random.seed(seed)
    dur = hours * 3600
    step = 5
    pts = []
    t = 0.0
    while t < dur:
        a = t / dur * 2 * math.pi * 1.1
        lat = center[0] + rlat * math.sin(a) + 0.004 * math.sin(3 * a + seed)
        lon = center[1] + rlon * math.cos(a) + 0.004 * math.cos(2 * a)
        pts.append((t, lat, lon))
        t += step

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="PrivateBike demo" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">',
        "  <trk>",
        f"    <name>{Path(name).stem}</name>",
        "    <type>cycling</type>",
        "    <trkseg>",
    ]
    for t, lat, lon in pts:
        a = t / dur * 2 * math.pi
        v = max(6.0, base_speed + 8 * math.sin(3 * a + seed) + 3 * math.sin(9 * a))
        ele = 480 + 70 * math.sin(2 * a + 0.4) + 15 * math.sin(6 * a) * (seed % 5) / 4
        ts = start + timedelta(seconds=t)
        hr = int(112 + 45 * min(1.0, max(0.0, (v - 10) / 22)) + random.uniform(-4, 4))
        cad = int(60 + 36 * min(1.0, max(0.0, (v - 9) / 24)) + random.uniform(-5, 5))
        pw = int(80 + 160 * min(1.0, max(0.0, (v - 8) / 26)) + random.uniform(-12, 12))
        lines.append(
            f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">'
            f"<ele>{ele:.1f}</ele>"
            f'<time>{ts.strftime("%Y-%m-%dT%H:%M:%SZ")}</time>'
            f"<extensions><gpxtpx:TrackPointExtension>"
            f"<gpxtpx:hr>{hr}</gpxtpx:hr><gpxtpx:cad>{cad}</gpxtpx:cad>"
            f"<gpxtpx:power>{pw}</gpxtpx:power>"
            f"</gpxtpx:TrackPointExtension></extensions></trkpt>"
        )
    lines += ["    </trkseg>", "  </trk>", "</gpx>"]
    path = OUT_DIR / name
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        print("written:", make(spec))
