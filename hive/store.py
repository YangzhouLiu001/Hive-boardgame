# -*- coding: utf-8 -*-
"""存档、棋谱、自动保存。"""

from __future__ import annotations

import json
import os
import sys
import time

from .rules import Game, move_text, neighbors, KIND_NAMES

APP_DIR_NAME = "虫虫蜂房"


def app_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_DIR_NAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = os.path.expanduser("~")
    return d


def record_dir() -> str:
    """棋谱默认放这里（用户看得见的地方）。"""
    if getattr(sys, "frozen", False):
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(root, "棋谱")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        d = os.path.join(app_dir(), "棋谱")
        os.makedirs(d, exist_ok=True)
        return d


def autosave_path() -> str:
    return os.path.join(app_dir(), "autosave.hive")


def settings_path() -> str:
    return os.path.join(app_dir(), "settings.json")


# ------------------------------------------------------------------ 存档
def _as_rec(m, fallback_index=0):
    """把 Move 或着法字典统一成可序列化的记录。"""
    if isinstance(m, dict):
        return dict(m)
    return {"n": fallback_index, "p": None, "k": None,
            "uid": m.uid,
            "frm": list(m.frm) if m.frm is not None else None,
            "to": list(m.to),
            "aux": m.aux}


def save_game(path: str, game: Game, moves: list, theme_key: str = "mahjong",
              versus: str = "human") -> None:
    data = game.to_save()
    if game.moves:
        # gym.moves 里的记录最完整（含走子方与棋子种类）
        data["moves"] = [dict(m) for m in game.moves]
    else:
        data["moves"] = [_as_rec(m, i + 1) for i, m in enumerate(moves or [])]
    data["theme"] = theme_key
    data["versus"] = versus
    data["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_game(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # 用 from_save 重建，先手 / 扩展这些选项才不会丢
    g = Game.from_save(data)
    moves = [move_from_record(rec) for rec in (data.get("moves") or [])]
    return g, moves, data


def move_from_record(rec: dict):
    from .rules import Move
    uid = rec["uid"]
    if rec.get("frm") is None:
        return Move("place", uid, tuple(rec["to"]))
    if rec.get("aux") is not None:
        return Move("toss", uid, tuple(rec["to"]),
                    frm=tuple(rec["frm"]), aux=rec["aux"])
    return Move("move", uid, tuple(rec["to"]), frm=tuple(rec["frm"]))


# ------------------------------------------------------------------ 棋谱文本
def _ascii_board(g: Game) -> str:
    """把棋盘画成字符图。"""
    if not g.stacks:
        return "（空盘）\n"
    codes = {"queen": "Q", "beetle": "B", "spider": "S", "grasshopper": "G",
             "ant": "A", "ladybug": "L", "mosquito": "M", "pillbug": "P"}
    cells = sorted(g.stacks.keys(), key=lambda p: (p[1] + p[0] / 2.0, p[0]))
    rmin = min(p[1] for p in cells)
    rmax = max(p[1] for p in cells)
    qmin = min(p[0] for p in cells)
    qmax = max(p[0] for p in cells)
    grid = {}
    for p in cells:
        col = int((p[0] - qmin) * 2 + (p[1] - rmin))
        row = int((p[1] - rmin) * 2 + (p[0] - qmin) % 2)
        grid[(row, col)] = p
    width = (qmax - qmin) * 2 + (rmax - rmin) + 2
    lines = []
    for r in range(-1, (rmax - rmin) * 2 + (qmax - qmin) + 3):
        row = [" "] * width
        for c in range(0, width):
            p = grid.get((r, c))
            if p is None:
                continue
            top = g.top(p)
            code = codes.get(g.pieces[top][1], "?")
            txt = code if g.pieces[top][0] == 0 else code.lower()
            row[c] = txt
        s = "".join(row).rstrip()
        if s:
            lines.append(s)
    return "\n".join(lines) + "\n"


def export_text(path: str, game: Game, moves: list) -> None:
    out = []
    out.append("虫虫蜂房 · Hive  对局棋谱")
    out.append("=" * 40)
    out.append("白方：%s    黑方：%s" % (game.names[0], game.names[1]))
    if game.expansions:
        out.append("扩展：%s" % "、".join(KIND_NAMES[k] for k in game.expansions))
    out.append("规则：官方规则（两侧同时被占才滑不过去）")
    out.append("")
    out.append("着法记录")
    out.append("-" * 40)
    n = 1
    for i, mv in enumerate(moves):
        rec = game.moves[i] if i < len(game.moves) else None
        if rec is None:
            continue
        who = game.names[rec["p"]]
        out.append("%3d. %s  %s" % (n, who, move_text(game, rec)))
        n += 1
    out.append("")
    if game.result == "win":
        out.append("结果：%s 获胜（%s）" % (game.names[game.winner], game.reason))
    elif game.result == "draw":
        out.append("结果：和棋（%s）" % game.reason)
    else:
        out.append("结果：未终局")
    out.append("")
    out.append("终局盘面（大写=白方，小写=黑方）")
    out.append("-" * 40)
    out.append(_ascii_board(game))
    out.append("图例：Q蜂后 B甲虫 S蜘蛛 G蚱蜢 A兵蚁 L瓢虫 M蚊子 P鼠妇")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


# ------------------------------------------------------------------ 设置
def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d: dict) -> None:
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass

