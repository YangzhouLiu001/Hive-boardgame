# -*- coding: utf-8 -*-
"""原型：蜂后气口的「精确威胁数」。

libs = 蜂后空邻格数
k    = 对手一手能同时威胁到的独立气口数（棋子↔气口 最大匹配）
esc  = 蜂后自己的合法落点数（能不能跑）
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hive.rules import neighbors, other  # noqa: E402


def ring_cells(g, owner):
    q = g.queen_pos[owner]
    if q is None:
        return []
    return [c for c in neighbors(q) if c not in g.stacks]


def fillers(g, victim):
    """victim 每个空邻格 -> 能一手占进去的敌方 uid 集合（精确）。"""
    holes = set(ring_cells(g, victim))
    out = {}
    if not holes:
        return out
    for mv in g.legal_moves(other(victim)):
        if mv.to in holes:
            out.setdefault(mv.to, set()).add(mv.uid)
    return out


def max_matching(cell2pieces):
    """气口 ↔ 棋子 的最大二分匹配（格子最多 6 个，直接匈牙利/回溯）。"""
    cells = list(cell2pieces)
    match_p = {}

    def try_cell(c, seen):
        for u in cell2pieces[c]:
            if u in seen:
                continue
            seen.add(u)
            if u not in match_p or try_cell(match_p[u], seen):
                match_p[u] = c
                return True
        return False

    n = 0
    for c in cells:
        if try_cell(c, set()):
            n += 1
    return n


def escape_count(g, owner):
    q = g.queen_pos[owner]
    if q is None:
        return 0
    top = g.top(q)
    if top is None or g.pieces[top][0] != owner:
        return 0
    n = 0
    for mv in g.legal_moves(owner):
        if mv.uid == top and mv.frm == q:
            n += 1
    return n


def ring_threat(g, owner):
    libs = ring_cells(g, owner)
    if not libs:
        return (0, 0, 0)
    k = max_matching(fillers(g, owner))
    return (len(libs), k, escape_count(g, owner))


if __name__ == "__main__":
    import ana
    path, no = sys.argv[1], int(sys.argv[2])
    steps, _f = ana.replay(path)
    for n, rec, before, mv in steps:
        if n != no:
            continue
        me = ana.AI_SIDE
        print("第 %d 手之前：", )
        print("  实际着法", ana.fmt_mv(before, mv),
              "-> libs/k/esc =", ring_threat(__import__("hive.ai", fromlist=["x"])._apply(before, mv), me))
        rows = []
        for m in before.legal_moves():
            h = __import__("hive.ai", fromlist=["x"])._apply(before, m)
            if h.result:
                continue
            rows.append((ring_threat(h, me), ana.fmt_mv(before, m)))
        rows.sort(key=lambda r: (r[0][0] - r[0][1], r[0][0]))
        print("%-26s %5s %3s %4s" % ("着法", "libs", "k", "esc"))
        for (libs, k, esc), d in rows:
            flag = "  <== 杀手锏" if k < libs else ("  <== 危险" if k >= libs and esc == 0 else "")
            print("%-26s %5d %3d %4d%s" % (d, libs, k, esc, flag))
        break
