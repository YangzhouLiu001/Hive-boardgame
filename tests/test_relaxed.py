# -*- coding: utf-8 -*-
"""只有官方规则：界面上没有规则开关、状态栏写明官方规则、窄门只认两侧同时被占。

关键约定（用户拍板）：
  两侧同时被占 → 滑不过去；只被一侧挡着 → 可以侧身挤过去。
  以前那套「任意一侧被占就走不了」是理解错误，界面和说明里都不许再出现。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402

uimod.enable_dpi()
FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


class Ev:
    def __init__(s, x, y):
        s.x = x
        s.y = y


SHORT = {"q": "queen", "b": "beetle", "s": "spider", "g": "grasshopper",
         "a": "ant"}


def load_board(g, board, turn):
    """直接把局面摆进 g，供界面测试用。"""
    for pos, items in board.items():
        for tag in items:
            k = SHORT[tag[0]]
            o = int(tag[1])
            uid = next(u for u in g.hand[o] if g.pieces[u][1] == k)
            g.hand[o].remove(uid)
            g.stacks.setdefault(pos, []).append(uid)
            g.where[uid] = pos
            g.placed[o] += 1
            if k == "queen":
                g.queen_pos[o] = pos
    g.turn_no = {0: 8, 1: 8}
    g.turn = turn


# 被自家两枚棋子夹在角上的黑蜂后：两个出口都只被一侧挡着
SANDWICH = {(0, 0): ["q1"], (1, 0): ["g1"], (0, 1): ["s1"], (0, 2): ["g0"],
            (1, 2): ["b0"], (2, 1): ["q0"], (0, 3): ["g0"]}
# 四周被占 5 格、只剩北面一个口子：每个出口的两侧都被塞满
SURROUND = {(0, 0): ["q1"], (1, -1): ["b0"], (1, 0): ["b0"], (0, 1): ["a0"],
            (-1, 1): ["b1"], (-1, 0): ["s1"], (-2, 0): ["s1"],
            (2, -1): ["q0"], (2, 0): ["g1"], (-2, 2): ["g0"]}

uimod.messagebox.showinfo = lambda *a, **k: None
root = tk.Tk()
app = uimod.HiveApp(root)
root.update()
# 固定成两人对战，免得受上次保存的设置影响
app.start_new(["白方", "黑方"], [], "human", 2, 1)
root.update()

print("[只有官方规则]")
check("官方规则" in app.status.cget("text"),
      "状态栏写明官方规则：%s" % app.status.cget("text").strip()[-16:])
d = uimod.NewGameDialog(app)
root.update()
check(not hasattr(d, "relaxed"), "新局对话框里没有规则开关")
d.destroy()
txt = uimod.RulesDialog.TEXT
check("强规则" not in txt and "弱规则" not in txt,
      "规则说明里没有强弱规则对比")
check("两侧" in txt and "同时" in txt, "规则说明直接写「两侧同时被占」")

print("[只被一侧挡着：蜂后能挤过去]")
g = app.game
load_board(g, SANDWICH, 1)
app.history = []
app.redraw()
app._update_side()
root.update()
q = g.top(g.queen_pos[1])
app._select_uid(q, 1)
root.update()
xs = sorted(app.dests)
check(xs == [(-1, 1), (1, -1)], "蜂后高亮出东北、西南两个落点：%s" % (xs,))
px, py = app.to_screen((-1, 1))
app.on_click(Ev(px, py))
root.update()
check(g.where[q] == (-1, 1), "点一下就走到了西南格")

print("[悔棋重建后仍然是官方规则]")
app.undo()
root.update()
h = app.game
check(h._slide_ok((0, 0), (1, 0), {(1, -1)}) is True,
      "单侧被占：能滑过去")
check(h._slide_ok((0, 0), (1, 0), {(1, -1), (0, 1)}) is False,
      "两侧被占：滑不过去")

print("[两侧都被塞满：蜂后一步也走不了]")
app.start_new(["白方", "黑方"], [], "human", 2, 1)
root.update()
g = app.game
load_board(g, SURROUND, 1)
app.history = []
app.redraw()
app._update_side()
root.update()
q = g.top(g.queen_pos[1])
app._select_uid(q, 1)
root.update()
check(app.dests == {}, "被围 5 面的蜂后没有落点（实际 %s）" % (app.dests,))

root.update()
root.destroy()

print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("官方规则自测全部通过 ✔")
