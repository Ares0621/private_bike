"""用已保存的会话验证行者接口与同步（不打开界面、不打印 cookie 内容）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bike import xingzhe
from bike.db import RideDB

cookies = xingzhe.load_cookies()
print("cookie 条目数:", len(cookies))

user = xingzhe.fetch_user(cookies)
print("user_info OK:", {k: user.get(k) for k in ("username", "nickname", "id") if k in user})

items = xingzhe.list_workouts(cookies)
print("list_workouts OK:", len(items), "条 | 最新:", items[0]["title"] if items else "-")

st = xingzhe.fetch_stream(cookies, items[0]["id"]) if items else None
print("stream OK: 点数", len((st or {}).get("location") or []),
      "| 有速度", bool((st or {}).get("speed")),
      "| 有心率", bool((st or {}).get("heartrate")))

db = RideDB()
print("同步前:", db.count(), "条")
res = xingzhe.sync(db, cookies, only_recent=10)
print("sync -> added", len(res["added"]), "skipped", res["skipped"],
      "no_track", len(res["no_track"]), "failed", len(res["failed"]))
print("同步后:", db.count(), "条 | 总里程",
      round(db.total_distance() / 1000, 1), "km")
for t, e in res["failed"][:5]:
    print("  fail:", t, e)
db.close()
print("done")
