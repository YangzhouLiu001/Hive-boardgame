# -*- coding: utf-8 -*-
"""逐手判死：AI 的每一手之后，对手最快几层能强行围死我。

    python 分析/death.py "棋谱/xxx.hive" [--from 5] [--plies 7]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
import solver  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import other  # noqa: E402


def main(argv):
    path = argv[1]
    frm = 1
    plies = 7
    if "--from" in argv:
        frm = int(argv[argv.index("--from") + 1])
    if "--plies" in argv:
        plies = int(argv[argv.index("--plies") + 1])
    steps, final = ana.replay(path)
    print("=" * 70)
    print(os.path.basename(path), "共", len(steps), "手")
    print("%4s %-26s %6s %s" % ("步", "AI 着法", "之后", "对手最快几层围死我"))
    prev = "?"
    for n, rec, before, mv in steps:
        if rec.get("p") != ana.AI_SIDE or before.result:
            continue
        if n < frm:
            continue
        h = A._apply(before, mv)
        if h.result:
            print("%4d %-26s  终局" % (n, ana.fmt_mv(before, mv)))
            continue
        lost, p = solver.lost_in(h, ana.AI_SIDE, plies)
        tag = "已输(%d层)" % p if lost else ("未定" if lost is None else "活着")
        if tag != prev:
            print("%4d %-26s %6s %s    <== 转折" % (n, ana.fmt_mv(before, mv),
                                                  ana.lib(h, ana.AI_SIDE), tag))
            prev = tag
        else:
            print("%4d %-26s %6s %s" % (n, ana.fmt_mv(before, mv),
                                        ana.lib(h, ana.AI_SIDE), tag))


if __name__ == "__main__":
    main(sys.argv)
