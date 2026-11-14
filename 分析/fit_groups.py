# -*- coding: utf-8 -*-
"""把当前模型的分项按"组"缩放，使总分尽量还原 v20261113-2037 的叠加结果。

做法：
  1. 取真实局面里每一个候选着法，算出 v2037 的根节点总分（目标 y）。
  2. 同一局面内减均值（局面间绝对值不可比）。
  3. 把当前模型的项分成 6 组，求 6 个缩放系数 s_g，最小化
        Σ ( Σ_g s_g · G_g(move) − y(move) )² + λ·Σ(s_g−1)²
  4. 输出 s_g 以及还原后的偏差/排名相关/首选一致率。

    python 分析/fit_groups.py [--games 6] [--lam 0.05] [--apply]
"""
from __future__ import annotations

import argparse
import json
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
from compare2037 import GAMES, load_old, old_roots, spearman  # noqa: E402

GROUPS = {
    "蜂后气口": ["opp_block", "my_block", "my_tight", "my_ring_own", "liberty_adv",
                 "squeeze_opp", "squeeze_me", "tempo_attack", "tempo_danger",
                 "ring_fill", "ring_hurry", "ring_escape", "ring_lost"],
    "甲虫": ["beetle_on_opp", "beetle_on_me", "beetle_near_opp", "beetle_near_me",
             "beetle_high", "counter_ready"],
    "结构": ["bridge_me", "bridge_opp", "new_bridge", "immobile_me",
             "immobile_opp", "gate_opp", "gate_me"],
    "控制": ["control", "control_lost", "opp_moves", "opp_mobility"],
    "进攻距离": ["threat_opp", "threat_me", "atk_fill", "atk_hurry", "atk_lost",
                 "queen_mobile_me", "queen_mobile_opp", "queen_far", "queen_grab"],
    "手牌子力": ["hand_count", "hand_value", "board_value", "ant_initiative",
                 "early_ant_hard", "rep"],
}


def group_of(term):
    for g, ks in GROUPS.items():
        if term in ks:
            return g
    return None


def evaluate_scales(det, scales, names):
    devs, rhos, agree = [], [], 0
    for rows in det:
        ys = [r[0] for r in rows]
        gs = [sum(scales[i] * r[1][i] for i in range(len(names))) for r in rows]
        my, mg = sum(ys) / len(ys), sum(gs) / len(gs)
        ca = [y - my for y in ys]
        cb = [g - mg for g in gs]
        scale = (max(ca) - min(ca)) or 1.0
        devs.append(sum(abs(x - y) for x, y in zip(ca, cb)) / len(ca) / scale)
        rhos.append(spearman(ys, gs))
        agree += (max(range(len(ys)), key=lambda i: ys[i])
                  == max(range(len(gs)), key=lambda i: gs[i]))
    return (sum(devs) / len(devs), sum(rhos) / len(rhos),
            100.0 * agree / len(det))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--from", dest="frm", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    old = load_old()
    me = ana.AI_SIDE
    names = list(GROUPS)
    det = []
    for name in GAMES[:args.games]:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        for no, rec, before, mv in steps:
            if rec.get("p") != me or before.result or no < args.frm:
                continue
            o = old_roots(old, before, me)
            ka = {m.key(): v for v, m in o}
            rows = []
            cache = {}
            for m in before.legal_moves():
                if m.key() not in ka:
                    continue
                _v, _h, t = cur.root_terms(before, me, m, 2, cache)
                gs = {g: 0.0 for g in names}
                for k, val in t.items():
                    g = group_of(k)
                    if g:
                        gs[g] += val
                rows.append((ka[m.key()], [gs[g] for g in names], m))
            if len(rows) >= 4:
                det.append(rows)
    print("来自 %d 个局面，%d 组" % (len(det), len(names)))

    # 坐标下降：直接最小化「与 v2037 的归一化偏差」
    scales = [1.0] * len(names)
    best = evaluate_scales(det, scales, names)
    print("起点：偏差 %.3f  排名相关 %.3f  首选一致 %.0f%%" % best)
    grid = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5]
    for it in range(4):
        improved = False
        for i in range(len(names)):
            cur_best, cur_s = best, scales[i]
            for s in grid:
                trial = list(scales)
                trial[i] = s
                m = evaluate_scales(det, trial, names)
                if m[0] < cur_best[0] - 1e-6:
                    cur_best, cur_s = m, s
            if cur_s != scales[i]:
                scales[i] = cur_s
                best = cur_best
                improved = True
        if not improved:
            break
    print("\n拟合出的组缩放系数（1.0 = 保持现在的权重）：")
    for g, v in zip(names, scales):
        print("   %-8s × %.2f" % (g, v))
    print("还原后：偏差 %.3f  排名相关 %.3f  首选一致 %.0f%%" % best)

    if args.apply:
        for g, k in zip(names, scales):
            for term in GROUPS[g]:
                if term in cur.W:
                    cur.W[term] = round(cur.W[term] * k, 2)
        out = os.path.join(ANA, "fit2037.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({g: k for g, k in zip(names, scales)}, f,
                      ensure_ascii=False, indent=1)
        print("\n系数已存 ->", out)
        print("放大后的权重（可直接抄进 hive/ai.py）：")
        for g in names:
            print("  # %s ×%.2f" % (g, dict(zip(names, scales))[g]))
            for term in GROUPS[g]:
                if term in cur.W:
                    print("  %-16s %s" % (term, round(cur.W[term], 2)))


if __name__ == "__main__":
    main()
