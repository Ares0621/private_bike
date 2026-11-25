"""行者（imxingzhe.com）数据接入。

做法：用软件自带的网页登录窗口（QtWebEngine）登录行者，程序拿自己的会话
cookie 调行者网页内部接口，把全部运动记录 + 轨迹流（含心率 / 踏频 / 功率）
转成统一的 Ride 对象入库。

用到的接口（网页端自己在用的同款接口）：
    GET /api/v1/pgworkout/?offset=&limit=&sport=&year=&month=     记录列表（分页）
    GET /api/v1/pgworkout/{id}/?segments=false&...               单条详情
    GET /api/v1/pgworkout/{id}/stream/                           轨迹流（最全）
    GET /api/v1/user/user_info/                                  当前用户

注意：接口要求 X-Requested-With 头，否则返回 400；未登录或会话过期时
会 401/302 到登录页。
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

from . import metrics
from .config import DATA_DIR
from .parsers import Ride

BASE = "https://www.imxingzhe.com"
COOKIE_PATH = os.path.join(str(DATA_DIR), "xingzhe_cookies.json")
PAGE_SIZE = 16
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# 行者运动类型编码（已知：3=骑行），其余靠标题里的关键词兜底
SPORT_CODES = {1: "跑步", 2: "骑行", 3: "骑行", 4: "徒步", 5: "游泳", 6: "滑雪", 8: "室内骑行"}
SPORT_KEYWORDS = (("骑行", "骑行"), ("跑步", "跑步"), ("徒步", "徒步"), ("游泳", "游泳"),
                  ("滑雪", "滑雪"), ("训练", "训练"))


# ------------------------------------------------------------------ 会话
def save_cookies(cookies: dict) -> None:
    """把登录会话保存到本地（仅本机 data 目录，不会上传）。"""
    try:
        os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            json.dump({"cookies": cookies, "saved_at": datetime.now().isoformat(timespec="seconds")},
                      f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def load_cookies() -> dict:
    try:
        with open(COOKIE_PATH, encoding="utf-8") as f:
            return (json.load(f) or {}).get("cookies") or {}
    except (OSError, ValueError):
        return {}


def clear_cookies() -> None:
    try:
        os.remove(COOKIE_PATH)
    except OSError:
        pass


def cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if k and v)


# ------------------------------------------------------------------ 请求
class XingzheError(Exception):
    pass


def _get(path: str, cookies: dict, timeout: float = 30.0, retries: int = 2):
    """带会话的 GET，返回解析后的 JSON。"""
    url = BASE + path
    hdr = {
        "Cookie": cookie_header(cookies),
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/workouts/list",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": UA,
    }
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            if body.lstrip()[:1] == b"<":
                # 未登录时接口会 302 到登录页，返回 HTML
                raise XingzheError("登录已失效，请重新登录行者")
            return json.loads(body.decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (401, 403):
                raise XingzheError("登录已失效，请重新登录行者") from exc
            if exc.code == 404:
                return None
            time.sleep(0.4 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise XingzheError(f"请求行者接口失败：{path}（{last}）")


def fetch_user(cookies: dict) -> dict:
    """当前登录用户信息，用来判断会话是否有效。"""
    data = _get("/api/v1/user/user_info/", cookies, retries=1)
    if not data or data.get("code") not in (0, 200):
        raise XingzheError("登录已失效，请重新登录行者")
    payload = data.get("data") or {}
    if isinstance(payload, dict) and "user" in payload:
        payload = payload["user"] or {}
    return payload


def _pages(cookies: dict, year: str, limit_pages: int = 60) -> list[dict]:
    """按年（year="" 表示全部）分页拉取记录列表。"""
    items_all: list[dict] = []
    offset = 0
    for _ in range(limit_pages):
        q = urllib.parse.urlencode({"offset": offset, "limit": PAGE_SIZE, "sport": "",
                                    "year": year, "month": ""})
        data = _get(f"/api/v1/pgworkout/?{q}", cookies)
        if not data or data.get("code") not in (0, 200):
            raise XingzheError("读取行者记录列表失败（可能是登录已失效）")
        items = (data.get("data") or {}).get("data") or []
        if not items:
            break
        items_all.extend(items)
        offset += PAGE_SIZE
        if len(items) < PAGE_SIZE:
            break
    return items_all


def list_workouts(cookies: dict, since: date | None = None, until: date | None = None,
                  limit_pages: int = 60) -> list[dict]:
    """拉取记录列表。

    给了时间段就按年份分别请求（服务端 year 过滤），少翻页；顺便按日期精确过滤。
    """
    if since is None and until is None:
        return _pages(cookies, "", limit_pages)

    y0 = (since or until).year
    y1 = (until or since).year
    years = [str(y) for y in range(min(y0, y1), max(y0, y1) + 1)]

    seen, merged = set(), []
    for y in years:
        for it in _pages(cookies, y, limit_pages):
            wid = it.get("id")
            if wid in seen:
                continue
            seen.add(wid)
            merged.append(it)
    return [m for m in merged if in_range(m, since, until)]


def in_range(meta: dict, since: date | None, until: date | None) -> bool:
    ms = meta.get("start_time")
    if not ms:
        return since is None and until is None
    try:
        d = datetime.fromtimestamp(float(ms) / 1000.0).date()
    except (OSError, ValueError, OverflowError):
        return False
    if since and d < since:
        return False
    if until and d > until:
        return False
    return True


def fetch_stream(cookies: dict, workout_id: int):
    """轨迹流；无轨迹的记录返回 None（接口 404）。"""
    data = _get(f"/api/v1/pgworkout/{workout_id}/stream/", cookies)
    if not data:
        return None
    if data.get("code") not in (0, 200):
        return None
    return data.get("data") or None


# ------------------------------------------------------------------ 转换
def _sport_cn(meta: dict) -> str:
    title = meta.get("title") or ""
    for kw, name in SPORT_KEYWORDS:
        if kw in title:
            return name
    return SPORT_CODES.get(meta.get("sport"), "骑行")


def _side_array(data: dict, key: str, n: int):
    arr = data.get(key) or []
    if not arr:
        return [None] * n
    if len(arr) >= n:
        return arr[:n]
    return list(arr) + [None] * (n - len(arr))


def workout_to_ride(meta: dict, stream: dict) -> Ride:
    """把行者记录（列表元信息 + 轨迹流）转成统一的 Ride。"""
    data = stream or {}
    loc = data.get("location") or []
    ts = data.get("timestamp") or []
    n = len(loc)
    if ts:
        n = min(n, len(ts))
    if n == 0:
        raise ValueError("该记录没有轨迹点")

    t0 = ts[0] if ts else 0
    alt = _side_array(data, "altitude", n)
    speed = _side_array(data, "speed", n)
    dist = _side_array(data, "distance", n)
    hr = _side_array(data, "heartrate", n)
    cad = _side_array(data, "cadence", n)
    pwr = _side_array(data, "power", n)

    samples = []
    for i in range(n):
        point = loc[i] or [None, None]
        lon, lat = (point[0], point[1]) if len(point) >= 2 else (None, None)
        if not lat or not lon or lat == 0 or lon == 0:
            lat = lon = None
        t = (ts[i] - t0) if ts else float(i)
        samples.append({
            "t": float(t),
            "lat": lat,
            "lon": lon,
            "alt": alt[i],
            "speed": speed[i],          # 行者给的是 m/s
            "hr": hr[i],
            "cadence": cad[i],
            "power": pwr[i],
            "dist": dist[i],            # 米
        })

    start = None
    ms = meta.get("start_time")
    if ms:
        try:
            start = datetime.fromtimestamp(float(ms) / 1000.0)
        except (OSError, ValueError, OverflowError):
            start = None
    if start is None and ts:
        start = datetime.fromtimestamp(ts[0])

    title = (meta.get("title") or "").strip() or (start.strftime("%Y-%m-%d %H:%M 骑行") if start else "行者记录")
    session = {}
    if meta.get("distance"):
        session["total_distance"] = float(meta["distance"])
    if meta.get("elevation_gain"):
        session["total_ascent"] = float(meta["elevation_gain"])

    ride = Ride(
        source_path=f"{BASE}/workouts/{meta.get('id')}",
        source_format="行者",
        fingerprint=f"xingzhe:{meta.get('id')}",
        title=title,
        sport=_sport_cn(meta),
        start_time=start,
        samples=samples,
        session=session,
    )
    return ride


# ------------------------------------------------------------------ 同步
def sync(db, cookies: dict, progress=None, should_stop=None, only_recent: int | None = None,
         skip_existing: bool = True, since: date | None = None, until: date | None = None) -> dict:
    """把行者记录同步进库。

    since / until 限定时间段（只拉这段时间内的记录，避免每次全量扫描）。
    progress(step, total, message) 用于界面进度；should_stop() 返回 True 时中止。
    返回 {"added":[...], "skipped":n, "no_track":[...], "failed":[(title, err)], "user":..., "range":str}
    """
    result = {"added": [], "skipped": 0, "no_track": [], "failed": [], "user": None, "range": ""}
    result["user"] = fetch_user(cookies)

    if since or until:
        result["range"] = f"{since or '—'} ~ {until or '—'}"
    items = list_workouts(cookies, since, until)
    if only_recent:
        items = items[:only_recent]
    total = len(items)
    if progress:
        scope = f"（{result['range']}）" if result["range"] else "（全部记录）"
        progress(0, total, f"范围{scope}共 {total} 条，开始同步…")

    for i, meta in enumerate(items):
        if should_stop and should_stop():
            break
        wid = meta.get("id")
        title = meta.get("title") or str(wid)
        if progress:
            progress(i, total, f"{title}")
        fp = f"xingzhe:{wid}"
        if skip_existing and db.exists(fp):
            result["skipped"] += 1
            continue
        try:
            stream = fetch_stream(cookies, wid)
            if not stream:
                result["no_track"].append(title)
                continue
            ride = workout_to_ride(meta, stream)
            ride.stats = metrics.compute_stats(ride.samples, ride.session)
            # 跨来源去重：本地已用 FIT/GPX 导入过同一场骑行时不再重复入库
            dup = db.find_similar(
                ride.start_time.strftime("%Y-%m-%d %H:%M:%S") if ride.start_time else "",
                ride.stats.get("distance_m"))
            if dup:
                result["skipped"] += 1
                continue
            db.add_ride(ride)
            result["added"].append(ride)
        except Exception as exc:  # noqa: BLE001
            result["failed"].append((title, str(exc)))
        time.sleep(0.15)

    if progress:
        progress(total, total, "同步完成")
    return result
