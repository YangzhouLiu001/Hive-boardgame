# -*- coding: utf-8 -*-
"""列出某一步之前的所有棋子/叠层细节。"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
from hive.rules import KIND_NAMES, hex_dist, neighbors  # noqa: E402


def dump(g, me):
    print("棋子清单（我=黑 %d）" % me)
    for o in (0, 1):
        items = []
        for u in g.on_board(o):
            p = g.where[u]
            st = g.stacks[p]
            lv = st.index(u)
            items.append("%s %s%s@%s" % (
                g.pieces[u][1], KIND_NAMES[g.pieces[u][1]],
                "" if lv == 0 else "#%d" % lv, p))
        print("  %s：%s" % ("我" if o == me else "敌", "；".join(items)))
        print("  手牌：%s" % "、".join(
            KIND_NAMES[g.pieces[u][1]] for u in g.hand[o]))
    print("叠层：")
    for p, st in sorted(g.stacks.items()):
        if len(st) > 1:
            print("  %s %s" % (p, " ← ".join(
                "%s%s" % ("我" if g.pieces[u][0] == me else "敌",
                          KIND_NAMES[g.pieces[u][1]]) for u in st)))
    q = g.queen_pos[me]
    if q is not None:
        print("我的蜂后 %s 能否动：%s" % (q, _queen_move_list(g, me)))
    oq = g.queen_pos[1 - me]
    if oq is not None:
        print("对方蜂后 %s 能否动：%s" % (oq, _queen_move_list(g, 1 - me)))


def _queen_move_list(g, owner):
    q = g.queen_pos[owner]
    out = []
    for mv in g.legal_moves(owner):
        if mv.uid == g.top(q) or (g.pieces[mv.uid][0] == owner
                                  and g.where[mv.uid] == q):
            out.append(str(mv.to))
    return out or "不能"


def main(argv):
    path, no = argv[1], int(argv[2])
    steps, _f = ana.replay(path)
    for n, rec, before, mv in steps:
        if n == no:
            print("第 %d 手之前（实际：%s）" % (n, ana.fmt_mv(before, mv)))
            dump(before, ana.AI_SIDE)
            return


if __name__ == "__main__":
    main(sys.argv)
