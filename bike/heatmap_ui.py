"""骑行热力图窗口：选时间范围 -> 生成 -> 预览 -> 导出 PNG。"""
import os

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                             QMessageBox, QProgressBar, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from datetime import datetime

from . import heatmap
from .config import DATA_DIR
from .theme import QSS

SIZES = (("标准 · 宽约 1200px", 1200), ("高清 · 宽约 2000px", 2000),
         ("超清 · 宽约 3200px", 3200))


class HeatmapWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(object)      # HeatResult
    failed = pyqtSignal(str)

    def __init__(self, db, spec, parent=None):
        super().__init__(parent)
        self.db = db
        self.spec = spec
        self._tmp_db = None

    def run(self):
        from .db import RideDB
        try:
            self._tmp_db = RideDB(self.db.path)   # 线程内独立连接
            res = heatmap.render(self._tmp_db, self.spec,
                                 progress=lambda i, t, m: self.progress.emit(i, t, m))
            self.done.emit(res)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            if self._tmp_db is not None:
                try:
                    self._tmp_db.close()
                except Exception:  # noqa: BLE001
                    pass


class HeatmapDialog(QDialog):
    """年度 / 月度骑行热力图。"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.worker = None
        self.result = None
        self._image: QImage | None = None

        self.setWindowTitle("骑行热力图")
        self.resize(980, 820)
        self.setStyleSheet(QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        title = QLabel("骑行热力图")
        title.setObjectName("RideTitle")
        root.addWidget(title)

        hint = QLabel("把一段时间里的所有轨迹叠在一张深色地图上：同一条路骑得越多，颜色越红、线条越粗。"
                      "底图用深色街道瓦片（不带地名），纯本地绘制，可导出 PNG。")
        hint.setObjectName("Dim")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ---------------- 控制行 ----------------
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("范围"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("全部记录", "all")
        self.cmb_mode.addItem("按年份（年度）", "year")
        self.cmb_mode.addItem("按月份（月度）", "month")
        self.cmb_mode.setFixedWidth(132)
        row.addWidget(self.cmb_mode)

        self.cmb_year = QComboBox()
        self.cmb_year.setFixedWidth(84)
        row.addWidget(self.cmb_year)

        self.cmb_month = QComboBox()
        self.cmb_month.setFixedWidth(76)
        for m in range(1, 13):
            self.cmb_month.addItem(f"{m} 月", m)
        self.cmb_month.setCurrentIndex(datetime.now().month - 1)
        row.addWidget(self.cmb_month)

        row.addSpacing(6)
        row.addWidget(QLabel("底图"))
        self.cmb_style = QComboBox()
        self.cmb_style.addItem("深色街道 · 无地名", "dark")
        self.cmb_style.addItem("卫星影像 · 压暗", "sat")
        self.cmb_style.addItem("高德路网 · 线稿", "line")
        self.cmb_style.setFixedWidth(150)
        row.addWidget(self.cmb_style)

        row.addWidget(QLabel("输出"))
        self.cmb_size = QComboBox()
        for label, px in SIZES:
            self.cmb_size.addItem(label, px)
        self.cmb_size.setCurrentIndex(1)
        self.cmb_size.setFixedWidth(160)
        row.addWidget(self.cmb_size)

        row.addStretch(1)
        self.btn_gen = QPushButton("生成热力图")
        self.btn_gen.clicked.connect(self.generate)
        row.addWidget(self.btn_gen)
        self.btn_export = QPushButton("导出图片")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_image)
        row.addWidget(self.btn_export)
        root.addLayout(row)

        # ---------------- 预览 ----------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview = QLabel("选好范围后点「生成热力图」。\n\n提示：第一次生成的区域要下载底图瓦片，"
                              "慢一点；同样的区域之后再生成会用本地缓存。")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("Dim")
        self.scroll.setWidget(self.preview)
        root.addWidget(self.scroll, 1)

        # ---------------- 底部 ----------------
        bar = QHBoxLayout()
        self.lbl_stats = QLabel("")
        self.lbl_stats.setObjectName("Dim")
        bar.addWidget(self.lbl_stats, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.hide()
        bar.addWidget(self.progress)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        self.reload_years()
        self.cmb_mode.currentIndexChanged.connect(self._sync_controls)
        self.cmb_year.currentIndexChanged.connect(self._sync_controls)
        self._sync_controls()

    # ------------------------------------------------ 数据
    def reload_years(self):
        cur = self.cmb_year.currentText()
        self.cmb_year.blockSignals(True)
        self.cmb_year.clear()
        for y in (self.db.years() or []):
            self.cmb_year.addItem(str(y), str(y))
        if not self.cmb_year.count():
            self.cmb_year.addItem("无记录", "")
        idx = self.cmb_year.findText(cur) if cur else -1
        self.cmb_year.setCurrentIndex(max(0, idx))
        self.cmb_year.blockSignals(False)

    def _sync_controls(self):
        mode = self.cmb_mode.currentData()
        use_year = mode in ("year", "month")
        self.cmb_year.setEnabled(use_year)
        self.cmb_month.setEnabled(mode == "month")

    # ------------------------------------------------ 生成
    def generate(self):
        if self.worker is not None and self.worker.isRunning():
            return
        mode = self.cmb_mode.currentData()
        year = self.cmb_year.currentData() or None
        spec = heatmap.HeatSpec(
            mode=mode,
            year=year if mode in ("year", "month") else None,
            month=self.cmb_month.currentData() if mode == "month" else None,
            style=self.cmb_style.currentData(),
            target_px=self.cmb_size.currentData(),
        )
        if mode != "all" and not spec.year:
            QMessageBox.information(self, "提示", "库里还没有可用的年份数据。")
            return
        self.btn_gen.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.lbl_stats.setText("正在生成…")

        self.worker = HeatmapWorker(self.db, spec, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, i, total, msg):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(i)
        self.lbl_stats.setText(msg)

    def _on_done(self, res):
        self.result = res
        self._image = res.image
        self.progress.hide()
        self.btn_gen.setEnabled(True)
        self.btn_export.setEnabled(True)
        st = res.stats
        self.lbl_stats.setText(
            f"{st['rides']} 次骑行 · {st['total_km']:.1f} km · 最高重复 {st['max_repeat']} 次 · "
            f"画布 {st['width']}×{st['height']} · 缩放 z{st['zoom']}"
            + (f" · 跳过 {st['skipped']} 条无轨迹记录" if st.get("skipped") else ""))
        self._refresh_preview()

    def _on_failed(self, msg):
        self.progress.hide()
        self.btn_gen.setEnabled(True)
        self.lbl_stats.setText("")
        QMessageBox.warning(self, "生成失败", msg)

    def _refresh_preview(self):
        if not self._image:
            return
        area = self.scroll.viewport().size()
        pm = QPixmap.fromImage(self._image)
        if pm.width() > area.width() - 8 or pm.height() > area.height() - 8:
            pm = pm.scaled(max(200, area.width() - 8), max(200, area.height() - 8),
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pm)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_preview()

    # ------------------------------------------------ 导出
    def export_image(self):
        if not self._image:
            return
        label = heatmap.range_label(self.cmb_mode.currentData(),
                                    self.cmb_year.currentData(),
                                    self.cmb_month.currentData()) if self.cmb_mode.currentData() != "all" else "全部"
        default = str(DATA_DIR / f"骑行热力图_{label.replace(' ', '')}.png")
        path, _ = QFileDialog.getSaveFileName(self, "导出热力图", default,
                                             "PNG 图片 (*.png);;JPEG 图片 (*.jpg)")
        if not path:
            return
        fmt = "JPG" if path.lower().endswith((".jpg", ".jpeg")) else "PNG"
        if self._image.save(path, fmt):
            self.lbl_stats.setText(f"已导出：{os.path.basename(path)}　（距上次统计）"
                                   + self.lbl_stats.text().split("（距上次统计）")[-1])
            QMessageBox.information(self, "已导出", f"图片已保存到：\n{path}")
        else:
            QMessageBox.warning(self, "导出失败", "写文件失败，换个目录试试。")

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)


def show_heatmap(parent, db):
    dlg = HeatmapDialog(db, parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
