"""验证行者列表接口的 year 参数与时间段过滤。

用法：python tools/check_range.py
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bike import xingzhe  # noqa: E402


def show(tag, items):
    cur = year = None
    print(f"\n[{tag}] {len(items)} 条")
    if not items:
        return
    for it in items[:3]:
        ms = it.get("start_time")
        d = datetime.fromtimestamp(float(ms) / 1000).strftime("%Y-%m-%d %H:%M") if ms else "?"
        print(f"   · id={it.get('id')} {d} {it.get('title')}")
    print(f"   最早：{min(xingzhe_date(it) for it in items)}  最晚：{max(xingzhe_date(it) for it in items)}")
    years = sorted({xingzhe_date(it).year for it in items})
    print(f"   含年份：{years}")


def xingzhe_date(it):
    return datetime.fromtimestamp(float(it.get("start_time")) / 1000).date()


def main():
    ck = xingzhe.load_cookies()
    if not ck:
        print("没有会话，请先在程序里登录行者")
        return 1

    print("已读取会话 cookie", len(ck), "个")
    try:
        print("用户：", xingzhe.fetch_user(ck).get("username"))
    except Exception as exc:
        print("会话失效：", exc)
        return 1

    # 1) 服务端 year 参数是否真的过滤
    for y in ("", "2026", "2025"):
        raw = xingzhe._pages(ck, y, limit_pages=5)
        print(f"\nyear='{y}' 前 5 页拿到 {len(raw)} 条", end="")
        if raw:
            ys = sorted({xingzhe_date(it).year for it in raw})
            print(f"，年份分布 {ys}")
        else:
            print()

    # 2) 时间段过滤
    show("全部", xingzhe.list_workouts(ck))
    show("2026 今年", xingzhe.list_workouts(ck, date(2026, 1, 1), date(2026, 11, 24)))
    show("2026-09-01~2026-11-24", xingzhe.list_workouts(ck, date(2026, 9, 1), date(2026, 11, 24)))
    show("最近 30 天", xingzhe.list_workouts(ck, date(2026, 10, 25), date(2026, 11, 24)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
