"""训练计划：从历史骑行数据推能力画像，再生成可执行的周训练任务。

没有心率 / 功率也能练 —— 这里用「速度分区 + 说话测试」定义强度：
以个人近 N 天的均速为基准 V，把强度分成 Z1~Z5，每节课直接给出目标均速区间。
"""
import statistics as st
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# 强度分区：(代号, 名称, 相对基准系数的下界, 上界, 主观感觉)
ZONES = (
    ("Z1", "恢复", 0.70, 0.85, "非常轻松，能完整对话，主要促进恢复"),
    ("Z2", "耐力", 0.85, 0.97, "轻松长骑，鼻呼吸为主，能说短句"),
    ("Z3", "节奏", 0.97, 1.06, "略吃力，呼吸变深，说话变短"),
    ("Z4", "阈值", 1.06, 1.15, "明显吃力，只能说几个字，可维持 8~20 分钟"),
    ("Z5", "冲刺", 1.15, 1.35, "全力，20 秒~3 分钟，组间充分恢复"),
)

WEEK_DAYS = {2: (3, 6), 3: (2, 4, 7), 4: (2, 3, 5, 7), 5: (1, 2, 4, 6, 7)}
DAY_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}


@dataclass
class Profile:
    window_days: int
    rides: int
    km_per_week: float
    rides_per_week: float
    base_speed: float          # km/h，个人均速基准
    speed_p25: float
    speed_p75: float
    typical_min: float
    typical_km: float
    longest_km: float
    elev_per_km: float
    has_hr: bool
    has_power: bool
    last_ride: str
    notes: list = field(default_factory=list)

    def zone_range(self, code: str) -> str:
        for z_code, z_name, lo, hi, _ in ZONES:
            if z_code == code:
                return f"{self.base_speed * lo:.0f}-{self.base_speed * hi:.0f} km/h"
        return ""

    def zone_avg(self, code: str) -> float:
        for z_code, z_name, lo, hi, _ in ZONES:
            if z_code == code:
                return self.base_speed * (lo + hi) / 2
        return self.base_speed

    def zone_feel(self, code: str) -> str:
        for z_code, z_name, lo, hi, feel in ZONES:
            if z_code == code:
                return feel
        return ""


def _pct(values, q):
    if not values:
        return 0.0
    vals = sorted(values)
    return vals[min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))]


