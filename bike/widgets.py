"""可复用小部件。"""
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("Card")
        self.setMinimumHeight(64)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 8)
        lay.setSpacing(1)
        self.t = QLabel(title)
        self.t.setObjectName("CardTitle")
        self.v = QLabel("--")
        self.v.setObjectName("CardValue")
        self.s = QLabel("")
        self.s.setObjectName("CardSub")
        lay.addWidget(self.t)
        lay.addWidget(self.v)
        lay.addWidget(self.s)

    def set(self, value: str, sub: str = ""):
        self.v.setText(value)
        self.s.setText(sub)
