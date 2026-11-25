"""行者同步界面：内置网页登录窗口 + 同步对话框。

登录窗口是软件自己起的 QtWebEngine 页面，会话 cookie 由程序自己持有并保存到
data/xingzhe_cookies.json（仅本机），用来调行者接口拉取记录。
"""
import os
from datetime import date, timedelta

from PyQt6.QtCore import QDate, Qt, QThread, QUrl, QTimer, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QComboBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from . import xingzhe
from .config import DATA_DIR
from .db import RideDB
from .theme import QSS

LOGIN_URL = "https://www.imxingzhe.com/login"
JS_USER_INFO = """(() => {
  try {
    const x = new XMLHttpRequest();
    x.open('GET', '/api/v1/user/user_info/', false);
    x.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    x.send();
    return x.status + '|' + x.responseText;
  } catch (e) { return 'ERR|' + e; }
})()"""


class XingzheLoginWindow(QDialog):
    """内置浏览器登录窗口。登录成功后自动保存会话并关闭。"""

    logged_in = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录行者")
        self.resize(880, 760)
        self.setStyleSheet(QSS)
        self._cookies: dict[str, str] = xingzhe.load_cookies()
        self._checked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        bar = QHBoxLayout()
        self.lbl = QLabel("请在上方页面登录行者账号（登录页已打开）")
        self.lbl.setWordWrap(True)
        bar.addWidget(self.lbl, 1)
        self.btn_close = QPushButton("完成")
        self.btn_close.clicked.connect(self._finish)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        profile_path = os.path.join(str(DATA_DIR), "webprofile")
        os.makedirs(profile_path, exist_ok=True)
        self.profile = QWebEngineProfile("privatebike-xingzhe", self)
        self.profile.setPersistentStoragePath(profile_path)
        self.profile.setCachePath(os.path.join(profile_path, "cache"))
        self.profile.setHttpUserAgent(xingzhe.UA)
        try:
            self.profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        except Exception:  # noqa: BLE001
            pass
        store = self.profile.cookieStore()
        store.cookieAdded.connect(self._on_cookie_added)
        store.cookieRemoved.connect(self._on_cookie_removed)

        self.view = QWebEngineView(self)
        self.view.setPage(self._make_page())
        self.view.setUrl(QUrl(LOGIN_URL))
        self.view.urlChanged.connect(lambda _: self._schedule_check())
        root.addWidget(self.view, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(2500)
        self._timer.timeout.connect(self._check_login)
        self._timer.start()

    def _make_page(self):
        from PyQt6.QtWebEngineCore import QWebEnginePage
        return QWebEnginePage(self.profile, self.view)

    # ---------- cookie ----------
    def _on_cookie_added(self, cookie):
        try:
            domain = (cookie.domain() or "")
            if "imxingzhe" not in domain:
                return  # 只保留行者站点自己的会话 cookie
            name = bytes(cookie.name()).decode("utf-8", "ignore")
            value = bytes(cookie.value()).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return
        if name:
            self._cookies[name] = value

    def _on_cookie_removed(self, cookie):
        try:
            name = bytes(cookie.name()).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            return
        self._cookies.pop(name, None)

    # ---------- 登录检测 ----------
    def _schedule_check(self):
        QTimer.singleShot(1200, self._check_login)

    def _check_login(self):
        if self._checked:
            return
        self.view.page().runJavaScript(JS_USER_INFO, self._on_user_info)

    def _on_user_info(self, text):
        if self._checked or not text:
            return
        try:
            status, payload = str(text).split("|", 1)
        except ValueError:
            return
        if status != "200":
            return
        try:
            import json
            data = json.loads(payload)
        except ValueError:
            return
        if data.get("code") not in (0, 200):
            return
        info = data.get("data") or {}
        if isinstance(info, dict) and "user" in info:
            info = info["user"] or {}
        name = info.get("username") or info.get("nickname") or info.get("name") or "已登录"
        self._checked = True
        xingzhe.save_cookies(self._cookies)
        self.lbl.setText(f"已登录：{name}（会话已保存到本机）")
        self.btn_close.setText("完成并关闭")
        self.logged_in.emit(str(name))
        QTimer.singleShot(900, self.accept)

    def _finish(self):
        if self._cookies:
            xingzhe.save_cookies(self._cookies)
        self.accept()

    def cookies(self) -> dict:
        return dict(self._cookies)

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class SyncWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(dict)

    def __init__(self, db, cookies: dict, only_recent=None, since=None, until=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.cookies = cookies
        self.only_recent = only_recent
        self.since = since
        self.until = until
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # SQLite 连接不能跨线程复用：这里在本线程内单独开一个连接，用完关掉
        db = None
        try:
            db = RideDB(self.db.path)
            res = xingzhe.sync(db, self.cookies,
                               progress=lambda i, t, m: self.progress.emit(i, t, m),
                               should_stop=lambda: self._stop,
                               only_recent=self.only_recent,
                               since=self.since, until=self.until)
        except Exception as exc:  # noqa: BLE001
            res = {"error": str(exc)}
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:  # noqa: BLE001
                    pass
        self.finished_ok.emit(res)


class XingzheSyncDialog(QDialog):
    """同步行者数据：登录 / 拉取 / 进度。"""

    synced = pyqtSignal(int)   # 新增条数
    sync_started = pyqtSignal()   # 开始同步（主窗口据此抓能力图基线）

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.worker = None
        self.login_window = None

        self.setWindowTitle("同步行者数据")
        self.resize(700, 560)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        title = QLabel("行者（imxingzhe）数据同步")
        title.setObjectName("RideTitle")
        root.addWidget(title)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("Dim")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        # ---------- 时间段 ----------
        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        range_row.addWidget(QLabel("时间范围"))
        self.cmb_range = QComboBox()
        for label, key in (("最近 7 天", "7"), ("最近 30 天", "30"), ("最近 90 天", "90"),
                           ("今年", "year"), ("全部记录", "all"), ("自定义", "custom")):
            self.cmb_range.addItem(label, key)
        self.cmb_range.setCurrentIndex(1)      # 默认最近 30 天，避免每次全量扫
        self.cmb_range.setFixedWidth(120)
        self.cmb_range.currentIndexChanged.connect(self._on_range_changed)
        range_row.addWidget(self.cmb_range)

        today = date.today()
        self.dt_start = QDateEdit(QDate(today.year, 1, 1))
        self.dt_end = QDateEdit(QDate(today.year, today.month, today.day))
        for w in (self.dt_start, self.dt_end):
            w.setDisplayFormat("yyyy-MM-dd")
            w.setCalendarPopup(True)
            w.setFixedWidth(118)
            w.dateChanged.connect(lambda _: self._on_range_changed())
        range_row.addWidget(QLabel("从"))
        range_row.addWidget(self.dt_start)
        range_row.addWidget(QLabel("到"))
        range_row.addWidget(self.dt_end)
        range_row.addStretch(1)
        root.addLayout(range_row)

        self.lbl_range = QLabel("")
        self.lbl_range.setObjectName("Dim")
        self.lbl_range.setWordWrap(True)
        root.addWidget(self.lbl_range)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_login = QPushButton("登录 / 重新登录")
        self.btn_login.clicked.connect(self.open_login)
        self.btn_range = QPushButton("同步所选范围")
        self.btn_range.clicked.connect(lambda: self.start_sync(None, self.current_range()))
        self.btn_stop = QPushButton("停止")
        self.btn_stop.clicked.connect(self.stop_sync)
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_range)
        row.addWidget(self.btn_stop)
        row.addStretch(1)
        root.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.hide()
        root.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("同步日志会显示在这里…")
        root.addWidget(self.log, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)

        self.refresh_status()
        self._on_range_changed()

    # ---------- 状态 ----------
    def _cookies(self) -> dict:
        return xingzhe.load_cookies()

    def refresh_status(self):
        cookies = self._cookies()
        if not cookies:
            self.lbl_status.setText("当前未登录。点「登录 / 重新登录」打开行者登录页，"
                                   "登录一次后会话会保存在本机 data/xingzhe_cookies.json。")
            self.btn_range.setEnabled(False)
            return
        try:
            user = xingzhe.fetch_user(cookies)
            name = user.get("username") or user.get("nickname") or "已登录"
            self.lbl_status.setText(f"已登录：{name}　·　选好下面的时间范围再点同步，"
                                   "只拉这段时间的记录，已导入的会自动跳过。")
            self.btn_range.setEnabled(True)
        except Exception as exc:  # noqa: BLE001
            self.lbl_status.setText(f"会话已失效（{exc}）。请重新登录行者。")
            self.btn_range.setEnabled(False)

    # ---------- 时间段 ----------
    def current_range(self):
        """返回 (since, until)，None 表示不限。"""
        key = self.cmb_range.currentData()
        today = date.today()
        if key == "all":
            return None, None
        if key == "custom":
            s = self.dt_start.date().toPyDate()
            e = self.dt_end.date().toPyDate()
            return (s, e) if s <= e else (e, s)
        if key == "year":
            return date(today.year, 1, 1), today
        days = int(key)
        return today - timedelta(days=days - 1), today

    def _on_range_changed(self):
        key = self.cmb_range.currentData()
        custom = (key == "custom")
        self.dt_start.setEnabled(custom)
        self.dt_end.setEnabled(custom)
        s, e = self.current_range()
        if s is None:
            self.lbl_range.setText("不限时间段：首次同步 / 补历史时用，会把所有年份的记录翻一遍。")
            self.btn_range.setText("同步全部记录")
        else:
            if not custom:   # 预置范围时把两个日期框显示成实际起止，避免看着像可改
                for w, d in ((self.dt_start, s), (self.dt_end, e)):
                    w.blockSignals(True)
                    w.setDate(QDate(d.year, d.month, d.day))
                    w.blockSignals(False)
            self.lbl_range.setText(f"本次只同步 {s.strftime('%Y-%m-%d')} ~ {e.strftime('%Y-%m-%d')} "
                                  "之间的记录（这段时间之外的不会被重新扫描）。")
            self.btn_range.setText("同步所选范围")

    # ---------- 登录 ----------
    def open_login(self):
        if self.login_window is None:
            self.login_window = XingzheLoginWindow(self)
            self.login_window.logged_in.connect(lambda _n: self.refresh_status())
        self.login_window.show()
        self.login_window.raise_()
        self.login_window.activateWindow()

    # ---------- 同步 ----------
    def _log(self, text: str):
        self.log.appendPlainText(text)

    def start_sync(self, only_recent=None, rng=(None, None)):
        cookies = self._cookies()
        if not cookies:
            self.open_login()
            return
        since, until = rng
        self.sync_started.emit()
        self.btn_range.setEnabled(False)
        self.btn_login.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.show()
        if since or until:
            self._log(f"开始同步：{since} ~ {until}")
        else:
            self._log("开始同步：全部记录（按年份分页）")

        self.worker = SyncWorker(self.db, cookies, only_recent, since, until, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, i, total, msg):
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(i)
        self.bar.setFormat(f"{i}/{total}  %p%")
        self._log(f"[{min(i + 1, total)}/{total}] {msg}" if total else msg)

    def _on_done(self, res):
        self.bar.hide()
        self.btn_stop.setEnabled(False)
        self.btn_login.setEnabled(True)
        self.refresh_status()

        if res.get("error"):
            self._log(f"同步失败：{res['error']}")
            QMessageBox.warning(self, "同步失败", str(res["error"]))
            return

        added = len(res.get("added") or [])
        skipped = res.get("skipped") or 0
        no_track = res.get("no_track") or []
        failed = res.get("failed") or []
        self._log("")
        scope = f"（范围 {res['range']}）" if res.get("range") else "（全部记录）"
        self._log(f"完成{scope}：新增 {added} 条，跳过已存在 {skipped} 条，"
                  f"无轨迹 {len(no_track)} 条，失败 {len(failed)} 条。")
        for title in no_track[:20]:
            self._log(f"  · 无轨迹：{title}")
        for title, err in failed[:10]:
            self._log(f"  · 失败：{title} → {err}")
        self.synced.emit(added)
        self.worker = None

    def stop_sync(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self._log("已请求停止，正在结束当前这条…")
        self.btn_stop.setEnabled(False)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(4000)
        if self.login_window:
            self.login_window.close()
            self.login_window = None
        super().closeEvent(event)
