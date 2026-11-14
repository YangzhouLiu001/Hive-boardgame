# -*- coding: utf-8 -*-
"""复刻 choose_move 的三个阶段，看排名是在哪一步被翻掉的。

    python 分析/stages.py "棋谱/xxx.hive" 43 [--level 3]
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
from hive.rules import move_text, other  # noqa: E402


def desc(g, mv):
    return move_text(g, {"k": g.pieces[mv.uid][1], "to": list(mv.to),
                         "frm": list(mv.frm) if mv.frm is not None else None,
                         "aux": mv.aux})


def main(argv):
    path, no = argv[1], int(argv[2])
    level = 3
    if "--level" in argv:
        level = int(argv[argv.index("--level") + 1])
    steps, _f = ana.replay(path)
    for n, rec, g, actual in steps:
        if n != no:
            continue
        me = ana.AI_SIDE
        budget = A.TIME_BUDGET[level]
        deadline = time.time() + budget
        branch = A.MAX_BRANCH[level]
        depth_cap = A.DEPTH_CAP[level]
        print("=" * 70)
        print("第 %d 手，实际 %s（难度 %d）" % (n, desc(g, actual), level))

        scored = []
        for mv in g.legal_moves():
            v, h, t = A.root_terms(g, me, mv, level)
            scored.append((v, mv))
        scored.sort(key=lambda x: -x[0])
        print("[阶段1 静态] 前 6：")
        for i, (v, mv) in enumerate(scored[:6]):
            print("   %d. %-26s %.1f%s" % (i + 1, desc(g, mv), v,
                                           "  <<<实际" if mv.key() == actual.key() else ""))

        cut = min(24, len(scored))
        top = scored[:cut]
        nodes2 = [0]
        tt2 = {}
        dl2 = min(deadline, time.time() + budget * 0.35)
        re_scored = []
        for v1, mv in top:
            if time.time() > dl2:
                re_scored.append((v1, mv))
                continue
            h = A._apply(g, mv)
            if h.result:
                re_scored.append((v1, mv))
                continue
            v2 = A._search(h, me, 2, -A.INF, A.INF, dl2, nodes2, tt2)
            re_scored.append((v2, mv))
        re_scored.sort(key=lambda x: -x[0])
        scored = re_scored + scored[cut:]
        print("[阶段2 二层重排] 前 6：")
        for i, (v, mv) in enumerate(scored[:6]):
            print("   %d. %-26s %.1f%s" % (i + 1, desc(g, mv), v,
                                           "  <<<实际" if mv.key() == actual.key() else ""))

        roots = [m for _s, m in scored[:max(branch, 4)]]
        nodes = [0]
        tt = {}
        best_mv = roots[0]
        for depth in range(1, depth_cap + 1):
            alpha, beta = -A.INF, A.INF
            cur_best, cur_val = None, -A.INF
            per = []
            for mv in roots:
                h = A._apply(g, mv)
                if h.result == "win" and h.winner == me:
                    print("[阶段3] 绝杀：", desc(g, mv))
                    return
                v = A._search(h, me, depth - 1, alpha, beta, deadline, nodes, tt)
                per.append((v, mv))
                if v > cur_val:
                    cur_val, cur_best = v, mv
                if v > alpha:
                    alpha = v
                if time.time() > deadline:
                    break
            per.sort(key=lambda x: -x[0])
            print("[阶段3 迭代加深 第 %d 层] 最佳 %-24s %.1f | 前3 %s" % (
                depth, desc(g, cur_best), cur_val,
                ", ".join("%s %.0f" % (desc(g, m), v) for v, m in per[:3])))
            if cur_best is not None and cur_val > -A.INF:
                best_mv = cur_best
            if time.time() > deadline:
                print("   预算用完（%.1fs）" % budget)
                break
        print("最终：%s%s" % (desc(g, best_mv),
                             "  = 实际" if best_mv.key() == actual.key() else "  ≠ 实际"))
        return


if __name__ == "__main__":
    main(sys.argv)
