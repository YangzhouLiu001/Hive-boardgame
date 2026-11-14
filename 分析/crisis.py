# -*- coding: utf-8 -*-
"""危机失手统计：AI 选的一手是否把「还能活」的局面走成「三步内必死」。

    python 分析/crisis.py [--level 3] [--games 3] [--tag base]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
ANA = os.path.join(ROOT, "分析")
if ANA not in sys.path:
    sys.path.insert(0, ANA)

import ana  # noqa: E402
import solver  # noqa: E402
from hive import ai as AI_NEW  # noqa: E402

GAMES = [
    "白方 vs 黑方 20261113-2252.hive",
    "白方 vs 黑方 20261113-2217.hive",
    "白方 vs 黑方 20261113-2148.hive",
]


def load_base():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hive.ai_base", os.path.join(ANA, "ai_base.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hive.ai_base"] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--games", type=int, default=3)
    ap.add_argument("--tag", default="base")
    ap.add_argument("--from", dest="frm", type=int, default=6)
    ap.add_argument("--engine", default="new", choices=["new", "base"])
    ap.add_argument("--set", action="append", default=[],
                    help="覆盖权重，例如 --set threat_me=0")
    ap.add_argument("--games-list", default="",
                    help="逗号分隔的棋谱文件名（默认用内置 3 局）")
    args = ap.parse_args()
    if args.games_list:
        GAMES[:] = [g.strip() for g in args.games_list.split(",") if g.strip()]
    A = AI_NEW if args.engine == "new" else load_base()
    for s in args.set:
        k, v = s.split("=")
        A.W[k] = float(v)
        print("  覆盖 W[%s] = %s" % (k, v))
    me = ana.AI_SIDE
    blunders = []
    total = 0
    t0 = time.time()
    for name in GAMES[:args.games]:
        steps, _f = ana.replay(os.path.join(ROOT, "棋谱", name))
        for n, rec, before, mv in steps:
            if rec.get("p") != me or before.result or n < args.frm:
                continue
            total += 1
            chosen = A.choose_move(A.clone(before), args.level, None, use_book=False)
            if chosen is None:
                continue
            h = A._apply(before, chosen)
            if h.result:
                continue
            lost, p = solver.lost_in(h, me, 3)
            if not lost:
                continue
            # 有没有能活的着法
            alive = []
            for cand in before.legal_moves():
                hc = A._apply(before, cand)
                if hc.result:
                    if hc.winner == me:
                        alive.append(ana.fmt_mv(before, cand))
                    continue
                lo, _pp = solver.lost_in(hc, me, 7)
                if not lo:
                    alive.append(ana.fmt_mv(before, cand))
            blunders.append({"game": name, "n": n,
                             "chosen": ana.fmt_mv(before, chosen),
                             "alive": alive[:6], "n_alive": len(alive)})
            print("%-28s 第%3d手 选了 %-24s 三步内必死；能活 %d 条：%s" % (
                name[-14:], n, ana.fmt_mv(before, chosen), len(alive),
                alive[:4]))
    print("=" * 60)
    print("[%s] 共查 %d 个局面，危机失手 %d 个，用时 %.0fs" % (
        args.tag, total, len(blunders), time.time() - t0))
    out = os.path.join(ANA, "crisis_%s.json" % args.tag)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"total": total, "blunders": blunders}, f, ensure_ascii=False,
                  indent=1)
    print("明细 ->", out)


if __name__ == "__main__":
    main()
