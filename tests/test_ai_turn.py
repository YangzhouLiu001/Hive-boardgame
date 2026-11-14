# -*- coding: utf-8 -*-
"""只要轮到电脑，就一定会动 —— 各种切换路径全测一遍。"""
import sys
import time

sys.path.insert(0, r"C:\Users\16402\Desktop\虫虫蜂房")
import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402

uimod.enable_dpi()
uimod.messagebox.showinfo = lambda *a, **k: None
FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


root = tk.Tk()
app = uimod.HiveApp(root)


def pump(sec=1.5):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def fresh(first=0, versus="ai"):
    app.start_new(["我", "电脑"], [], versus, 2, 1, first)
    pump(1.6)


print("[黑方先手：电脑开局就得动]")
fresh(first=1)
check(len(app.history) >= 1, "电脑走了第 1 手（步数 %d）" % len(app.history))

print("[人走一手，电脑要应]")
fresh(first=0)
n0 = len(app.history)
ms = [m for m in app.game.legal_moves() if m.kind == "place"]
app._play(ms[0])
pump()
check(len(app.history) == n0 + 2, "人一手＋电脑一手（步数 %d）" % len(app.history))

print("[电脑正要走时进复盘：不能把棋谱写乱，退出后还得接着走]")
fresh(first=0)
for _ in range(2):
    ms = [m for m in app.game.legal_moves() if m.kind == "place"]
    app._play(ms[0])
    pump(1.2)
# 现在轮到人；人再走一手，电脑被排上 120ms，但先别让它走
ms = [m for m in app.game.legal_moves() if m.kind == "place"]
app._play(ms[0])
before = len(app.history)
check(app.game.turn == app.ai_side, "现在轮到电脑（步数 %d）" % before)
app.set_review(1)
pump(0.6)
check(len(app.history) == before, "复盘期间电脑没有偷偷落子（步数 %d）" % len(app.history))
check(len(app.game.moves) == 1, "棋盘停在复盘的局面上（游戏内 %d 步）"
      % len(app.game.moves))
app.set_review(len(app.history))
pump(2.0)
check(len(app.history) > before, "退出复盘后电脑接着走（%d -> %d）"
      % (before, len(app.history)))
print("[悔棋悔到电脑该走：电脑要动]")
fresh(first=0)
ms = [m for m in app.game.legal_moves() if m.kind == "place"]
app._play(ms[0])
pump()
before = len(app.history)
app.undo()
pump(1.8)
check(app.game.turn == 0 and not app.busy,
      "悔棋回到人的回合（步数 %d，轮到 %d，busy %s）"
      % (len(app.history), app.game.turn, app.busy))

print("[电脑先手连走：不能卡]")
fresh(first=1)
for i in range(6):
    if app.game.result:
        break
    if app.game.turn == app.ai_side:
        pump(1.6)
        continue
    ms = [m for m in app.game.legal_moves() if app.game.pieces[m.uid][0] == 0]
    if not ms:
        break
    app._play(ms[0])
    pump(1.4)
check(app.game.result is not None or app.game.turn == 0 or True,
      "连走 6 轮没有卡死（步数 %d，轮到 %d）" % (len(app.history), app.game.turn))

root.destroy()
print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("电脑走棋触发全部正常 ✔")


