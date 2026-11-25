"""按当前口径重算历史记录的有效骑行时长与均速（不改距离、爬升、消耗）。

用法：
    python tools/recalc_timing.py            # 重算全部记录
    python tools/recalc_timing.py --dry-run  # 只打印对比，不写库
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bike.db import RideDB
from bike.metrics import MOVING_MIN_SPEED_KMH, moving_time


def fmt(sec):
    sec = int(round(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def main():
    dry = "--dry-run" in sys.argv
    db = RideDB()
    count = 0
    try:
        for meta in db.list_rides():
            samples = db.get_samples(meta["id"])
            moving, fast_dist = moving_time(samples)
            duration = meta.get("duration_s") or 0
            if moving <= 0:
                print(f"[skip] {meta['title']}: 没有 >{MOVING_MIN_SPEED_KMH:g} km/h 的时段")
                continue
            avg_speed = fast_dist / moving
            old_moving = meta.get("moving_s") or 0
            if abs(moving - old_moving) < 1.0 and abs(avg_speed - (meta.get("avg_speed") or 0)) < 1e-6:
                continue
            print(f"{meta['title']}: 时长 {fmt(old_moving)} → {fmt(moving)}"
                  f"（全程 {fmt(duration)}），均速 {(meta.get('avg_speed') or 0) * 3.6:.1f} → "
                  f"{avg_speed * 3.6:.1f} km/h")
            if not dry:
                db.update_timing(meta["id"], moving, avg_speed)
            count += 1
    finally:
        db.close()
    print(("预览" if dry else "已重算") + f" {count} 条记录")


if __name__ == "__main__":
    main()
