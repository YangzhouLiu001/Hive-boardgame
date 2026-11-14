# -*- coding: utf-8 -*-
"""AI 自测：不能自杀、会压蜂后、不随便挪蜂后。"""
import copy
import random
import sys

sys.path.insert(0, r"C:\Users\16402\Desktop\虫虫蜂房")
from hive import ai as ailib  # noqa: E402
from hive.rules import Game  # noqa: E402

FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


SHORT = {"q": "queen", "b": "beetle", "s": "spider", "g": "grasshopper",
         "a": "ant", "p": "pillbug"}


def build(board, turn, exps=()):
    g = Game(list(exps), first_player=0)
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
    return g


print("[绝不能选「立刻输」的一手]")
random.seed(5)
bad = total = 0
for gi in range(20):
    g = Game(["pillbug"], first_player=0)
    for step in range(26):
        if g.result:
            break
        ms = g.legal_moves()
        if not ms:
            break
        g.apply(random.choice(ms))
    if g.result:
        continue
    for lvl in (2, 3):
        mv = ailib.choose_move(copy.deepcopy(g), lvl, random.Random(gi))
        if mv is None:
            continue
        h = copy.deepcopy(g)
        h.apply(mv)
        total += 1
        if h.result == "win" and h.winner != g.turn:
            bad += 1
check(bad == 0, "共 %d 次决策，自杀 %d 次" % (total, bad))

print("[甲虫压制]")
g = build({(0, 0): ["q0"], (1, 0): ["b1"], (1, 1): ["q1"], (0, 1): ["a0"]}, 1)
mv = ailib.choose_move(g, 3, random.Random(7))
climb = (mv is not None and g.pieces[mv.uid][1] == "beetle" and mv.to == (0, 0))
check(climb, "甲虫贴着对方蜂后时会爬上去（选了 %s)" % ((mv.frm, mv.to) if mv else None,))

print("[不随便挪蜂后]")
g = build({(0, 0): ["q1"], (0, 1): ["a1"], (1, 0): ["a0"]}, 1)
done = True
for lvl in (2, 3):
    mv = ailib.choose_move(g, lvl, random.Random(5))
    if mv is None:
        continue
    if mv.kind != "place" and g.pieces[mv.uid][1] == "queen":
        done = False
check(done, "对方蜂后还没落、手里有子时不挪自家蜂后")

print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("AI 自测全部通过 ✔")

