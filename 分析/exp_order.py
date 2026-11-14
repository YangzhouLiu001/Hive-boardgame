# -*- coding: utf-8 -*-
"""实验：给搜索加上「防守着法也进候选」的排序，看能否不靠权重改进棋力。

    python 分析/exp_order.py "棋谱/xxx.hive" 43 [--order atk|mix|mix2]
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import hex_dist, neighbors  # noqa: E402


def order_atk(g, mv, me, maxing):
    tgt = g.queen_pos[1 - me] if maxing else g.queen_pos[me]
    d = hex_dist(mv.to, tgt) if tgt is not None else 0
    return (d, 0 if mv.kind == "place" else 1)


def order_mix(g, mv, me, maxing):
    """我方节点：攻(靠近敌后) 与 守(靠近自家蜂后) 都进来。"""
    if not maxing:
        return order_atk(g, mv, me, maxing)
    enq, myq = g.queen_pos[1 - me], g.queen_pos[me]
    d_atk = hex_dist(mv.to, enq) if enq is not None else 9
    d_def = hex_dist(mv.to, myq) if myq is not None else 9
    # 撤自家气口 / 压住对方气口 也算防守
    if myq is not None and mv.frm is not None and mv.frm in neighbors(myq):
        d_def = 0
    return (min(d_atk, d_def), 0 if mv.kind == "place" else 1)


def order_mix2(g, mv, me, maxing):
    """攻/守各排一半：用 (类别, 距离) 保证两类都进前 N。"""
    enq, myq = g.queen_pos[1 - me], g.queen_pos[me]
    d_atk = hex_dist(mv.to, enq) if enq is not None else 9
    d_def = hex_dist(mv.to, myq) if myq is not None else 9
    if myq is not None and mv.frm is not None and mv.frm in neighbors(myq):
        d_def = 0
    if not maxing:
        return (0, d_atk, 0 if mv.kind == "place" else 1)
    # 距离 0/1 的攻防都排前面
    return (0 if min(d_atk, d_def) <= 1 else 1, min(d_atk, d_def),
            0 if mv.kind == "place" else 1)


ORDERS = {"atk": order_atk, "mix": order_mix, "mix2": order_mix2}


def run(path, no, order, level=3):
    A._order_key = ORDERS[order]
    steps, _f = ana.replay(path)
    for n, rec, g, actual in steps:
        if n != no:
            continue
        me = ana.AI_SIDE
        t0 = time.time()
        best = A.choose_move(A.clone(g), level, None, use_book=False)
        print("%-12s 第 %d 手 选中 %-24s （实际 %-24s）%.1fs" % (
            order, n, ana.fmt_mv(g, best) if best else None,
            ana.fmt_mv(g, actual), time.time() - t0))


if __name__ == "__main__":
    path, no = sys.argv[1], int(sys.argv[2])
    order = "atk"
    if "--order" in sys.argv:
        order = sys.argv[sys.argv.index("--order") + 1]
    level = 3
    if "--level" in sys.argv:
        level = int(sys.argv[sys.argv.index("--level") + 1])
    run(path, no, order, level)
