"""WGS-84 ⇄ GCJ-02（火星坐标）互转。

高德/腾讯等国内底图瓦片用的是 GCJ-02，而 GPX/FIT 里的 GPS 原始坐标是 WGS-84；
两者在国内相差几百米（成都约 300~500 m）。把原始坐标直接画到高德瓦片上就会整体偏移，
所以凡是用高德瓦片（road / sat）的地方都要先转 GCJ-02；Esri 等海外瓦片是 WGS-84，保持原样。
"""
import math

_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lat: float, lon: float) -> bool:
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _tlat(x: float, y: float) -> float:
    r = (-100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y
         + 0.2 * math.sqrt(abs(x)))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    r += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return r


def _tlon(x: float, y: float) -> float:
    r = (300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y
         + 0.1 * math.sqrt(abs(x)))
    r += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    r += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    r += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return r


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """GPS 原始坐标 → 高德/国内底图坐标。境外坐标原样返回。"""
    if _out_of_china(lat, lon):
        return lat, lon
    dlat = _tlat(lon - 105.0, lat - 35.0)
    dlon = _tlon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lat + dlat, lon + dlon


def gcj02_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
    """高德坐标 → GPS 原始坐标（迭代逼近，误差 <0.5 m）。"""
    if _out_of_china(lat, lon):
        return lat, lon
    wlat, wlon = lat, lon
    for _ in range(6):
        glat, glon = wgs84_to_gcj02(wlat, wlon)
        wlat += lat - glat
        wlon += lon - glon
    return wlat, wlon


def is_gcj_style(tile_style: str) -> bool:
    """该底图瓦片是否为国内 GCJ-02 坐标系（高德）。"""
    return tile_style in ("road", "sat")
