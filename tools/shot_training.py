"""验证训练计划窗口：生成课表、截图、导出一份 Markdown 预览。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from bike import training  # noqa: E402
from bike.db import RideDB  # noqa: E402
from bike.theme import QSS  # noqa: E402
from bike.training_ui import TrainingPlanDialog  # noqa: E402

app.setStyleSheet(QSS)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


db = RideDB()

# 1) 逻辑自检：三个目标 × 次数组合
for goal in ("auto", "endurance", "speed", "health"):
    for per_week in (3, 5):
        prof = training.build_profile(db, 90)
        plan = training.build_plan(prof, weeks=4, per_week=per_week, goal=goal)
        sessions = len(plan["sessions"])
        km = sum(plan["week_km"].values())
        print(f"{goal:10s} 每周{per_week}次 -> {sessions} 节课, 合计 {km:.0f} km, "
              f"周量 {list(plan['week_km'].values())}")
prof = training.build_profile(db, 90)
print("profile:", prof.rides_per_week, "次/周", prof.km_per_week, "km/周",
      "基准", prof.base_speed, "km/h")

# 2) 界面截图 + 导出预览
dlg = TrainingPlanDialog(db)
dlg.resize(1080, 780)
dlg.show()
dlg.refresh()
wait(900)
dlg.grab().save(os.path.join(ROOT, "data", "_train.png"))
print("shot ok, 课表行数:", dlg.table.rowCount())

md = training.plan_to_markdown(dlg.plan)
out = os.path.join(ROOT, "data", "训练计划_预览.md")
with open(out, "w", encoding="utf-8") as f:
    f.write(md)
print("md ok ->", out, len(md), "chars")

# 3) 默认（耐力目标 / 每周 3 次）也导一份给用户
dlg.cmb_goal.setCurrentIndex(1)
dlg.cmb_per_week.setCurrentIndex(1)
dlg.regenerate()
wait(300)
md2 = training.plan_to_markdown(dlg.plan)
with open(os.path.join(ROOT, "data", "训练计划.md"), "w", encoding="utf-8") as f:
    f.write(md2)
print("default plan -> data/训练计划.md")

dlg.close()
db.close()
print("done")
