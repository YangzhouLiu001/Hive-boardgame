# -*- coding: utf-8 -*-
"""打印求解器找到的杀棋/防守主线。"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
import solver  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import move_text  # noqa: E402


def d(g, mv):
    return move_text(g, {"k": g.pieces[mv.uid][1], "to": list(mv.to),
                         "frm": list(mv.frm) if mv.frm is not None else None,
                         "aux": mv.aux})


def line(g, attacker, plies, depth=0, max_depth=8):
    """沿求解器的判定走主线。"""
    pad = "  " * depth
    if plies <= 0:
        print(pad + "（到层数上限）")
        return
    if g.turn == attacker:
        for mv in solver.attack_moves(g, 1 - attacker):
            h = A._apply(g, mv)
            if h.result == "win" and h.winner == attacker:
                print(pad + "攻 " + d(g, mv) + "  ==> 围死，胜")
                return
            if h.result:
                continue
            if not solver._defending(h, attacker, plies - 1, [0], {}):
                print(pad + "攻 " + d(g, mv))
                line(h, attacker, plies - 1, depth + 1)
                return
        print(pad + "攻方找不到强制手")
    else:
        for mv in solver.defense_moves(g, attacker):
            h = A._apply(g, mv)
            if h.result == "win" and h.winner == attacker:
                continue
            if h.result:
                continue
            if not solver._attacking(h, attacker, plies - 1, [0], {}):
                print(pad + "守 " + d(g, mv))
                line(h, attacker, plies - 1, depth + 1)
                return
        print(pad + "守方无解")


def main(argv):
    path, no = argv[1], int(argv[2])
    which = argv[3] if len(argv) > 3 else None      # 指定黑方那一手（子串匹配）
    plies = 5
    steps, _f = ana.replay(path)
    for n, rec, before, mv in steps:
        if n != no:
            continue
        me = ana.AI_SIDE
        if which:
            cand = [m for m in before.legal_moves() if which in d(before, m)]
            if not cand:
                print("找不到着法：", which)
                return
            mv = cand[0]
        print("模拟黑走：" + d(before, mv))
        h = A._apply(before, mv)
        lost, p = solver.lost_in(h, me, 7)
        print("  判定：", "已输(%s层)" % p if lost else ("未知" if lost is None else "活着"))
        tt = {}
        for q in range(1, 8, 2):
            if solver._attacking(h, 1 - me, q, [0], tt):
                print("  白方 %d 层内强杀，主线：" % q)
                line(h, 1 - me, q)
                return
        print("  白方 7 层内杀不了")
        return


if __name__ == "__main__":
    main(sys.argv)
