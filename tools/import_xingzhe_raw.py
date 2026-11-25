"""把已抓取到本地缓存的行者数据（data/xingzhe_raw）导入正式库。

用法：python tools/import_xingzhe_raw.py [--db 路径] [--dry-run]
缓存里是 workout_list.json（记录列表）+ stream_<id>.json（轨迹流），
结构与本模块在线同步用的接口完全一致，可用来验证转换链路。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bike import metrics, xingzhe  # noqa: E402
from bike.db import RideDB  # noqa: E402

RAW_DIR = os.path.join(ROOT, "data", "xingzhe_raw")


def main():
    dry = "--dry-run" in sys.argv
    db_path = None
    for i, a in enumerate(sys.argv):
        if a == "--db" and i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]

    with open(os.path.join(RAW_DIR, "workout_list.json"), encoding="utf-8") as f:
        metas = {int(m["id"]): m for m in json.load(f)}

    db = RideDB(db_path)
    added = skipped = no_track = failed = 0
    for path in sorted(glob.glob(os.path.join(RAW_DIR, "stream_*.json"))):
        wid = int(os.path.basename(path).split("_")[1].split(".")[0])
        meta = metas.get(wid)
        if meta is None:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            data = (payload or {}).get("data") or {}
            if not data.get("location"):
                no_track += 1
                continue
            ride = xingzhe.workout_to_ride(meta, data)
            ride.stats = metrics.compute_stats(ride.samples, ride.session)
            if db.exists(ride.fingerprint):
                skipped += 1
                continue
            if db.find_similar(
                    ride.start_time.strftime("%Y-%m-%d %H:%M:%S") if ride.start_time else "",
                    ride.stats.get("distance_m")):
                skipped += 1
                print(f"skip(duplicate) {ride.start_time} {ride.title}")
                continue
            if dry:
                added += 1
                print(f"[dry] {ride.start_time} {ride.title}  "
                      f"{ride.stats['distance_m'] / 1000:.2f}km  "
                      f"{(ride.stats['avg_speed'] or 0) * 3.6:.1f}km/h  "
                      f"{len(ride.samples)}点  hr={ride.stats['avg_hr']}")
                continue
            db.add_ride(ride)
            added += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL", wid, exc)

    print(f"done: added={added} skipped={skipped} no_track={no_track} failed={failed}")
    print("db total:", db.count(), "distance km:",
          round(db.total_distance() / 1000, 1))
    db.close()


if __name__ == "__main__":
    main()
