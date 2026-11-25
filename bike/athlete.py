"""个人资料 / 车辆资料 / 个人能力图（全部从本地骑行数据自动算出）。

设计原则：
- **能力图**只用骑行记录算（Haversine 距离、均速、爬升密度、周骑量、周频次、节奏变化），
  不需要手填任何东西；填了身高体重年龄，只是多给 BMI / 心率区间 / 估算 W·kg 这些换算。
- 功率是「按体重 + 车重 + 速度」的物理估算（滚阻 + 空气阻力 + 传动损失），
  没有功率计也能给个量级参考，界面上标明是估算。
"""
from dataclasses import dataclass
from datetime import date

from . import training

RHO = 1.225          # 空气密度 kg/m3
CRR = 0.005          # 公路车滚阻系数
CDA = 0.36           # 上把位迎风面积
LOSS = 1.12          # 传动 + 路面 + 风的小幅补偿

DEFAULT_WEIGHT_KG = 65.0
DEFAULT_BIKE_KG = 8.5


@dataclass
class Athlete:
    name: str = ""
    sex: str = ""
    birth_year: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    resting_hr: float | None = None
    max_hr: float | None = None
    ftp_w: float | None = None
    weekly_goal_km: float | None = None
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "Athlete":
        def num(key):
            v = (row or {}).get(key)
            try:
                return float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return cls(
            name=(row or {}).get("name") or "",
            sex=(row or {}).get("sex") or "",
            birth_year=int(num("birth_year")) if num("birth_year") else None,
            height_cm=num("height_cm"),
            weight_kg=num("weight_kg"),
            resting_hr=num("resting_hr"),
            max_hr=num("max_hr"),
            ftp_w=num("ftp_w"),
            weekly_goal_km=num("weekly_goal_km"),
            notes=(row or {}).get("notes") or "",
        )

    @property
    def age(self) -> int | None:
        if not self.birth_year:
            return None
        return max(0, date.today().year - self.birth_year)

    @property
    def bmi(self) -> float | None:
        if not self.height_cm or not self.weight_kg:
            return None
        h = self.height_cm / 100.0
        return round(self.weight_kg / (h * h), 1)

    @property
    def max_hr_est(self) -> float | None:
        """有实测最大心率就用实测，否则用 Tanaka 公式（比 220-年龄 更稳）。"""
        if self.max_hr:
            return self.max_hr
        if self.age:
            return round(208 - 0.7 * self.age)
        return None

    @property
    def is_empty(self) -> bool:
        return not any([self.name, self.height_cm, self.weight_kg, self.resting_hr,
                        self.birth_year, self.max_hr])

    def hr_zones(self) -> list[tuple[str, str, str, str]]:
        """(代号, 名称, bpm 区间, 用途)。按最大心率百分比。"""
        mx = self.max_hr_est
        if not mx:
            return []
        parts = (
            ("Z1", "恢复", 0.50, 0.60, "热身 / 恢复，能完整聊天"),
            ("Z2", "耐力", 0.60, 0.70, "长距离有氧，鼻呼吸为主"),
            ("Z3", "节奏", 0.70, 0.80, "略吃力，说短句"),
            ("Z4", "阈值", 0.80, 0.90, "明显吃力，几个字"),
            ("Z5", "冲刺", 0.90, 1.00, "全力，维持时间很短"),
        )
        return [(c, n, f"{mx * lo:.0f}-{mx * hi:.0f} bpm", u) for c, n, lo, hi, u in parts]

    def resting_note(self) -> str:
        rhr = self.resting_hr
        if not rhr:
            return "未填静息心率（晨起安静坐 5 分钟后测最准）"
        if rhr < 50:
            return f"静息 {rhr:.0f} bpm，有训练基础；若伴随头晕/乏力要留意过度训练"
        if rhr < 60:
            return f"静息 {rhr:.0f} bpm，有氧基础不错"
        if rhr <= 70:
            return f"静息 {rhr:.0f} bpm，普通水平，规律有氧会降下来"
        return f"静息 {rhr:.0f} bpm 偏高，先以轻松有氧为主，别一上来就练强度"

    def bmi_note(self) -> str:
        bmi = self.bmi
        if not bmi:
            return "填身高体重后显示 BMI"
        if bmi < 18.5:
            return f"BMI {bmi:g} 偏轻，注意补给与力量训练"
        if bmi < 24:
            return f"BMI {bmi:g} 正常，爬坡有优势"
        if bmi < 28:
            return f"BMI {bmi:g} 略高，减脂优先用长时间 Z2"
        return f"BMI {bmi:g} 偏高，先控饮食 + 规律有氧，强度课少排"


