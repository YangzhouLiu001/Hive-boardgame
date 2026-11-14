# -*- coding: utf-8 -*-
"""棋谱败招分析工具（不改动 hive/ 源码）。

用法：
    python 分析/ana.py curve "棋谱/xxx.hive"
    python 分析/ana.py blunder "棋谱/xxx.hive" [--last 8]
    python 分析/ana.py some ...
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hive.rules import Game, Move, hex_dist, neighbors, other, move_text  # noqa: E402
from hive import ai as A  # noqa: E402

AI_SIDE = 1          # ui.py: self.ai_side = 1


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def _rec_move(rec):
    uid = rec["uid"]
    if rec.get("frm") is None:
        return Move("place", uid, tuple(rec["to"]))
    if rec.get("aux") is not None:
        return Move("toss", uid, tuple(rec["to"]),
                    frm=tuple(rec["frm"]), aux=rec["aux"])
    return Move("move", uid, tuple(rec["to"]), frm=tuple(rec["frm"]))


def replay(path):
    """从空盘重放，返回 [(步号, rec, 走之前的副本, Move)] 和终局盘面。"""
    data = load(path)
    o = data.get("options") or {}
    recs = data.get("moves") or []
    first = o.get("first")
    if first is None:
        first = recs[0]["p"] if recs else 0
    g = Game(o.get("expansions") or [], int(first) % 2,
             names=o.get("names"), relaxed=bool(o.get("relaxed", False)))
    out = []
    for rec in recs:
        if g.result:
            break
        before = A.clone(g)
        mv = _rec_move(rec)
        out.append((rec.get("n"), rec, before, mv))
        g.apply(mv)
    return out, g


def lib(g, owner):
    """蜂后气数（空邻格数）。蜂后没落子返回 None。"""
    q = g.queen_pos[owner]
    if q is None:
        return None
    return 6 - sum(1 for n in neighbors(q) if n in g.stacks)


def opp_mate_moves(g, me):
    """轮到 opp 走，能一手围死我的着法数。"""
    opp = other(me)
    n = 0
    best = []
    for mv in g.legal_moves():
        h = A._apply(g, mv)
        if h.result == "win" and h.winner == opp:
            n += 1
            best.append(mv)
    return n, best


def best_threat(g, me):
    """轮到我方的对手，一手棋之后我的蜂后最少剩几口气。返回 (minlib, 着法)。"""
    opp = other(me)
    lo, arg = 99, None
    for mv in g.legal_moves():
        h = A._apply(g, mv)
        if h.result == "win" and h.winner == opp:
            return 0, mv
        v = lib(h, me)
        if v is None:
            return 99, None
        if v < lo:
            lo, arg = v, mv
    return lo, arg


def danger(g, mv, me):
    """走完 mv 之后，对手一手能把我压到几口气。"""
    h = A._apply(g, mv)
    if h.result == "win":
        return ("win" if h.winner == me else "lose"), 0
    return best_threat(h, me)[0], 0


def fmt_mv(g, mv):
    rec = {"k": g.pieces[mv.uid][1], "to": list(mv.to),
           "frm": list(mv.frm) if mv.frm is not None else None,
           "aux": mv.aux}
    return move_text(g, rec)


def curve(path):
    steps, final = replay(path)
    print("=" * 78)
    print(os.path.basename(path), " 共 %d 手，结果 %s / %s" %
          (len(steps), final.result, final.reason))
    print("%4s %-4s %-22s %5s %5s" % ("步", "方", "着法", "黑气", "白气"))
    for n, rec, before, mv in steps:
        g2 = A._apply(before, mv)
        print("%4d %-4s %-22s %5s %5s" % (
            n, "AI" if rec.get("p") == AI_SIDE else "人",
            fmt_mv(before, mv),
            lib(g2, 1) if lib(g2, 1) is not None else "-",
            lib(g2, 0) if lib(g2, 0) is not None else "-"))


def blunder(path, last=10):
    steps, final = replay(path)
    ai_steps = [(n, rec, b, mv) for n, rec, b, mv in steps
                if rec.get("p") == AI_SIDE]
    print("=" * 78)
    print(os.path.basename(path), "%d 手，AI 走 %d 步" % (len(steps), len(ai_steps)))
    print("%4s %-24s %6s %6s %6s %6s" %
          ("步", "实际着法", "走前气", "走后气", "对手压到", "安全解"))
    for n, rec, before, mv in ai_steps[-last:]:
        q0 = lib(before, AI_SIDE) or 0
        a = A._apply(before, mv)
        if a.result == "win" and a.winner == AI_SIDE:
            print("%4d %-24s %6d %6s %6s %6s" %
                  (n, fmt_mv(before, mv), q0, "绝杀", "-", "-"))
            continue
        q1 = lib(a, AI_SIDE)
        worst, wmv = best_threat(a, AI_SIDE)
        # 全局：每条着法之下，对手能压到的最少气数；找最好的那条
        best_safe, best_mv = -1, None
        for c in before.legal_moves():
            h = A._apply(before, c)
            if h.result == "win" and h.winner == AI_SIDE:
                best_safe, best_mv = 99, c
                break
            if h.result:
                continue
            t, _ = best_threat(h, AI_SIDE)
            if t > best_safe:
                best_safe, best_mv = t, c
        mark = "" if worst >= best_safe else "  <-- 败招"
        print("%4d %-24s %6d %6d %6d %6d%s" %
              (n, fmt_mv(before, mv), q0, q1, worst, best_safe, mark))
        if mark and best_mv is not None:
            print("%33s 更好：%s" % ("", fmt_mv(before, best_mv)))


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return
    cmd, path = argv[1], argv[2]
    last = 10
    if "--last" in argv:
        last = int(argv[argv.index("--last") + 1])
    if cmd == "curve":
        curve(path)
    elif cmd == "blunder":
        blunder(path, last)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