def build_profile(db, days: int = 90) -> Profile:
    """从库里最近 days 天的记录推能力画像；样本太少时自动扩大到全部记录。"""
    all_rows = [r for r in db.list_rides() if r.get("start_time")]
    if not all_rows:
        raise ValueError("库里还没有骑行记录，先同步或导入数据")
    last = all_rows[0]["start_time"]
    last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    lo = (last_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in all_rows if r["start_time"][:10] >= lo]
    used_days = days
    if len(rows) < 6:                      # 太少就以全部记录为准，避免画像失真
        rows = all_rows
        used_days = max(30, (last_dt - datetime.strptime(rows[-1]["start_time"], "%Y-%m-%d %H:%M:%S")).days)

    km = sum((r.get("distance_m") or 0) for r in rows) / 1000.0
    minutes = sum((r.get("moving_s") or r.get("duration_s") or 0) for r in rows) / 60.0
    elev = sum((r.get("elev_gain_m") or 0) for r in rows)
    speeds = [(r.get("avg_speed") or 0) * 3.6 for r in rows if r.get("avg_speed")]
    ride_minutes = [(r.get("moving_s") or r.get("duration_s") or 0) / 60.0 for r in rows]
    ride_km = [(r.get("distance_m") or 0) / 1000.0 for r in rows]
    weeks = max(1.0, used_days / 7.0)

    base = st.mean(speeds) if speeds else 18.0
    prof = Profile(
        window_days=used_days,
        rides=len(rows),
        km_per_week=round(km / weeks, 1),
        rides_per_week=round(len(rows) / weeks, 1),
        base_speed=round(base, 1),
        speed_p25=round(_pct(speeds, 0.25), 1),
        speed_p75=round(_pct(speeds, 0.75), 1),
        typical_min=round(_pct(ride_minutes, 0.5)),
        typical_km=round(_pct(ride_km, 0.5), 1),
        longest_km=round(max(ride_km), 1),
        elev_per_km=round(elev / km, 1) if km else 0.0,
        has_hr=any(r.get("avg_hr") for r in rows),
        has_power=any(r.get("avg_power") for r in rows),
        last_ride=last[:10],
    )

    # ---------------- 诊断 ----------------
    n = prof.rides_per_week
    if n < 2.0:
        prof.notes.append(f"训练频率偏低且不规律：近 {prof.window_days} 天平均每周只有 {n} 次，"
                          f"周骑量 {prof.km_per_week:g} km。先把频次稳定到每周 3 次，比堆距离更有效。")
    elif n < 3.0:
        prof.notes.append(f"频率 {n} 次/周，略低于渐进所需；计划里会把周中两次课固定下来。")
    spread = prof.speed_p75 - prof.speed_p25
    if spread < 3.0:
        prof.notes.append(f"配速过于单一：均速集中在 {prof.speed_p25:g}~{prof.speed_p75:g} km/h（四分位区间只有 "
                          f"{spread:g} km/h），几乎每次都用同一个节奏。需要加入 Z3/Z4 间歇，才能带动巡航速度上台阶。")
    elif spread < 6.0:
        prof.notes.append(f"节奏有一定变化（{prof.speed_p25:g}~{prof.speed_p75:g} km/h），但高强度占比不高。")
    else:
        prof.notes.append(f"节奏变化充分（{prof.speed_p25:g}~{prof.speed_p75:g} km/h），可以按周期化推进。")
    if prof.elev_per_km < 4:
        prof.notes.append(f"地形几乎全是平路（每公里爬升 {prof.elev_per_km:g} m），爬坡课要找桥 / 立交 / 缓坡，"
                          "或用骑行台大阻力低踏频代替。")
    if prof.longest_km > prof.typical_km * 3:
        prof.notes.append(f"底子在：最长单次 {prof.longest_km:g} km（典型单次只有 {prof.typical_km:g} km），"
                          "说明耐力基础可挖，计划用渐进长距离把它重新激活。")
    if not prof.has_hr and not prof.has_power:
        prof.notes.append("记录里没有心率 / 功率数据，强度用「目标均速区间 + 说话测试」控制；"
                          "有条件加一条心率带，计划执行会更准。")
    return prof


# ------------------------------------------------------------------ 课程模板
@dataclass
class Session:
    week: int
    weekday: int
    kind: str
    title: str
    duration_min: int
    distance_km: float
    zone: str
    structure: str
    note: str = ""

    @property
    def speed_text(self) -> str:
        return self.zone


def _session(week, weekday, kind, title, minutes, zone_range, zone_code, prof, structure, note=""):
    avg = prof.zone_avg(zone_code)
    return Session(week=week, weekday=weekday, kind=kind, title=title,
                   duration_min=minutes, distance_km=round(minutes / 60.0 * avg, 1),
                   zone=zone_range, structure=structure, note=note)


GOAL_LABELS = {
    "auto": "按数据自动安排",
    "endurance": "提升耐力 / 长距离",
    "speed": "提升速度 / 爬坡",
    "health": "规律骑行 / 减脂",
}


