# -*- coding: utf-8 -*-
"""单局面诊断：盘面 + 蜂后气口归属 + 每手静态分项 + 危险度。

    python 分析/pos.py "棋谱/xxx.hive" 43 [--search 2] [--top 12]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import KIND_NAMES, hex_dist, neighbors, other  # noqa: E402
from hive.store import _ascii_board  # noqa: E402


def ring_report(g, owner):
    q = g.queen_pos[owner]
    if q is None:
        return "蜂后未落"
    rows = []
    for n in neighbors(q):
        st = g.stacks.get(n) or []
        if not st:
            rows.append("%s 空" % (n,))
        else:
            o = g.pieces[st[-1]][0]
            rows.append("%s %s%s%s" % (
                n, "我" if o == owner else "敌",
                KIND_NAMES[g.pieces[st[-1]][1]],
                "" if len(st) == 1 else "×%d" % len(st)))
    return "；".join(rows)


def show(g, me, n=None, top=12, level=2, search=0):
    print("=" * 80)
    if n is not None:
        print("第 %s 手（轮到%s走，AI=%d）" % (n, "黑" if g.turn else "白", me))
    print(_ascii_board(g))
    print("我的蜂后气口：", ring_report(g, me))
    print("对方蜂后气口：", ring_report(g, other(me)))
    print("气数：我 %s / 对方 %s" % (ana.lib(g, me), ana.lib(g, other(me))))
    rows = []
    for mv in g.legal_moves():
        v, h, terms = A.root_terms(g, me, mv, level)
        if h.result:
            d = "绝杀" if h.winner == me else "自杀"
            rows.append((v, mv, terms, d, 0))
            continue
        t, _w = ana.best_threat(h, me)
        rows.append((v, mv, terms, h, t))
    rows.sort(key=lambda r: -r[0])
    print("%-4s %-24s %9s %7s %s" % ("名", "着法", "静态分", "对手压到", "主要分项"))
    for i, (v, mv, terms, h, t) in enumerate(rows[:top]):
        if isinstance(h, str):
            extra = h
        else:
            extra = "%d 气" % t
        top3 = sorted(terms.items(), key=lambda kv: -abs(kv[1]))[:5]
        txt = " ".join("%s%+.0f" % (k, val) for k, val in top3)
        print("%-4d %-24s %9.1f %7s %s" % (i + 1, ana.fmt_mv(g, mv), v, extra, txt))
    if search:
        best = A.choose_move(A.clone(g), search, None, use_book=False)
        print("搜索(难度%d)选中：%s" % (search, ana.fmt_mv(g, best) if best else None))
    return rows


def main(argv):
    path, no = argv[1], int(argv[2])
    top = 12
    level = 2
    search = 0
    if "--top" in argv:
        top = int(argv[argv.index("--top") + 1])
    if "--search" in argv:
        search = int(argv[argv.index("--search") + 1])
    steps, _f = ana.replay(path)
    for n, rec, before, mv in steps:
        if n == no:
            print("实际走了：%s（%s）" % (
                ana.fmt_mv(before, mv),
                "AI" if rec.get("p") == ana.AI_SIDE else "人"))
            show(before, ana.AI_SIDE, n, top, level, search)
            return
    print("没有第 %d 手" % no)


if __name__ == "__main__":
    main(sys.argv)
