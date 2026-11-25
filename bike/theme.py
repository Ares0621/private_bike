"""全局样式表与应用图标。"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

QSS = """
* { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; }
QWidget { background: #15171b; color: #dfe3e8; font-size: 12px; }
QMainWindow, QDialog { background: #15171b; }
#Panel { background: #1b1e23; border: 1px solid #2a2f36; border-radius: 10px; }
#Card { background: #1f232a; border: 1px solid #2b3138; border-radius: 8px; }
#CardTitle { color: #8d95a1; font-size: 11px; background: transparent; }
#CardValue { color: #eaf1f8; font-size: 19px; font-weight: 600; background: transparent; }
#CardSub { color: #717b87; font-size: 10px; background: transparent; }
#RideTitle { font-size: 16px; font-weight: 600; background: transparent; }
#Dim { color: #8d95a1; background: transparent; }
#SectionTitle { color: #cfd7e0; font-size: 12px; font-weight: 600; background: transparent; }
#RideItemTitle { font-size: 13px; font-weight: 600; color: #e6ecf3; background: transparent; }
#RideItemSub { font-size: 11px; color: #8d95a1; background: transparent; }
QListWidget { background: #141619; border: 1px solid #262b31; border-radius: 8px; padding: 4px; outline: none; }
QListWidget::item { border-radius: 6px; padding: 2px; margin: 1px 2px; }
QListWidget::item:selected { background: #21384d; }
QListWidget::item:hover { background: #1c2530; }
QTableWidget { background: #141619; border: 1px solid #262b31; border-radius: 8px; gridline-color: #232830; alternate-background-color: #191d22; selection-background-color: #21384d; }
QTableWidget::item { padding: 4px 8px; border: none; }
QHeaderView::section { background: #1f232a; color: #8d95a1; border: none; padding: 6px 8px; font-weight: 600; }
QPushButton { background: #252b33; border: 1px solid #333b45; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #2d3540; }
QPushButton:pressed { background: #1f252c; }
QPushButton:checked { background: #1d3a52; border: 1px solid #3d6f9c; color: #cfe6ff; }
QPushButton:disabled { color: #5c6470; background: #1e2227; }
QLineEdit { background: #141619; border: 1px solid #262b31; border-radius: 6px; padding: 6px 8px; }
QLineEdit:focus { border: 1px solid #3d6f9c; }
QPlainTextEdit, QTextEdit { background: #141619; border: 1px solid #262b31; border-radius: 8px; padding: 6px; color: #cfd7e0; selection-background-color: #21384d; }
QComboBox { background: #252b33; border: 1px solid #333b45; border-radius: 6px; padding: 5px 8px; }
QComboBox QAbstractItemView { background: #1e2227; border: 1px solid #333b45; selection-background-color: #21384d; }
QDateEdit { background: #252b33; border: 1px solid #333b45; border-radius: 6px; padding: 5px 8px; }
QDateEdit:disabled { color: #6b7280; background: #1b1f25; border: 1px solid #262b31; }
QCheckBox { background: transparent; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #3d444f; background: #141619; }
QCheckBox::indicator:checked { background: #3d8fd6; border: 1px solid #5fa8e6; }
QProgressBar { border: 1px solid #2b3138; border-radius: 4px; background: #141619; height: 8px; text-align: center; }
QProgressBar::chunk { background: #3d8fd6; border-radius: 3px; }
QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:horizontal { width: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #333b45; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #414b57; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QStatusBar { background: #1b1e23; color: #8d95a1; }
"""


def make_app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1d3a52"))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QPen(QColor("#4da3ff"), 5))
    for a, b in zip([(12, 44), (24, 30), (34, 36), (46, 20)], [(24, 30), (34, 36), (46, 20)]):
        p.drawLine(*a, *b)
    p.setPen(QPen(QColor("#ffffff"), 2))
    p.setBrush(QColor("#39d353"))
    p.drawEllipse(9, 41, 8, 8)
    p.setBrush(QColor("#ff5d5d"))
    p.drawEllipse(42, 16, 8, 8)
    p.end()
    return QIcon(pm)
