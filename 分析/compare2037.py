# -*- coding: utf-8 -*-
"""把「用户最满意的 v20261113-2037」和当前版本逐手对比，量出权重被削了多少。

做法：同一批真实局面，对每条合法着法分别算两个版本的「根节点总分」，
在同一局面内减掉均值（因为不同局面绝对值不可比），比较：
  · 平均绝对偏差（分）
  · 两条排名序列的排名相关系数
  · 首选是否一致

    python 分析/compare2037.py [--games 6] [--sets key=value ...]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ANA = os.path.join(ROOT, "分析")
if ANA not in sys.path:
    sys.path.insert(0, ANA)

import ana  # noqa: E402
from hive import ai as cur  # noqa: E402

BACKUP = os.path.join(ROOT, "备份", "v20261113-2037", "src", "hive", "ai.py")

GAMES = [
    "白方 vs 黑方 20261114-1508.hive",
    "白方 vs 黑方 20261114-0151.hive",
    "白方 vs 黑方 20261114-0148.hive",
    "白方 vs 黑方 20261114-0135.hive",
    "白方 vs 黑方 20261113-2252.hive",
    "白方 vs 黑方 20261113-2148.hive",
]


def load_old():
    spec = importlib.util.spec_from_file_location("hive.ai_2037", BACKUP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hive.ai_2037"] = mod
    spec.loader.exec_module(mod)
    return mod


def old_roots(old, g, me):
    """2037 版 choose_move 里的根节点打分循环（原样复刻）。"""
    out = []
    for mv in g.legal_moves():
        h = old._apply(g, mv)
        v = old.evaluate(h, me)
        if not h.result:
            if (mv.frm is None and g.pieces[mv.uid][1] == "ant"
                    and g.turn_no[me] <= 3):
                v += (-20.0 if g.turn_no[me] <= 0 else 0.0)
            grew = old._bridges(h, me) - old._bridges(g, me)
            if grew > 0:
                v -= grew * old.W["new_bridge"]
            v += old.control_gain(g, h, me) * old.W["control"]
            v -= old.control_loss(g, h, me) * old.W["control_lost"]
            v -= len(h.legal_moves()) * old.W["opp_moves"]
            v += (old.mobility_value(h, me) - old.mobility_value(h, old.other(me))) * old.W["mobility"]
        out.append((v, mv))
    return out


def cur_roots(g, me):
    out = []
    cache = {}
    for mv in g.legal_moves():
        v, _h, _t = cur.root_terms(g, me, mv, 2, cache)
        out.append((v, mv))
    return out


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return 1.0
    rx = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: -xs[i]))}
    ry = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: -ys[i]))}
    mx = sum(rx.values()) / n
    my = sum(ry.values()) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = (sum((rx[i] - mx) ** 2 for i in range(n))
           * sum((ry[i] - my) ** 2 for i in range(n))) ** 0.5
    return num / den if den else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--from", dest="frm", type=int, default=8)
    args = ap.parse_args()
    old = load_old()
    me = ana.AI_SIDE
    devs, rhos, agree, n = [], [], 0, 0
    per_game = {}
    for name in GAMES[:args.games]:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        g_dev, g_n = 0.0, 0
        for no, rec, before, mv in steps:
            if rec.get("p") != me or before.result or no < args.frm:
                continue
            a = old_roots(old, before, me)
            b = cur_roots(before, me)
            ka = {m.key(): v for v, m in a}
            kb = {m.key(): v for v, m in b}
            keys = [k for k in ka if k in kb]
            if len(keys) < 4:
                continue
            va = [ka[k] for k in keys]
            vb = [kb[k] for k in keys]
            ma, mb = sum(va) / len(va), sum(vb) / len(vb)
            # 只用"偏离均值"的部分比较（局面间绝对值不可比）
            ca = [x - ma for x in va]
            cb = [x - mb for x in vb]
            scale = (max(ca) - min(ca)) or 1.0
            dev = sum(abs(x - y) for x, y in zip(ca, cb)) / len(keys) / scale
            devs.append(dev)
            rhos.append(spearman(va, vb))
            best_a = max(range(len(keys)), key=lambda i: va[i])
            best_b = max(range(len(keys)), key=lambda i: vb[i])
            agree += (best_a == best_b)
            n += 1
            g_dev += dev
            g_n += 1
        if g_n:
            per_game[name[-14:]] = g_dev / g_n
    print("局面数 %d" % n)
    print("平均归一化偏差 %.3f（0=完全一致，1=差一个满量程）" % (sum(devs) / len(devs)))
    print("平均排名相关 %.3f（1=顺序完全一致）" % (sum(rhos) / len(rhos)))
    print("首选一致率 %.0f%%" % (100.0 * agree / n))
    for k, v in per_game.items():
        print("   %-20s 偏差 %.3f" % (k, v))


if __name__ == "__main__":
    main()
