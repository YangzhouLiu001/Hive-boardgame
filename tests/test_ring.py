# -*- coding: utf-8 -*-
"""蜂后气口预警自测：不分兵种的「输棋预警」是否算对。

关键约定：
  1. k = 对手一手能同时盯住的**独立气口数**（一个棋子只能占一格，所以是匹配）。
  2. libs = 6 − 已占邻格，跟占格子的是谁无关 —— 自家堵气和敌子堵气一样致命。
  3. ring_lost = 气口全被盯住（k ≥ libs）且蜂后跑不掉（esc = 0）。
  4. 只在蜂后吃紧（气口 ≤ 4）时才付这笔计算成本。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "分析"))

from hive import ai as ailib  # noqa: E402
from hive.rules import Game, neighbors  # noqa: E402

FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


SHORT = {"q": "queen", "b": "beetle", "s": "spider", "g": "grasshopper",
         "a": "ant", "p": "pillbug"}


def build(board, turn, turn_no=8):
    g = Game([], first_player=0)
    for pos, items in board.items():
        for tag in items:
            k = SHORT[tag[0]]
            o = int(tag[1])
            uid = next(u for u in g.hand[o] if g.pieces[u][1] == k)
            g.hand[o].remove(uid)
            g.stacks.setdefault(tuple(pos), []).append(uid)
            g.where[uid] = tuple(pos)
            g.placed[o] += 1
            if k == "queen":
                g.queen_pos[o] = tuple(pos)
    g.turn_no = {0: turn_no, 1: turn_no}
    g.turn = turn
    return g


print("[一个棋子只能占一格：匹配，而不是简单相加]")
check(ailib._max_match({("A",): {"p1"}, ("B",): {"p1"}}) == 1,
      "同一枚棋子盯两个气口，只能算 1 个")
check(ailib._max_match({("A",): {"p1", "p2"}, ("B",): {"p3"}}) == 2,
      "两个气口、三枚候补，算 2 个")
check(ailib._max_match({("A",): {"p1", "p2", "p3"}}) == 1,
      "三个候补抢一个气口，算 1 个")
check(ailib._max_match({}) == 0, "没有气口 = 0")

print("[气数只看格子被占，不看是谁占的]")
g = build({(0, 0): ["q1"], (1, 0): ["a0"], (0, 1): ["a1"], (1, 1): ["q0"]}, 1)
libs, k, slack, esc = ailib.ring_danger(g, 1)
check(libs == 4, "蜂后 6 邻格占了 2 个 -> 4 口气（实际 %d）" % libs)
check(esc == 2, "官方规则下两个出口各只被一侧挡着，蜂后还能挤出去（实际 %d）" % esc)
# 换成自家棋子占同一格：气口数必须一样
g2 = build({(0, 0): ["q1"], (1, 0): ["a1"], (0, 1): ["a1"], (1, 1): ["q0"]}, 1)
libs2, _k2, _s2, esc2 = ailib.ring_danger(g2, 1)
check(libs2 == 4, "自家子堵在同一格，气口数也是 4（实际 %d）" % libs2)
check(esc2 == esc, "谁占着那两格都一样，活路数不变（%d）" % esc2)

print("[对照真实棋谱：2252 第 43 手（黑方被逼到 2 口气）]")
games = os.path.join(ROOT, "棋谱")
target = None
for fn in sorted(os.listdir(games)):
    if fn.endswith("20261113-2252.hive"):
        target = os.path.join(games, fn)
if target is None:
    print("  (跳过：找不到棋谱)")
else:
    import ana
    steps, _f = ana.replay(target)
    pos43 = None
    for n, rec, before, mv in steps:
        if n == 43:
            pos43 = (before, mv)
    before, actual = pos43
    h = ailib._apply(before, actual)
    libs, k, slack, esc = ailib.ring_danger(h, 1)
    check(libs == 2, "走后只剩 2 口气（实际 %d）" % libs)
    check(k == 2, "白方一手能同时盯住 2 口（实际 %d）" % k)
    check(esc == 0, "蜂后跑不掉（实际 %d）" % esc)
    terms = ailib.ring_terms(h, 1)
    check("ring_lost" in terms, "判定为「两步内被围死」的形状")
    # 分级预警（老师的设计）：一步被杀 > 两步 > 三步；我方 V 同构且更大
    check(ailib.W["t1"] < ailib.W["t2"] < ailib.W["t3"] <= 0,
          "T 分级单调：T>TT>TTT（%s/%s/%s）" % (ailib.W["t1"], ailib.W["t2"], ailib.W["t3"]))
    check(ailib.W["v1"] > ailib.W["v2"] > ailib.W["v3"] >= 0,
          "V 分级单调：V>VV>VVV（%s/%s/%s）" % (ailib.W["v1"], ailib.W["v2"], ailib.W["v3"]))
    check(ailib.W["v1"] > abs(ailib.W["t1"]),
          "同级别下先手方占优：V > T")

print("[吃紧才算：开局气口多的时候不花这笔钱]")
g3 = Game([], first_player=0)
g3.apply(g3.legal_moves()[0])
mv = g3.legal_moves()[0]
h = ailib._apply(g3, mv)
terms = ailib.ring_terms(h, 1)
check("ring_lost" not in terms and "ring_hurry" not in terms,
      "开局没有「被围死 / 只剩一口气」的预警（实际 %s）" % list(terms))
check(all(abs(v) < 1e-9 for kk, v in terms.items() if kk.startswith("ring_")),
      "开局的 ring_* 项权重为 0，不花这笔钱（实际 %s）" % terms)

print("[回归：2252 第 43 手不再走「三步内必死」的那一手]")
if target is None:
    print("  (跳过：找不到棋谱)")
else:
    # 求解器验证过的 4 条活路
    ALIVE = {
        "蜘蛛(-2,4)→(0,2)", "蜘蛛(-2,4)→(-1,3)",
        "兵蚁(3,-1)→(0,2)", "甲虫(-3,3)→(-2,3)",
    }
    # 用难度 3（用户实际下的档位）。
    # 已知缺口：难度 2（1.2 秒）在这个局面上会选兵蚁(-4,0)→(-4,2)，不是活路。
    # 原因见开发笔记：v2037 的 opp_moves/mobility 权重很重，1.2 秒搜不到 5 层，
    # 根节点的气口先验在各条候选上又是同一个常数（全都 -300），无法区分。
    chosen = ailib.choose_move(ailib.clone(before), 3, None, use_book=False)
    txt = ana.fmt_mv(before, chosen) if chosen else None
    check(txt in ALIVE, "选中 %s（活路 %s）" % (txt, "、".join(sorted(ALIVE))))

print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("蜂后气口预警自测全部通过 ✔")
