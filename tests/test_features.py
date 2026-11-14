# -*- coding: utf-8 -*-
"""新功能自测：先手、鼠妇搬运、棋谱复盘。"""
import os
import sys

ROOT = r"C:\Users\16402\Desktop\虫虫蜂房"
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402
from hive.rules import Game  # noqa: E402

uimod.enable_dpi()
FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


class Ev:
    def __init__(s, x, y):
        s.x, s.y = x, y


uimod.messagebox.showinfo = lambda *a, **k: None
root = tk.Tk()
app = uimod.HiveApp(root)
root.update()

print("[先手可选]")
app.start_new(["我", "电脑"], [], "ai", 2, 1, 1)
root.update()
check(app.game.turn == 1, "黑方先手时轮到黑方")
check(app.ai_side == 1, "电脑下黑方")
check(app.busy or app.game.moves, "电脑先手会自动开局")
app.busy = False

app.start_new(["我", "电脑"], [], "ai", 2, 1, 0)
root.update()
check(app.game.turn == 0, "白方先手时轮到白方")
check(app.my_turn(), "白方先手时是玩家走")
check(app.game.first_player == 0, "first_player 记录正确")

print("[鼠妇搬运]")
SHORT = {"q": "queen", "b": "beetle", "s": "spider", "g": "grasshopper",
         "a": "ant", "p": "pillbug"}
g = Game(["pillbug"], first_player=0)
for pos, items in {(0, 0): ["p0"], (0, 1): ["a1"], (1, 0): ["q0"], (1, 1): ["q1"]}.items():
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
g.turn = 0
app.game = g
app.history = []
app.versus = "human"
app.redraw()
root.update()
pb = g.top((0, 0))
app._select_uid(pb, 0)
root.update()
check(len(app.carryable) == 2, "鼠妇列出 2 枚可搬的棋子（实际 %d）" % len(app.carryable))
target = g.top((0, 1))
app._start_carry(target)
root.update()
check(len(app.carry_dests) == 4, "搬运落点 4 个（实际 %d）" % len(app.carry_dests))
spot = sorted(app.carry_dests)[0]
gx, gy = app.to_screen(spot)
n_before = len(app.history)
app.on_click(Ev(gx, gy))
root.update()
check(len(app.history) == n_before + 1, "点击落点后确实搬了一步")
check(g.where[target] == spot, "被搬的棋子到了 %s" % (spot,))

print("[棋谱复盘]")
app.start_new(["白方", "黑方"], [], "human", 2, 1, 0)
root.update()
# 走 4 步
for i in range(4):
    ms = app.game.legal_moves()
    if not ms:
        break
    mv = [m for m in ms if m.kind == "place"][0]
    app.game.apply(mv)
    app.history.append(mv)
app._rebuild(app.history)
root.update()
check(len(app.history) == 4, "共 4 步")
full_board = dict(app.game.stacks)

app.set_review(2)
root.update()
check(app.review == 2, "复盘到第 2 步")
check(len(app.game.moves) == 2, "棋盘回到第 2 步（实际 %d 步）" % len(app.game.moves))
check(len(app.history) == 4, "完整棋谱没丢（%d 步）" % len(app.history))
check(not app.my_turn(), "复盘时不能落子")

app.step_review(-1)
root.update()
check(app.review == 1, "← 退到第 1 步")
for _ in range(3):
    app.step_review(1)
root.update()
check(app.review is None, "→ 连按到最后一步应回到实时")
check(app.game.stacks == full_board, "回到实时后局面正确")

app.set_review(0)
root.update()
check(len(app.game.stacks) == 0, "退到第 0 步是空盘")
app.set_review(4)
root.update()
check(app.review is None and app.game.stacks == full_board, "点最后一行回到实时")

root.destroy()
print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("新功能自测全部通过 ✔")

