# -*- coding: utf-8 -*-
"""统计各分项在真实局面里的大小（平均绝对值 + 极值），看谁在主导评估。

    python 分析/terms.py [--games 6]
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ANA = os.path.join(ROOT, "分析")
if ANA not in sys.path:
    sys.path.insert(0, ANA)

import ana  # noqa: E402
from hive import ai as A  # noqa: E402

GAMES = [
    "白方 vs 黑方 20261114-0151.hive",
    "白方 vs 黑方 20261114-0148.hive",
    "白方 vs 黑方 20261114-0135.hive",
    "白方 vs 黑方 20261113-2252.hive",
    "白方 vs 黑方 20261113-2217.hive",
    "白方 vs 黑方 20261113-2148.hive",
]


def main():
    from collections import defaultdict
    agg = defaultdict(list)
    pos = 0
    for name in GAMES:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        for n, rec, before, mv in steps:
            if rec.get("p") != ana.AI_SIDE or before.result or n < 8:
                continue
            pos += 1
            for m in before.legal_moves():
                _v, _h, t = A.root_terms(before, ana.AI_SIDE, m, 2)
                for k, val in t.items():
                    agg[k].append(val)
    rows = []
    for k, vals in agg.items():
        n = len(vals)
        mean = sum(vals) / n
        mx = max(vals)
        mn = min(vals)
        spread = mx - mn
        rows.append((spread, k, mean, mn, mx, n))
    rows.sort(reverse=True)
    print("局面 %d 个，样本 %d 条" % (pos, len(agg.get("opp_moves", []))))
    print("%-16s %10s %10s %10s %10s" % ("项", "平均", "最小", "最大", "波动幅度"))
    for spread, k, mean, mn, mx, n in rows:
        print("%-16s %10.1f %10.1f %10.1f %10.1f" % (k, mean, mn, mx, spread))


if __name__ == "__main__":
    main()