@dataclass
class Bike:
    model: str = ""
    bike_type: str = "公路车"
    weight_kg: float | None = None
    wheel: str = ""
    gearing: str = ""
    notes: str = ""
    id: int | None = None

    @classmethod
    def from_row(cls, row: dict) -> "Bike":
        row = row or {}
        try:
            w = float(row.get("weight_kg")) if row.get("weight_kg") not in (None, "") else None
        except (TypeError, ValueError):
            w = None
        return cls(model=row.get("model") or "", bike_type=row.get("bike_type") or "公路车",
                   weight_kg=w, wheel=row.get("wheel") or "", gearing=row.get("gearing") or "",
                   notes=row.get("notes") or "", id=row.get("id"))

    @property
    def is_empty(self) -> bool:
        return not any([self.model, self.weight_kg, self.wheel, self.gearing])

    @property
    def mass(self) -> float:
        return self.weight_kg or DEFAULT_BIKE_KG


def estimate_power(speed_kmh: float, total_kg: float, grade_pct: float = 0.0) -> float:
    """平路/坡度上维持该速度需要的功率（W）。坡度为百分比，例如 4 表示 4%。"""
    if speed_kmh <= 0:
        return 0.0
    v = speed_kmh / 3.6
    roll = total_kg * 9.81 * CRR
    aero = 0.5 * RHO * CDA * v * v
    climb = total_kg * 9.81 * (grade_pct / 100.0)
    return round((roll + aero + climb) * v * LOSS, 0)


# ------------------------------------------------------------------ 能力图
# (代号, 名称, 口语解释, 参考值 = 进阶爱好者的水平, 单位)
CAP_AXES = (
    ("endurance", "耐力", "最长单次能骑多远", 120.0, "km"),
    ("weekly", "周骑量", "一周累计里程", 100.0, "km"),
    ("frequency", "训练频率", "一周骑几次", 4.5, "次"),
    ("cruise", "巡航速度", "日常均速基线", 30.0, "km/h"),
    ("climb", "爬坡", "每公里爬升", 20.0, "m/km"),
    ("rhythm", "节奏变化", "快慢结合的幅度", 8.0, "km/h"),
)


def capability(db, days: int = 90) -> dict:
    """只用骑行记录算能力图。返回 {items, overall, profile, summary}。"""

    def score(value, ref):
        return max(0, min(100, int(round(value / ref * 100)))) if ref else 0

    try:
        prof = training.build_profile(db, days)
    except ValueError:
        return {"items": [], "overall": 0, "profile": None,
                "summary": "还没有骑行记录，先同步行者或导入 FIT/GPX，能力图会自动生成。"}
    except Exception:  # noqa: BLE001
        return {"items": [], "overall": 0, "profile": None, "summary": "能力图计算失败，请检查数据。"}

    spread = round(prof.speed_p75 - prof.speed_p25, 1)
    raw = {
        "endurance": prof.longest_km,
        "weekly": prof.km_per_week,
        "frequency": prof.rides_per_week,
        "cruise": prof.base_speed,
        "climb": prof.elev_per_km,
        "rhythm": spread,
    }
    items = []
    for key, name, desc, ref, unit in CAP_AXES:
        v = raw[key]
        items.append({
            "key": key, "label": name, "desc": desc,
            "value": v, "text": f"{v:g} {unit}", "score": score(v, ref),
            "ref_text": f"进阶 {ref:g} {unit}",
        })

    overall = round(sum(i["score"] for i in items) / len(items))
    strong = max(items, key=lambda i: i["score"])
    weak = min(items, key=lambda i: i["score"])
    summary = (f"整体 {overall} 分（相对进阶爱好者）。相对强的是「{strong['label']}」"
               f"（{strong['text']}），最该补的是「{weak['label']}」（{weak['text']}）。")
    return {"items": items, "overall": overall, "profile": prof, "summary": summary}


def load(db) -> tuple[Athlete, Bike]:
    return Athlete.from_row(db.get_athlete()), Bike.from_row(db.get_bike())


def derived(prof, athlete: Athlete, bike: Bike, speed_kmh: float | None = None) -> dict:
    """把身体/车的数据和骑行数据结合，给出可展示的换算结果。"""
    weight = athlete.weight_kg or DEFAULT_WEIGHT_KG
    total = weight + bike.mass
    speed = speed_kmh or (prof.base_speed if prof else 19.0)
    p0 = estimate_power(speed, total)
    p_thr = estimate_power(speed * 1.10, total)
    wkg = round(p_thr / weight, 2)
    return {
        "total_kg": round(total, 1),
        "weight_known": athlete.weight_kg is not None,
        "bike_known": bike.weight_kg is not None,
        "power_cruise": p0,
        "power_threshold": p_thr,
        "w_per_kg": wkg,
        "speed": round(speed, 1),
    }
