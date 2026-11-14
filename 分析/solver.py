# -*- coding: utf-8 -*-
"""窄化强制杀棋搜索（第二版：攻方只走"填气口"，守方只走"与蜂后相关"的着法）。

判据：attacker 能否在 plies 层内强行围死 defender 的蜂后。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hive import ai as A  # noqa: E402
from hive.rules import hex_dist, neighbors, other  # noqa: E402

BUDGET = 60000


class Abort(Exception):
    pass


def _empty_ring(g, q):
    return [c for c in neighbors(q) if c not in g.stacks]


def attack_moves(g, victim):
    """攻方（=other(victim)）能直接填对方蜂后气口的着法。"""
    q = g.queen_pos[victim]
    if q is None:
        return []
    holes = set(_empty_ring(g, q))
    return [mv for mv in g.legal_moves(other(victim)) if mv.to in holes]


def defense_moves(g, attacker):
    """守方（=other(attacker)）与蜂后相关的着法：蜂后走、撤气口、贴气口、距离 2 的封门。"""
    defender = other(attacker)
    q = g.queen_pos[defender]
    legal = g.legal_moves(defender)
    if q is None:
        return legal
    ring = set(neighbors(q))
    near2 = set()
    for c in ring:
        near2.update(neighbors(c))
    near3 = set()
    for c in near2:
        near3.update(neighbors(c))
    out = []
    for mv in legal:
        if mv.to in ring or mv.frm in ring or mv.to == q:
            out.append((0, mv))
        elif mv.to in near2:
            out.append((1, mv))
        elif mv.frm in near2 or mv.to in near3:
            out.append((2, mv))
    out.sort(key=lambda x: x[0])
    return [m for _k, m in out]


def _defending(g, attacker, plies, count, tt):
    """守方行棋：能否撑过 plies 层。"""
    count[0] += 1
    if count[0] > BUDGET:
        raise Abort()
    if plies <= 0:
        return True
    key = (g._hashes[-1] if g._hashes else 0, plies, 1)
    if key in tt:
        return tt[key]
    defender = other(attacker)
    found = False
    for mv in defense_moves(g, attacker):
        h = A._apply(g, mv)
        if h.result == "win" and h.winner == attacker:
            continue
        if h.result == "win":
            found = True
            break
        if h.result:
            continue
        if not _attacking(h, attacker, plies - 1, count, tt):
            found = True
            break
    if len(tt) < 300000:
        tt[key] = found
    return found


def _attacking(g, attacker, plies, count, tt):
    """攻方行棋：能否在 plies 层内围死。"""
    count[0] += 1
    if count[0] > BUDGET:
        raise Abort()
    if plies <= 0:
        return False
    key = (g._hashes[-1] if g._hashes else 0, plies, 0)
    if key in tt:
        return tt[key]
    ok = False
    for mv in attack_moves(g, other(attacker)):
        h = A._apply(g, mv)
        if h.result == "win" and h.winner == attacker:
            ok = True
            break
        if h.result:
            continue
        if not _defending(h, attacker, plies - 1, count, tt):
            ok = True
            break
    if len(tt) < 300000:
        tt[key] = ok
    return ok


def lost_in(g, victim, max_plies=7):
    """g 是 victim 刚走完的局面。返回 (是否已输 / None 未知, 层数)。"""
    attacker = other(victim)
    tt = {}
    for p in range(1, max_plies + 1, 2):
        count = [0]
        try:
            if _attacking(g, attacker, p, count, tt):
                return True, p
        except Abort:
            return None, None
    return False, None


if __name__ == "__main__":
    import ana
    import time
    steps, _f = ana.replay(sys.argv[1])
    no = int(sys.argv[2])
    for n, rec, before, mv in steps:
        if n == no:
            h = A._apply(before, mv)
            t0 = time.time()
            print(n, ana.fmt_mv(before, mv), "->", solver_lost := lost_in(h, ana.AI_SIDE))
            print("用时 %.1fs" % (time.time() - t0))
            break
