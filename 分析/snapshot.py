# -*- coding: utf-8 -*-
"""把近期棋谱里每个「AI 该走」的局面导成快照（静态排名 + 可选搜索结论）。

    python 分析/snapshot.py out.json [--search 2]
"""
from __future__ import annotations

import json
import os
import sys
import time

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


def static_rank(g, me, level=2):
    out = []
    for mv in g.legal_moves():
        v, h, t = A.root_terms(g, me, mv, level)
        out.append((v, mv))
    out.sort(key=lambda x: -x[0])
    return out


def desc(g, mv):
    rec = {"k": g.pieces[mv.uid][1], "to": list(mv.to),
           "frm": list(mv.frm) if mv.frm is not None else None,
           "aux": mv.aux}
    return move_text(g, rec)


def main(argv):
    out_path = argv[1] if len(argv) > 1 else "分析/snap.json"
    search_level = 0
    if "--search" in argv:
        search_level = int(argv[argv.index("--search") + 1])
    snaps = []
    for name in GAMES:
        path = os.path.join(ROOT, "棋谱", name)
        steps, final = ana.replay(path)
        for n, rec, before, mv in steps:
            if rec.get("p") != ana.AI_SIDE:
                continue
            if before.result:
                continue
            t0 = time.time()
            rank = static_rank(before, ana.AI_SIDE)
            ent = {
                "game": name, "n": n,
                "actual": desc(before, mv),
                "actual_static": None,
                "top": [[round(v, 1), desc(before, m)] for v, m in rank[:16]],
                "t": round(time.time() - t0, 2),
            }
            ak = None
            for i, (v, m) in enumerate(rank):
                if m.key() == mv.key():
                    ak = (i + 1, round(v, 1))
                    break
            ent["actual_static"] = ak
            if search_level:
                t1 = time.time()
                best = A.choose_move(before, search_level, None, use_book=False)
                ent["chosen"] = desc(before, best) if best else None
                ent["chosen_ok"] = bool(best and best.key() == mv.key())
                ent["search_t"] = round(time.time() - t1, 1)
                print("%-32s n=%-3d 静态第 %-3s 搜索选 %-24s (%s) %.1fs" % (
                    name[-14:], n, ak and ak[0], ent["chosen"],
                    "实际" if ent["chosen_ok"] else "不同", ent["search_t"]))
            snaps.append(ent)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snaps, f, ensure_ascii=False, indent=1)
    print("共 %d 个局面 -> %s" % (len(snaps), out_path))


if __name__ == "__main__":
    main(sys.argv)
