# -*- coding: utf-8 -*-
"""对打测试：两个 AI 版本互相下棋，统计胜负与对局质量。

    python 分析/match.py --games 8 --level 2 [--budget 1.2] [--save 分析/games]

A = 基线（分析/ai_base.py），B = 当前 hive/ai.py。
先手交替。超时回合判和。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ANA = os.path.join(ROOT, "分析")
if ANA not in sys.path:
    sys.path.insert(0, ANA)

import hive  # noqa: E402
from hive import ai as ai_new  # noqa: E402
from hive.rules import Game, other  # noqa: E402


def load_base():
    spec = importlib.util.spec_from_file_location(
        "hive.ai_base", os.path.join(ANA, "ai_base.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hive.ai_base"] = mod
    spec.loader.exec_module(mod)
    return mod


def lib_count(g, owner):
    from hive.rules import neighbors
    q = g.queen_pos[owner]
    if q is None:
        return None
    return 6 - sum(1 for n in neighbors(q) if n in g.stacks)


def play(ai_a, ai_b, first, level, budget, max_moves, rng, seed):
    old_budget = dict(ai_new.TIME_BUDGET)
    ai_new.TIME_BUDGET[level] = budget
    ai_a.TIME_BUDGET[level] = budget
    g = Game([], first_player=first, names=["A", "B"], relaxed=True)
    curve = []
    t0 = time.time()
    while not g.result and len(g.moves) < max_moves:
        eng = ai_a if g.turn == 0 else ai_b
        mv = eng.choose_move(g, level, random.Random(rng.randint(1, 10 ** 9)),
                             use_book=False)
        if mv is None:
            g.result, g.winner, g.reason = "win", other(g.turn), "无棋可动"
            break
        g.apply(mv)
        curve.append((len(g.moves), g.turn, lib_count(g, 0), lib_count(g, 1)))
    ai_new.TIME_BUDGET.clear()
    ai_new.TIME_BUDGET.update(old_budget)
    return g, curve, time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--budget", type=float, default=0.8)
    ap.add_argument("--max-moves", type=int, default=120)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--save", default="")
    args = ap.parse_args()

    base = load_base()
    rng = random.Random(args.seed)
    wins = {0: 0, 1: 0, "draw": 0}
    rows = []
    for i in range(args.games):
        first = i % 2
        # A 执黑，B 执白；first 交替
        t0 = time.time()
        g, curve, dt = play(base, ai_new, first, args.level, args.budget,
                            args.max_moves, rng, args.seed + i)
        if g.result == "win":
            who = "B" if g.winner == 1 else "A"
            wins[g.winner] += 1
        else:
            who = "和"
            wins["draw"] += 1
        last = [c for c in curve[-1:]] or [(0, 0, None, None)]
        rows.append({"i": i, "first": first, "moves": len(g.moves),
                     "who": who, "reason": g.reason, "t": round(dt, 1)})
        print("第 %2d 局：先手 %s  共 %3d 手  胜者 %s（%s）%.0fs  末手气数 白%s/黑%s" % (
            i + 1, "A" if first == 0 else "B", len(g.moves), who, g.reason,
            dt, last[0][2], last[0][3]))
        if args.save:
            os.makedirs(args.save, exist_ok=True)
            with open(os.path.join(args.save, "game%02d.json" % (i + 1)), "w",
                      encoding="utf-8") as f:
                json.dump({"moves": g.moves, "result": g.result,
                           "winner": g.winner, "reason": g.reason,
                           "first": first, "curve": curve}, f,
                          ensure_ascii=False)
    total = sum(wins[k] for k in (0, 1))
    print("A(基线) %d : %d B(新版)   和 %d" % (wins[0], wins[1], wins["draw"]))
    if total:
        print("B 胜率 %.0f%%" % (100.0 * wins[1] / total))


if __name__ == "__main__":
    main()