def build_plan(prof: Profile, weeks: int = 4, per_week: int = 3, goal: str = "auto",
               start: date | None = None) -> dict:
    """生成 weeks 周、每周 per_week 次的训练任务。"""
    auto = (goal == "auto")
    if auto:
        goal = "endurance" if prof.rides_per_week < 3 else "speed"

    if start is None:
        today = date.today()
        start = today + timedelta(days=(7 - today.weekday()) % 7 or 7)   # 下一个周一

    weekdays = WEEK_DAYS.get(per_week, WEEK_DAYS[3])[:per_week]

    # 周中课从典型时长起步，逐周加 5 分钟；长距离从 1.3 倍典型时长起步
    mid_base = max(30, min(60, round(prof.typical_min / 5) * 5))
    long_base = max(50, min(120, round(prof.typical_min * 1.3 / 5) * 5))

    sessions: list[Session] = []
    for w in range(1, weeks + 1):
        is_deload = (w == weeks)
        block = (w - 1) % 3              # 0=基础 1=阈值 2=冲刺/爬坡
        add_mid = min(12, (w - 1) * 3)
        mid = mid_base + add_mid
        long_min = long_base + min(40, (w - 1) * 10)
        if is_deload:
            mid = max(30, mid_base)
            long_min = max(45, long_base)

        for i, wd in enumerate(weekdays):
            is_long = per_week >= 3 and i == per_week - 1
            if is_deload and i == 0:
                sessions.append(_session(w, wd, "恢复", "恢复骑", max(25, mid - 10),
                                         prof.zone_range("Z1"), "Z1", prof,
                                         "全程 Z1，踏频 80~90 rpm，心率/呼吸都很轻松；"
                                         "目的只是让腿转起来、加快恢复，不要追速度。"))
            elif is_long:
                sessions.append(_session(w, wd, "长距离", "周末长距离",
                                         long_min, prof.zone_range("Z2"), "Z2", prof,
                                         "全程 Z2 稳住，前 1/3 别冲；每 20 分钟补水一口；"
                                         "状态好就在最后 15 分钟提到 Z3，但不冲刺。",
                                         "本周最长的一节，宁可放慢也别中途掉速。"))
            elif i == 0:
                sessions.append(_session(w, wd, "耐力", "耐力基础",
                                         mid, prof.zone_range("Z2"), "Z2", prof,
                                         f"热身 8 分钟 Z1 → 主体 {max(15, mid - 18)} 分钟 Z2 连续骑 → 放松 10 分钟 Z1。"
                                         "全程用能说短句的强度。"))
            elif block == 0 or is_deload:
                reps = 3 if not is_deload else 2
                sessions.append(_session(w, wd, "节奏", "节奏间歇",
                                         mid, prof.zone_range("Z3"), "Z3", prof,
                                         f"热身 10 分钟 Z1 → {reps}×8 分钟 Z3（组间 3 分钟 Z1）→ 放松 10 分钟。"))
            elif block == 1:
                if goal == "health":
                    sessions.append(_session(w, wd, "节奏", "节奏间歇（轻松版）",
                                             mid, prof.zone_range("Z3"), "Z3", prof,
                                             f"热身 10 分钟 Z1 → 2×10 分钟 Z3（组间 5 分钟 Z1）→ 放松 10 分钟。"
                                             "目标是出汗和稳定输出，不追求极限。"))
                else:
                    reps = 4
                    sessions.append(_session(w, wd, "阈值", "阈值间歇",
                                             mid, prof.zone_range("Z4"), "Z4", prof,
                                             f"热身 10 分钟 Z1 → {reps}×6 分钟 Z4（组间 3 分钟 Z1）→ 放松 10 分钟。"
                                             "最后一组还能维持住节奏就算成功。"))
            else:
                if goal == "speed":
                    sessions.append(_session(w, wd, "爬坡", "爬坡 / 低踏频力量",
                                             mid, prof.zone_range("Z4"), "Z4", prof,
                                             f"热身 10 分钟 → 6×3 分钟爬坡（踏频 60~70 rpm，Z4~Z5）+ 3 分钟下坡恢复 → 放松 10 分钟。"))
                elif goal == "health":
                    sessions.append(_session(w, wd, "耐力", "耐力巡航",
                                             mid, prof.zone_range("Z2"), "Z2", prof,
                                             "热身 8 分钟 Z1 → 全程 Z2 稳定巡航 → 放松 10 分钟；"
                                             "全程能正常说话，靠时间积累消耗。"))
                else:
                    sessions.append(_session(w, wd, "节奏", "节奏长间歇",
                                             mid, prof.zone_range("Z3"), "Z3", prof,
                                             "热身 10 分钟 Z1 → 3×10 分钟 Z3（组间 4 分钟 Z1）→ 放松 10 分钟。"
                                             "耐力路线不加冲刺，用较长的节奏块练持续输出。"))

    week_km = {}
    for s in sessions:
        week_km[s.week] = round(week_km.get(s.week, 0.0) + s.distance_km, 1)

    return {
        "profile": prof,
        "goal": goal,
        "auto": auto,
        "goal_label": GOAL_LABELS.get(goal, goal),
        "weeks": weeks,
        "per_week": per_week,
        "start": start,
        "sessions": sessions,
        "week_km": week_km,
        "zones": [(c, n, prof.zone_range(c), feel) for c, n, lo, hi, f_ in ZONES for feel in [f_]],
    }


