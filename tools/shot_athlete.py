"""验证个人中心窗口 + 导入前后能力图对比（截图）。"""
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from bike import athlete  # noqa: E402
from bike.athlete_ui import AthleteDialog, CapabilityCompareDialog  # noqa: E402
from bike.config import DB_PATH  # noqa: E402
from bike.db import RideDB  # noqa: E402
from bike.theme import QSS  # noqa: E402

app.setStyleSheet(QSS)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


db = RideDB()
print("rides:", db.count())

# ---- 个人中心 ----
dlg = AthleteDialog(db)
dlg.resize(1180, 780)
dlg.show()
wait(900)
dlg.grab().save(os.path.join(ROOT, "data", "_athlete.png"))
print("athlete shot ok | overall:", dlg.lbl_overall.text())
print("summary:", dlg.lbl_summary.text())
print("cards:", {k: c.v.text() for k, c in dlg.cards.items()})

# ---- 构造「导入前」基线：复制库并删掉最新一条 ----
tmp = os.path.join(ROOT, "data", "_tmp_cap.db")
shutil.copy(DB_PATH, tmp)
conn = sqlite3.connect(tmp)
cur = conn.execute("SELECT MAX(id) FROM rides")
max_id = cur.fetchone()[0]
conn.execute("DELETE FROM rides WHERE id=?", (max_id,))
conn.commit()
conn.close()
tmp_db = RideDB(tmp)
before = athlete.capability(tmp_db)
tmp_db.close()
after = athlete.capability(db)
print("before overall:", before["overall"], "after:", after["overall"])
for b, a in zip(before["items"], after["items"]):
    print(f"  {a['label']}: {b['score']} -> {a['score']} ({a['text']})")

cmp_dlg = CapabilityCompareDialog(before, after, 1, "手动导入 · 测试对比")
cmp_dlg.resize(780, 660)
cmp_dlg.show()
wait(700)
cmp_dlg.grab().save(os.path.join(ROOT, "data", "_cap_compare.png"))
print("compare shot ok")

cmp_dlg.close()
dlg.close()
db.close()
os.remove(tmp)
print("done")
