# -*- coding: utf-8 -*-
"""读档 / 复盘 / 看门狗：电脑一定会接着走（不会卡死）。

不依赖 棋谱\ 里有没有文件：自己造一局、存档、再读回来。
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, r"C:\Users\16402\Desktop\虫虫蜂房")
import tkinter as tk  # noqa: E402
from hive import store, ui as uimod  # noqa: E402

uimod.enable_dpi()
uimod.messagebox.showinfo = lambda *a, **k: None
FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


root = tk.Tk()
app = uimod.HiveApp(root)


def pump(sec=1.6):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def human_move():
    ms = [m for m in app.game.legal_moves()
          if app.game.pieces[m.uid][0] == 0]
    if not ms:
        return False
    app._play(ms[0])
    pump()
    return True


app.start_new(["我", "电脑"], [], "ai", 2, 1, 0)
pump(0.4)
for _ in range(2):
    if not human_move():
        break
tmp = os.path.join(tempfile.gettempdir(), "hive_test_load.hive")
store.save_game(tmp, app.game, app.history, app.theme.key, app.versus)
print("测试存档: %d 步，轮到 %d" % (len(app.history), app.game.turn))
check(os.path.exists(tmp), "存档已生成")


def load_and_wait(tag):
    app._load_path(tmp)
    base = len(app.history)
    pump(3.0)
    ok = (len(app.history) > base or app.game.turn != app.ai_side
          or app.game.result)
    check(ok, "%s：读档后电脑接着走（%d -> %d，轮到 %d）"
          % (tag, base, len(app.history), app.game.turn))


print("[直接读档]")
load_and_wait("直接读档")

print("[先复盘，再读档]")
app.set_review(1)
root.update()
check(app.review is not None, "先进入复盘（第 %s 步）" % app.review)
load_and_wait("复盘后读档")
check(app.review is None, "读档把复盘状态清掉了")

print("[看门狗兜底]")
app.busy = False
app.game.turn = app.ai_side
if app.game.result is None:
    before = len(app.history)
    pump(2.6)
    check(len(app.history) != before or app.game.turn != app.ai_side,
          "没人管的电脑被看门狗叫醒（%d -> %d）" % (before, len(app.history)))
else:
    check(True, "对局已结束，跳过")

print("[复盘期间不许乱动]")
n0 = len(app.history)
app.set_review(1)
pump(2.0)
check(len(app.history) == n0, "复盘时步数没变（%d）" % len(app.history))
app.set_review(len(app.history))
pump(2.4)
check(app.review is None, "回到实时")

try:
    os.remove(tmp)
except OSError:
    pass

root.destroy()
print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("读档 / 复盘 / 看门狗全部正常 ✔")