def session_date(plan: dict, s: Session) -> str:
    start = plan["start"]
    d = start + timedelta(days=(s.week - 1) * 7 + (s.weekday - 1))
    return f"{d.month}月{d.day}日" if d.year == date.today().year else d.strftime("%Y-%m-%d")


def plan_to_markdown(plan: dict) -> str:
    prof: Profile = plan["profile"]
    title = plan["goal_label"] + ("（按数据自动选择）" if plan.get("auto") else "")
    lines = [f"# 骑行训练计划（{title}）", ""]
    lines.append(f"- 生成依据：近 {prof.window_days} 天 {prof.rides} 次骑行，"
                 f"周均 {prof.km_per_week:g} km / {prof.rides_per_week} 次，"
                 f"个人均速基准 {prof.base_speed:g} km/h")
    lines.append(f"- 计划：{plan['weeks']} 周，每周 {plan['per_week']} 次，"
                 f"从 {plan['start'].strftime('%Y-%m-%d')} 开始")
    lines.append("")
    lines.append("## 当前能力诊断")
    for n in prof.notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## 强度分区（按速度，配合说话测试）")
    lines.append("")
    lines.append("| 分区 | 名称 | 目标均速 | 主观感觉 |")
    lines.append("| --- | --- | --- | --- |")
    for code, name, rng, feel in plan["zones"]:
        lines.append(f"| {code} | {name} | {rng} | {feel} |")
    lines.append("")
    lines.append("## 每周任务")
    for w in range(1, plan["weeks"] + 1):
        ws = [s for s in plan["sessions"] if s.week == w]
        tag = "（减量周）" if w == plan["weeks"] else ""
        lines.append(f"### 第 {w} 周{tag} · 合计 {plan['week_km'].get(w, 0):g} km")
        lines.append("")
        lines.append("| 日期 | 课程 | 时长 | 目标距离 | 强度 | 结构 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for s in ws:
            lines.append(f"| {session_date(plan, s)} | {s.title} | {s.duration_min} 分钟 | "
                         f"{s.distance_km:g} km | {s.zone} | {s.structure} |")
        lines.append("")
        for s in ws:
            if s.note:
                lines.append(f"> {s.title}：{s.note}")
        lines.append("")
    lines.append("## 执行要点")
    lines.append("")
    lines.append("- 周中课按「目标均速区间」骑，宁可慢一点也别冲进下一区；强度课的高强度部分只在主课里出现。")
    lines.append("- 每次课前后各留 5~10 分钟轻松骑，别一上车就进强度。")
    lines.append("- 同周两节课之间至少隔一天；如果某天状态差，把强度课往后挪，别连着两天上强度。")
    lines.append("- 每周结束后看一次软件里的月度统计 / 叠加对比，确认周骑量是否落在计划值附近（±10% 都算达标）。")
    lines.append("- 减量周不要额外加量：这一周的作用是把前几周的疲劳消化掉。")
    return "\n".join(lines) + "\n"


def plan_to_csv(plan: dict) -> str:
    rows = ["周次,日期,课程,时长(分钟),目标距离(km),强度,结构,备注"]
    for s in plan["sessions"]:
        rows.append(",".join([
            str(s.week), session_date(plan, s), s.title, str(s.duration_min),
            f"{s.distance_km:g}", s.zone.replace(",", "；"), f"\"{s.structure}\"",
            f"\"{s.note}\"",
        ]))
    return "\n".join(rows) + "\n"
