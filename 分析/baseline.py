# -*- coding: utf-8 -*-
"""基线：用「重构前」的原始代码路径算静态排名，供重构等价性对比。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import move_text, other  # noqa: E402

GAMES = [
    "白方 vs 黑方 20261113-2252.hive",
    "白方 vs 黑方 20261113-2217.hive",
    "白方 vs 黑方 20261113-2148.hive",
    "白方 vs 黑方 20261113-2132.hive",
    "白方 vs 黑方 20261113-2055.hive",
]


def static_rank_orig(g, me, level=2):
    scored = []
    for mv in g.legal_moves():
        h = A._apply(g, mv)
        v = A.evaluate(h, me)
        if level >= 2 and not h.result:
            if (mv.frm is None and g.pieces[mv.uid][1] == "ant"
                    and g.turn_no[me] <= 3):
                v += (-20.0 if g.turn_no[me] <= 0 else 0.0)
            grew = A._bridges(h, me) - A._bridges(g, me)
            if grew > 0:
                v -= grew * A.W["new_bridge"]
            v += A.control_gain(g, h, me) * A.W["control"]
            v -= A.control_loss(g, h, me, mv.frm) * A.W["control_lost"]
            v -= len(h.legal_moves()) * A.W["opp_moves"]
            v += (A.mobility_value(h, me)
                  - A.mobility_value(h, other(me))) * A.W["mobility"]
        scored.append([round(v, 6), mv])
    scored.sort(key=lambda x: -x[0])
    return scored


def desc(g, mv):
    return move_text(g, {"k": g.pieces[mv.uid][1], "to": list(mv.to),
                         "frm": list(mv.frm) if mv.frm is not None else None,
                         "aux": mv.aux})


def main(argv):
    out = []
    for name in GAMES:
        steps, _final = ana.replay(os.path.join(ROOT, "棋谱", name))
        for n, rec, before, mv in steps:
            if rec.get("p") != ana.AI_SIDE or before.result:
                continue
            rank = static_rank_orig(before, ana.AI_SIDE)
            out.append({"game": name, "n": n,
                        "top": [[v, desc(before, m)] for v, m in rank]})
    path = argv[1] if len(argv) > 1 else "分析/base.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("%d 个局面 -> %s" % (len(out), path))


if __name__ == "__main__":
    main(sys.argv)
