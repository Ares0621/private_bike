"""SQLite 存储：rides（骑行概要）+ samples（逐点轨迹）。"""
import os
import sqlite3
from datetime import datetime

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS rides(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT UNIQUE,
    source_file   TEXT,
    source_format TEXT,
    title         TEXT,
    sport         TEXT,
    start_time    TEXT,
    duration_s    REAL,
    moving_s      REAL,
    distance_m    REAL,
    elev_gain_m   REAL,
    elev_loss_m   REAL,
    avg_speed     REAL,
    max_speed     REAL,
    avg_hr        REAL,
    max_hr        REAL,
    avg_cadence   REAL,
    max_cadence   REAL,
    avg_power     REAL,
    max_power     REAL,
    calories      REAL,
    point_count   INTEGER,
    imported_at   TEXT
);
CREATE TABLE IF NOT EXISTS samples(
    ride_id INTEGER,
    idx     INTEGER,
    t       REAL,
    dist    REAL,
    lat     REAL,
    lon     REAL,
    alt     REAL,
    speed   REAL,
    hr      REAL,
    cadence REAL,
    power   REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ride ON samples(ride_id, idx);

CREATE TABLE IF NOT EXISTS athlete(
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    name          TEXT,
    sex           TEXT,
    birth_year    INTEGER,
    height_cm     REAL,
    weight_kg     REAL,
    resting_hr    REAL,
    max_hr        REAL,
    ftp_w         REAL,
    weekly_goal_km REAL,
    notes         TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS bikes(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    model       TEXT,
    bike_type   TEXT,
    weight_kg   REAL,
    wheel       TEXT,
    gearing     TEXT,
    notes       TEXT,
    is_default  INTEGER DEFAULT 1,
    updated_at  TEXT
);
"""

ATHLETE_FIELDS = ("name", "sex", "birth_year", "height_cm", "weight_kg",
                  "resting_hr", "max_hr", "ftp_w", "weekly_goal_km", "notes")
BIKE_FIELDS = ("model", "bike_type", "weight_kg", "wheel", "gearing", "notes")

SAMPLE_FIELDS = ("t", "dist", "lat", "lon", "alt", "speed", "hr", "cadence", "power")

RIDE_FIELDS = (
    "fingerprint", "source_file", "source_format", "title", "sport", "start_time",
    "duration_s", "moving_s", "distance_m", "elev_gain_m", "elev_loss_m",
    "avg_speed", "max_speed", "avg_hr", "max_hr", "avg_cadence", "max_cadence",
    "avg_power", "max_power", "calories", "point_count", "imported_at",
)


class RideDB:
    def __init__(self, path=None):
        ensure_dirs()
        self.path = path or os.environ.get("PB_DB") or DB_PATH
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- 写入 ----------
    def exists(self, fingerprint: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM rides WHERE fingerprint=?", (fingerprint,))
        return cur.fetchone() is not None

    def add_ride(self, ride) -> int:
        stats = ride.stats
        values = {
            "fingerprint": ride.fingerprint,
            "source_file": ride.source_path,
            "source_format": ride.source_format,
            "title": ride.title,
            "sport": ride.sport,
            "start_time": ride.start_time.strftime("%Y-%m-%d %H:%M:%S") if ride.start_time else "",
            "duration_s": stats.get("duration_s"),
            "moving_s": stats.get("moving_s"),
            "distance_m": stats.get("distance_m"),
            "elev_gain_m": stats.get("elev_gain_m"),
            "elev_loss_m": stats.get("elev_loss_m"),
            "avg_speed": stats.get("avg_speed"),
            "max_speed": stats.get("max_speed"),
            "avg_hr": stats.get("avg_hr"),
            "max_hr": stats.get("max_hr"),
            "avg_cadence": stats.get("avg_cadence"),
            "max_cadence": stats.get("max_cadence"),
            "avg_power": stats.get("avg_power"),
            "max_power": stats.get("max_power"),
            "calories": stats.get("calories"),
            "point_count": len(ride.samples),
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        cur = self.conn.execute(
            f"INSERT INTO rides({','.join(RIDE_FIELDS)}) VALUES({','.join('?' * len(RIDE_FIELDS))})",
            [values[f] for f in RIDE_FIELDS],
        )
        ride_id = cur.lastrowid
        rows = [
            (ride_id, i, s.get("t"), s.get("dist"), s.get("lat"), s.get("lon"),
             s.get("alt"), s.get("speed"), s.get("hr"), s.get("cadence"), s.get("power"))
            for i, s in enumerate(ride.samples)
        ]
        self.conn.executemany(
            f"INSERT INTO samples(ride_id, idx, {','.join(SAMPLE_FIELDS)}) "
            f"VALUES(?, ?, {','.join('?' * len(SAMPLE_FIELDS))})",
            rows,
        )
        self.conn.commit()
        return ride_id

    def delete_ride(self, ride_id: int) -> None:
        self.conn.execute("DELETE FROM rides WHERE id=?", (ride_id,))
        self.conn.execute("DELETE FROM samples WHERE ride_id=?", (ride_id,))
        self.conn.commit()

    def update_timing(self, ride_id: int, moving_s: float, avg_speed: float) -> None:
        """只更新有效时长与均速（用于口径调整后重算历史记录）。"""
        self.conn.execute(
            "UPDATE rides SET moving_s=?, avg_speed=? WHERE id=?",
            (moving_s, avg_speed, ride_id),
        )
        self.conn.commit()

    # ---------- 读取 ----------
    def list_rides(self, keyword: str = ""):
        rows = self.conn.execute("SELECT * FROM rides ORDER BY start_time DESC, id DESC").fetchall()
        result = [dict(r) for r in rows]
        if keyword:
            kw = keyword.lower()
            result = [
                r for r in result
                if kw in (r.get("title") or "").lower() or kw in (r.get("start_time") or "")
            ]
        return result

    def find_similar(self, start_time: str, distance_m: float, tolerance_s: int = 90):
        """查找开始时间与距离都接近的已有记录（跨来源去重：FIT 导入 vs 行者同步）。"""
        if not start_time:
            return None
        try:
            t0 = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        rows = self.conn.execute(
            "SELECT id, title, start_time, distance_m FROM rides WHERE substr(start_time,1,10)=?",
            (start_time[:10],),
        ).fetchall()
        for r in rows:
            try:
                t = datetime.strptime(r["start_time"], "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            if abs((t - t0).total_seconds()) > tolerance_s:
                continue
            d1, d2 = distance_m or 0.0, r["distance_m"] or 0.0
            if not d1 or not d2 or abs(d1 - d2) <= max(200.0, 0.03 * max(d1, d2)):
                return dict(r)
        return None

    def get_ride(self, ride_id: int):
        row = self.conn.execute("SELECT * FROM rides WHERE id=?", (ride_id,)).fetchone()
        return dict(row) if row else None

    def get_samples(self, ride_id: int):
        rows = self.conn.execute(
            "SELECT t,dist,lat,lon,alt,speed,hr,cadence,power FROM samples "
            "WHERE ride_id=? ORDER BY idx", (ride_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM rides").fetchone()[0]

    def total_distance(self) -> float:
        return self.conn.execute("SELECT COALESCE(SUM(distance_m),0) FROM rides").fetchone()[0]

    def years(self):
        rows = self.conn.execute(
            "SELECT DISTINCT substr(start_time,1,4) AS y FROM rides "
            "WHERE start_time IS NOT NULL AND start_time <> '' ORDER BY y DESC"
        ).fetchall()
        return [r["y"] for r in rows]

    def stats_by_month(self, year: str | None = None):
        """按月汇总：次数、里程、移动时长、爬升、均速、心率、最长单次。"""
        sql = """
            SELECT substr(start_time,1,7) AS ym, COUNT(*) AS rides,
                   SUM(distance_m) AS dist, SUM(moving_s) AS moving,
                   SUM(elev_gain_m) AS elev, AVG(avg_speed) AS avg_speed,
                   AVG(avg_hr) AS avg_hr, MAX(distance_m) AS longest,
                   SUM(calories) AS calories
            FROM rides
            WHERE start_time IS NOT NULL AND start_time <> ''
        """
        params = []
        if year:
            sql += " AND substr(start_time,1,4) = ?"
            params.append(year)
        sql += " GROUP BY ym ORDER BY ym"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ---------- 个人资料 / 车辆 ----------
    def get_athlete(self) -> dict:
        row = self.conn.execute("SELECT * FROM athlete WHERE id=1").fetchone()
        return dict(row) if row else {}

    def save_athlete(self, data: dict) -> None:
        values = {f: data.get(f) for f in ATHLETE_FIELDS}
        values["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cols = list(values)
        self.conn.execute(
            f"INSERT INTO athlete(id, {','.join(cols)}) VALUES(1, {','.join('?' * len(cols))}) "
            f"ON CONFLICT(id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in cols),
            [values[c] for c in cols],
        )
        self.conn.commit()

    def get_bike(self) -> dict:
        row = self.conn.execute(
            "SELECT * FROM bikes ORDER BY is_default DESC, id LIMIT 1").fetchone()
        return dict(row) if row else {}

    def save_bike(self, data: dict) -> int:
        values = {f: data.get(f) for f in BIKE_FIELDS}
        values["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bike_id = data.get("id")
        if bike_id:
            cols = list(values)
            self.conn.execute(
                f"UPDATE bikes SET {', '.join(f'{c}=?' for c in cols)} WHERE id=?",
                [values[c] for c in cols] + [bike_id],
            )
            self.conn.commit()
            return int(bike_id)
        cur = self.conn.execute(
            f"INSERT INTO bikes({','.join(list(values) + ['is_default'])}) "
            f"VALUES({','.join('?' * (len(values) + 1))})",
            [values[c] for c in values] + [1],
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def close(self):
        self.conn.close()
