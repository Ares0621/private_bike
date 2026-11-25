"""高德栅格瓦片下载与本地缓存（多线程，磁盘 + 内存二级缓存）。"""
import os
import random
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QPixmap

from .config import TILE_DIR, TILE_STYLES

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
REFERER = "https://www.amap.com/"


class _FetchTask(QRunnable):
    def __init__(self, url: str, path: Path, key: str, signal):
        super().__init__()
        self.url, self.path, self.key, self.signal = url, path, key, signal
        self.setAutoDelete(True)

    def run(self):
        try:
            if self.path.exists() and self.path.stat().st_size > 600:
                self.signal.emit(self.key)
                return
            req = urllib.request.Request(self.url, headers={
                "User-Agent": UA, "Referer": REFERER, "Accept": "image/*,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
            if len(data) < 600 or not data[:4].startswith((b"\x89PNG", b"\xff\xd8")):
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.parent / f"{self.path.stem}.{random.getrandbits(24)}.tmp"
            tmp.write_bytes(data)
            try:
                os.replace(tmp, self.path)
            except OSError:
                tmp.unlink(missing_ok=True)
            self.signal.emit(self.key)
        except Exception:
            return


class TileManager(QObject):
    """瓦片管理：pixmap() 取缓存，request() 触发异步下载。"""

    tile_ready = pyqtSignal(str)          # 内部：worker -> 主线程
    tile_loaded = pyqtSignal(str)         # 对外：瓦片可用了

    def __init__(self, style: str = "road", parent=None):
        super().__init__(parent)
        self.style = style
        self._mem: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(8)
        self.tile_ready.connect(self._on_tile_ready)

    # -- key / path -------------------------------------------------
    def key(self, z: int, x: int, y: int) -> str:
        return f"{self.style}/{z}/{x}/{y}"

    def file_path(self, z: int, x: int, y: int) -> Path:
        return Path(TILE_DIR) / self.style / str(z) / str(x) / f"{y}.png"

    def set_style(self, style: str):
        if style == self.style:
            return
        self.style = style
        self._mem.clear()

    # -- 读取 -------------------------------------------------------
    def pixmap(self, z: int, x: int, y: int):
        k = self.key(z, x, y)
        pm = self._mem.get(k)
        if pm is not None:
            return pm
        p = self.file_path(z, x, y)
        if p.exists() and p.stat().st_size > 600:
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._remember(k, pm)
                return pm
        return None

    def request(self, z: int, x: int, y: int):
        k = self.key(z, x, y)
        if k in self._pending or self._mem.get(k) is not None:
            return
        p = self.file_path(z, x, y)
        if p.exists() and p.stat().st_size > 600:
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._remember(k, pm)
                self.tile_loaded.emit(k)
                return
        self._pending.add(k)
        sub = random.randint(1, 4)
        tmpl = TILE_STYLES.get(self.style, TILE_STYLES["road"])
        url = tmpl.format(s=sub, x=x, y=y, z=z)
        self._pool.start(_FetchTask(url, p, k, self.tile_ready))

    def _remember(self, key: str, pm: QPixmap):
        if len(self._mem) > 900:
            for k in list(self._mem)[:300]:
                self._mem.pop(k, None)
        self._mem[key] = pm

    def _on_tile_ready(self, key: str):
        self._pending.discard(key)
        style, z, x, y = key.split("/")
        p = Path(TILE_DIR) / style / z / x / f"{y}.png"
        if p.exists():
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._remember(key, pm)
                self.tile_loaded.emit(key)
