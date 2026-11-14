# -*- coding: utf-8 -*-
"""共线分析与项合并（按老师的要求：删掉不必要的项，把共线项拆到核心项上，系数相加）。

步骤：
  1. 采样：真实局面 × 每条合法着法，取每个分项的**原始值**（未乘权重）。
  2. 算共线：同局面内中心化后，两两相关系数。|r|>0.85 视为同一根轴。
  3. 合并：对每个"被删项"，把它对核心项做最小二乘分解 f_i ≈ Σ β_ij·g_j，
     于是 Σ_i W_i·f_i ≈ Σ_j (Σ_i W_i·β_ij)·g_j —— 权重就此并入核心项。
  4. 输出：核心项的新权重 + 与 v2037 叠加结果的一致度。

    python 分析/merge_terms.py            # 只看共线
    python 分析/merge_terms.py --merge    # 执行合并并打印新权重表
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ANA = os.path.join(ROOT, "分析")
if ANA not in sys.path:
    sys.path.insert(0, ANA)

import ana  # noqa: E402
from hive import ai as cur  # noqa: E402
from compare2037 import GAMES, load_old, old_roots, spearman  # noqa: E402

# ---- 核心项（老师点名的几根轴）：气口、甲虫、结构、控制、进攻、手牌
KEEP = [
    # 气口（精确、去类型化）
    "ring_fill", "ring_hurry", "ring_lost", "ring_escape",
    "atk_fill", "atk_hurry", "atk_lost",
    # 原始气数占用（最直观的两项）
    "my_block", "my_ring_own", "opp_block",
    # 甲虫（老师要求分类型）
    "beetle_on_opp", "beetle_on_me", "beetle_high",
    # 结构
    "bridge_me", "bridge_opp", "new_bridge",
    "immobile_me", "immobile_opp",
    # 控制 / 机动
    "control", "control_lost", "opp_moves", "opp_mobility",
    # 手牌 / 子力
    "hand_count", "board_value", "ant_initiative",
    # 其它
    "queen_mobile_me", "queen_mobile_opp", "queen_far", "rep",
]

DROP = [
    "my_tight", "squeeze_me", "squeeze_opp", "tempo_danger", "tempo_attack",
    "liberty_adv", "threat_me", "threat_opp", "queen_grab",
    "beetle_near_opp", "beetle_near_me", "counter_ready",
    "gate_opp", "gate_me", "support_me", "beetle_guard", "hole_gift",
    "ant_late", "hand_value", "early_ant_hard", "early_ant",
]


def raw_terms(g, me, mv, cache):
    """一条着法的全部分项原始值（未乘权重）。"""
    h = cur._apply(g, mv)
    t = {}
    if h.result:
        return t, h
    for k, val in cur.features(h, me).items():
        if val:
            t[k] = val
    opp = cur.other(me)
    omoves = h.legal_moves()
    after_imm = cur._immobile_pieces(h, opp, omoves)
    if cache.get("before_imm") is None:
        cache["before_imm"] = cur._immobile_pieces(g, opp)
    before_imm = cache["before_imm"]
    holes = set(cur._ring_cells(h, me))
    fillers = {m.uid for m in omoves if m.to in holes} if holes else set()
    cg = 0.0
    for u in after_imm - before_imm:
        v = cur.PIECE_VALUE.get(h.pieces[u][1], 2.0)
        if u in fillers:
            v *= cur.W["control_threat"]
        cg += v
    t["control"] = cg
    cl = 0.0
    for u in before_imm - after_imm:
        if mv.frm is not None and cur.hex_dist(h.where[u], mv.frm) > 2:
            continue
        cl += max(1.0, cur.PIECE_VALUE.get(h.pieces[u][1], 2.0))
    t["control_lost"] = cl
    t["opp_moves"] = float(len(omoves))
    opp_top = {u for u in h.on_board(opp)
               if (h.stacks.get(h.where[u]) or [None])[-1] == u}
    opp_movable = {m2.uid for m2 in omoves}
    mob = 0.0
    for u in opp_top:
        if u in opp_movable:
            mob += cur.PIECE_VALUE.get(h.pieces[u][1], 2.0)
    t["opp_mobility"] = mob
    t["new_bridge"] = max(0.0, cur._bridges(h, me) - cur._bridges(g, me))
    if mv.frm is None and g.pieces[mv.uid][1] == "ant" and g.turn_no[me] <= 0:
        t["early_ant_hard"] = 1.0
    if cur._ring_libs_after(g, me, mv) <= 4:
        for k, val in cur.ring_terms(h, me, omoves).items():
            t[k] = abs(val) / max(1e-9, abs(cur.W[k]))
    if len(cur._ring_cells(h, opp)) <= 4:
        mm = h.legal_moves(me)
        for k, val in cur.atk_ring_terms(h, opp, mm).items():
            t[k] = abs(val) / max(1e-9, abs(cur.W[k]))
    return t, h


def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    a = [x - mx for x in xs]
    b = [y - my for y in ys]
    num = sum(i * j for i, j in zip(a, b))
    den = (sum(i * i for i in a) * sum(j * j for j in b)) ** 0.5
    return num / den if den else 0.0


def build():
    old = load_old()
    me = ana.AI_SIDE
    samples = []          # [(target_total, {term: raw}, move_text)]
    for name in GAMES:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        for no, rec, before, mv in steps:
            if rec.get("p") != me or before.result or no < 8:
                continue
            o = old_roots(old, before, me)
            tgt = {m.key(): v for v, m in o}
            rows, cache = [], {}
            for m in before.legal_moves():
                if m.key() not in tgt:
                    continue
                t, _h = raw_terms(before, me, m, cache)
                if t:
                    rows.append((tgt[m.key()], t, ana.fmt_mv(before, m)))
            if len(rows) >= 4:
                samples.append(rows)
    return samples


def center(samples, names):
    """返回 [(ys, {name: centered value})]，同局面内减均值。"""
    out = []
    for rows in samples:
        my = sum(r[0] for r in rows) / len(rows)
        means = {n: sum(r[1].get(n, 0.0) for r in rows) / len(rows) for n in names}
        out.append(([r[0] - my for r in rows],
                    [{n: r[1].get(n, 0.0) - means[n] for n in names} for r in rows],
                    [r[2] for r in rows]))
    return out


def ridge_fit(X, y, lam):
    """解 (XᵀX+λI) β = Xᵀy。X: 样本×列。"""
    m = len(X[0])
    A = [[sum(r[i] * r[j] for r in X) + (lam if i == j else 0.0) for j in range(m)]
         for i in range(m)]
    b = [sum(r[i] * yy for r, yy in zip(X, y)) for i in range(m)]
    for i in range(m):
        p = max(range(i, m), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]
        b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            continue
        for r in range(i + 1, m):
            f = A[r][i] / A[i][i]
            if not f:
                continue
            for c in range(i, m):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    beta = [0.0] * m
    for i in reversed(range(m)):
        if abs(A[i][i]) < 1e-12:
            continue
        beta[i] = (b[i] - sum(A[i][c] * beta[c] for c in range(i + 1, m))) / A[i][i]
    return beta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--thresh", type=float, default=0.85)
    args = ap.parse_args()
    samples = build()
    names = sorted({n for rows in samples for _v, t, _d in rows for n in t})
    print("局面 %d，分项 %d" % (len(samples), len(names)))
    data = center(samples, names)

    # ---- 共线分析
    cols = defaultdict(list)
    for _ys, rows, _d in data:
        for r in rows:
            for n in names:
                cols[n].append(r[n])
    pairs = []
    for i, a in enumerate(names):
        if not any(cols[a]):
            continue
        for b in names[i + 1:]:
            if not any(cols[b]):
                continue
            r = corr(cols[a], cols[b])
            if abs(r) >= args.thresh:
                pairs.append((abs(r), r, a, b))
    pairs.sort(reverse=True)
    print("\n共线对（|r| ≥ %.2f），共 %d 对：" % (args.thresh, len(pairs)))
    for _a, r, a, b in pairs[:28]:
        print("   %+0.2f  %-16s %-16s" % (r, a, b))
    if not args.merge:
        return

    # ---- 按"同一根轴"聚类合并：把被并项按过原点最小二乘拆到代表项上，系数相加
    CLUSTERS = [
        ("board_value", ["hand_count", "hand_value"]),
        ("opp_moves", ["opp_mobility", "immobile_opp"]),
        ("bridge_me", ["new_bridge"]),
        ("beetle_on_opp", ["beetle_near_opp"]),
    ]
    W2 = dict(cur.W)
    ALIAS = {"opp_mobility": "mobility"}
    slopes = []

    def wt(name):
        return cur.W.get(ALIAS.get(name, name), 0.0)

    print("\n合并明细（被并项 → 代表项，系数 = 过原点回归斜率）：")
    for keep, drops in CLUSTERS:
        for d in drops:
            if not any(cols[d]):
                continue
            xs = cols[keep]
            ys = cols[d]
            sxx = sum(x * x for x in xs)
            if sxx < 1e-9:
                continue
            c = sum(x * y for x, y in zip(xs, ys)) / sxx
            resid = sum((y - c * x) ** 2 for x, y in zip(xs, ys))
            tot = sum(y * y for y in ys)
            r2 = 1.0 - resid / tot if tot > 0 else 1.0
            contrib = wt(d) * c
            print("   %-16s → %-16s 斜率 %+0.3f  R²=%.2f   带入 %+0.2f×%+0.3f = %+0.2f"
                  % (d, keep, c, r2, wt(d), c, contrib))
            ka, kd = ALIAS.get(keep, keep), ALIAS.get(d, d)
            W2[ka] = W2.get(ka, 0.0) + contrib
            W2[kd] = 0.0
            # 斜率存下来，供笔记核对
            slopes.append((d, keep, c, r2, contrib))
    print("\n合并后权重（只列有变化的）：")
    for k in sorted(W2):
        if k.startswith("_"):
            continue
        if abs(W2[k] - cur.W.get(k, 0.0)) > 0.005:
            print("   %-16s %8.2f -> %8.2f" % (k, cur.W.get(k, 0.0), round(W2[k], 2)))

    # ---- 校验：合并前后对 v2037 的一致度
    def score_with(r, wmap):
        return sum(wmap.get(n, 0.0) * v for n, v in r.items())

    for tag, wmap in (("合并前", cur.W), ("合并后", W2)):
        devs, rhos, agree = [], [], 0
        for ys_row, rows, _d in data:
            y = ys_row
            s = [score_with(r, wmap) for r in rows]
            my, ms = sum(y) / len(y), sum(s) / len(s)
            ca = [x - my for x in y]
            cb = [x - ms for x in s]
            scale = (max(ca) - min(ca)) or 1.0
            devs.append(sum(abs(p - q) for p, q in zip(ca, cb)) / len(ca) / scale)
            rhos.append(spearman(y, s))
            agree += (max(range(len(y)), key=lambda i: y[i])
                      == max(range(len(s)), key=lambda i: s[i]))
        print("\n[%s] vs v2037：偏差 %.3f  排名相关 %.3f  首选一致 %.0f%%" % (
            tag, sum(devs) / len(devs), sum(rhos) / len(rhos),
            100.0 * agree / len(data)))
    import json
    out = os.path.join(ANA, "merged_W.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(W2, f, ensure_ascii=False, indent=1)
    print("合并后权重表 ->", out)


if __name__ == "__main__":
    main()
