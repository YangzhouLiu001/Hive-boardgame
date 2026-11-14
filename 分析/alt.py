# -*- coding: utf-8 -*-
"""某一手：列出每条候选着法之后「对手最快几层围死我」——找出真正的救命手。

    python 分析/alt.py "棋谱/xxx.hive" 43 [--plies 7]
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
import solver  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import move_text  # noqa: E402


def desc(g, mv):
    return move_text(g, {"k": g.pieces[mv.uid][1], "to": list(mv.to),
                         "frm": list(mv.frm) if mv.frm is not None else None,
                         "aux": mv.aux})


def main(argv):
    path, no = argv[1], int(argv[2])
    plies = 7
    if "--plies" in argv:
        plies = int(argv[argv.index("--plies") + 1])
    steps, _f = ana.replay(path)
    for n, rec, before, mv in steps:
        if n != no:
            continue
        me = ana.AI_SIDE
        print("=" * 74)
        print("第 %d 手（%s 走）实际：%s" % (n, "AI" if rec.get("p") == me else "人",
                                         desc(before, mv)))
        rows = []
        t0 = time.time()
        for cand in before.legal_moves():
            h = A._apply(before, cand)
            if h.result:
                v = ("赢" if h.winner == me else "输")
            else:
                lost, p = solver.lost_in(h, me, plies)
                v = ("已输%d层" % p) if lost else ("未知" if lost is None else "活着")
            v1, _h, terms = A.root_terms(before, me, cand, 2)
            rows.append((v, v1, desc(before, cand), cand.key() == mv.key(), terms))
        alive = [r for r in rows if r[0] == "活着"]
        print("候选 %d 条，其中「活着」%d 条（用时 %.1fs）" % (len(rows), len(alive),
                                                     time.time() - t0))
        print("%-10s %9s  %-26s %s" % ("判定", "静态分", "着法", "主要分项"))
        rows.sort(key=lambda r: (0 if r[0] == "活着" else 1, -r[1]))
        for v, v1, d, is_act, terms in rows[:28]:
            top = sorted(terms.items(), key=lambda kv: -abs(kv[1]))[:4]
            print("%-10s %9.1f  %-26s %s%s" % (
                v, v1, d, " ".join("%s%+.0f" % (k, val) for k, val in top),
                "   <<< 实际" if is_act else ""))
        return
    print("没有第 %d 手" % no)


if __name__ == "__main__":
    main(sys.argv)
