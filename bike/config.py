"""全局配置：路径、高德地图参数、配色。"""
import os
from pathlib import Path

APP_NAME = "PrivateBike"
APP_TITLE = "私人骑行数据 · PrivateBike"

def _app_root() -> Path:
    """源码运行 = 项目根；PyInstaller 打包后 = exe 所在目录（数据跟着 exe 走）。"""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _app_root()
DATA_DIR = ROOT / "data"
TILE_DIR = DATA_DIR / "tiles"
DB_PATH = DATA_DIR / "bike.db"
RIDES_DIR = ROOT / "rides"

# 高德 key：不再硬编码在源码里，按以下顺序读
#   1) 环境变量 AMAP_KEY（推荐，公开仓库用这个）
#   2) data/amap_key.txt（本地文件，data/ 已在 .gitignore 里）
#   3) 项目根 .amap_key
# 注意：栅格瓦片接口本身不需要 key，只有后续要调高德 REST（静态图/逆地理编码）才用得上。
def _load_amap_key() -> str:
    key = (os.environ.get("AMAP_KEY") or "").strip()
    if key:
        return key
    for p in (DATA_DIR / "amap_key.txt", ROOT / ".amap_key"):
        try:
            if p.is_file():
                key = p.read_text(encoding="utf-8-sig").strip()
                if key and not key.startswith("#"):
                    return key
        except OSError:
            pass
    return ""


AMAP_KEY = _load_amap_key()

# 栅格瓦片：{s}=子域 1~4，{x}/{y}/{z}=瓦片编号
TILE_STYLES = {
    "road": "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
    "sat": "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    # Esri「深灰画布」底图：只有道路/水系，没有地名标注；注意它的顺序是 {z}/{y}/{x}
    "esri_dark": ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
                  "World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"),
}
TILE_SIZE = 256
MIN_ZOOM = 3
MAX_ZOOM = 18

# 默认视图（成都）
DEFAULT_CENTER = (30.6590, 104.0650)
DEFAULT_ZOOM = 13

# 配色
COLOR_BG = "#15171b"
COLOR_SURFACE = "#1b1e23"
COLOR_BORDER = "#2a2f36"
COLOR_TEXT = "#dfe3e8"
COLOR_TEXT_DIM = "#8d95a1"
COLOR_ACCENT = "#4da3ff"

TRACK_SLOW = (52, 152, 235)   # 慢：蓝
TRACK_MID = (255, 203, 92)    # 中：黄
TRACK_FAST = (255, 92, 92)    # 快：红
TRACK_SINGLE = (78, 201, 255)

# 多条对比时的轨迹配色
COMPARE_COLORS = ("#4da3ff", "#ffb74d", "#4ec9b0", "#ff6b6b",
                  "#a3e635", "#22d3ee", "#f59e0b", "#94a3b8")


def ensure_dirs() -> None:
    for p in (DATA_DIR, TILE_DIR, RIDES_DIR):
        p.mkdir(parents=True, exist_ok=True)
