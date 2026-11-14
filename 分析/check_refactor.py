# -*- coding: utf-8 -*-
"""对比重构前后的静态排名是否完全一致。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import ana  # noqa: E402
from hive import ai as A  # noqa: E402
from hive.rules import move_text  # noqa: E402

GAMES = [
    "白方 vs 黑方 20261113-2252.hive",
    "白方 vs 黑方 20261113-2217.hive",
    "白方 vs 黑方 20261113-2148.hive",
    "白方 vs 黑方 20261113-2132.hive",
    "白方 vs 黑方 20261113-2055.hive",
]


def desc(g, mv):
    return move_text(g, {"k": g.pieces[mv.uid][1], "to": list(mv.to),
                         "frm": list(mv.frm) if mv.frm is not None else None,
                         "aux": mv.aux})


def main(argv):
    base = json.load(open(argv[1] if len(argv) > 1 else "分析/base.json",
                         encoding="utf-8"))
    idx = 0
    bad = 0
    for name in GAMES:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        for n, rec, before, mv in steps:
            if rec.get("p") != ana.AI_SIDE or before.result:
                continue
            b = base[idx]
            idx += 1
            now = []
            for m in before.legal_moves():
                v, _h, _t = A.root_terms(before, ana.AI_SIDE, m, 2)
                now.append([round(v, 6), desc(before, m)])
            now.sort(key=lambda x: -x[0])
            old = sorted([[round(v, 6), d] for v, d in b["top"]],
                         key=lambda x: -x[0])
            now16 = now[:len(old)]
            if old != now16:
                bad += 1
                diff = [(d, ov, nv) for (ov, d), (nv, d2) in zip(old, now16)
                        if ov != nv or d != d2][:5]
                print("不一致：%s 第 %d 手，前 5 处差异 %s" % (name[-14:], n, diff))
    print("对比 %d 个局面，不一致 %d 个" % (idx, bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
