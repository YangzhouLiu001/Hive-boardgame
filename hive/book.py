# -*- coding: utf-8 -*-
"""从棋谱里学开局。

把 棋谱\\ 里所有存档回放一遍，记录前若干个回合里「这个局面下走哪一手、
最后赢没赢」，做成一个小开局库。开局库只在开局阶段、而且样本足够多时
才用；否则老老实实搜索。

不是神经网络，就是最朴素的「看别人怎么下的」统计。
"""

from __future__ import annotations

import glob
import json
import os

from . import store
from .rules import Game

MAX_PLY = 12          # 只学前 12 手
MIN_SAMPLES = 3       # 同一局面至少出现过几次才敢用
MIN_WINRATE = 0.45    # 胜率太低的着法不用


def position_key(g: Game) -> str:
    """稳定的局面指纹（跨进程不变，可以存 JSON）。"""
    items = []
    for p, st in g.stacks.items():
        items.append((p, tuple(g.pieces[u] for u in st)))
    items.sort()
    return repr((tuple(items), g.turn,
                 tuple(sorted(g.hand[0])), tuple(sorted(g.hand[1]))))


def _move_key(mv) -> str:
    frm = "-" if mv.frm is None else "%d,%d" % mv.frm
    return "%s|%s|%d,%d|%s" % (mv.kind, frm, mv.to[0], mv.to[1],
                               "-" if mv.aux is None else mv.aux)


def book_path() -> str:
    return os.path.join(store.app_dir(), "book.json")


def record_files() -> list:
    d = store.record_dir()
    return sorted(glob.glob(os.path.join(d, "*.hive")))


def build_book(files=None) -> dict:
    """回放所有棋谱，统计每个局面下各着法的 (胜, 总数)。"""
    files = files if files is not None else record_files()
    book: dict = {}
    games = 0
    for p in files:
        try:
            g0, moves, _data = store.load_game(p)
        except Exception:
            continue
        if not moves:
            continue
        games += 1
        winner = g0.winner
        g = Game(g0.expansions, g0.first_player, names=list(g0.names))
        for i, mv in enumerate(moves):
            if i >= MAX_PLY:
                break
            try:
                key = position_key(g)
                owner = g.turn
                slot = book.setdefault(key, {})
                mk = _move_key(mv)
                rec = slot.setdefault(mk, [0, 0])
                rec[1] += 1
                if winner is not None and winner == owner:
                    rec[0] += 1
            except Exception:
                break
            try:
                g.apply(mv)
            except Exception:
                break
    return {"games": games, "positions": book}


def save_book(book: dict) -> None:
    try:
        with open(book_path(), "w", encoding="utf-8") as f:
            json.dump(book, f, ensure_ascii=False)
    except Exception:
        pass


_CACHE = None


def get_book() -> dict:
    """进程内缓存一份，免得每步都读盘。"""
    global _CACHE
    if _CACHE is None:
        _CACHE = load_book()
    return _CACHE


def invalidate() -> None:
    global _CACHE
    _CACHE = None


def is_stale() -> bool:
    """棋谱比开局库新（或库还不存在）就该重建。"""
    p = book_path()
    if not os.path.exists(p):
        return True
    try:
        bt = os.path.getmtime(p)
    except OSError:
        return True
    for f in record_files():
        try:
            if os.path.getmtime(f) > bt:
                return True
        except OSError:
            continue
    return False


def ensure_book(verbose: bool = False) -> dict:
    """启动时调用：需要就把开局库重建一遍。"""
    if is_stale():
        b = rebuild()
        invalidate()
        if verbose:
            print("开局库已更新")
        return b
    return get_book()


def load_book() -> dict:
    try:
        with open(book_path(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and "positions" in d:
            return d
    except Exception:
        pass
    return {"games": 0, "positions": {}}


def rebuild(save=True) -> dict:
    book = build_book()
    if save:
        save_book(book)
    invalidate()
    return book


def _parse_move_key(mk: str):
    try:
        kind, frm, to, _aux = mk.split("|")
        f = None if frm == "-" else tuple(int(x) for x in frm.split(","))
        t = tuple(int(x) for x in to.split(","))
        return kind, f, t
    except Exception:
        return None


def lookup(book: dict, g: Game):
    """在当前局面里，从开局库挑一手；没有把握就返回 None。"""
    if not book or len(g.moves) >= MAX_PLY:
        return None
    slot = (book.get("positions") or {}).get(position_key(g))
    if not slot:
        return None
    best, best_score = None, -1.0
    for mk, (wins, plays) in slot.items():
        if plays < MIN_SAMPLES:
            continue
        score = wins / float(plays)
        if score < MIN_WINRATE:
            continue
        # 胜率优先，同胜率看样本数
        rank = score + 0.001 * plays
        if rank > best_score:
            best_score, best = rank, mk
    if best is None:
        return None
    parsed = _parse_move_key(best)
    if parsed is None:
        return None
    kind, frm, to = parsed
    for mv in g.legal_moves():
        if mv.kind == kind and mv.to == to and mv.frm == frm:
            return mv
    return None
