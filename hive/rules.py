# -*- coding: utf-8 -*-
"""虫虫蜂房 (Hive) 规则内核 —— 纯逻辑，不依赖界面。

坐标系：平顶六边形 (flat-top) 的 axial 坐标 (q, r)。
    像素  x = 1.5 * s * q
          y = sqrt(3) * s * (r + q/2)
六个邻居方向按顺时针排列：北、东北、东南、南、西南、西北。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

Pos = Tuple[int, int]

# 顺时针：N, NE, SE, S, SW, NW
DIRS: List[Pos] = [(0, -1), (1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0)]
DIR_NAMES = ["北", "东北", "东南", "南", "西南", "西北"]

# 棋子种类（顺序即新手牌顺序）
BASE_KINDS = ["queen", "beetle", "spider", "grasshopper", "ant"]
EXP_KINDS = ["ladybug", "mosquito", "pillbug"]
BASE_COUNTS = {"queen": 1, "beetle": 2, "spider": 2, "grasshopper": 3, "ant": 3}

KIND_NAMES = {
    "queen": "蜂后",
    "beetle": "甲虫",
    "spider": "蜘蛛",
    "grasshopper": "蚱蜢",
    "ant": "兵蚁",
    "ladybug": "瓢虫",
    "mosquito": "蚊子",
    "pillbug": "鼠妇",
}

KIND_DESC = {
    "queen": "每次走一格",
    "beetle": "走一格，可爬上/爬下蜂巢顶层",
    "spider": "沿蜂巢滑行整三步",
    "grasshopper": "跳过一串棋子，落在其后第一个空位",
    "ant": "沿蜂巢任意滑行",
    "ladybug": "先爬越两步，再落回地面",
    "mosquito": "复制相邻棋子的走法",
    "pillbug": "走一格；或有特殊搬运能力",
}


def add(a: Pos, b: Pos) -> Pos:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Pos, b: Pos) -> Pos:
    return (a[0] - b[0], a[1] - b[1])


def neighbors(p: Pos) -> List[Pos]:
    return [(p[0] + d[0], p[1] + d[1]) for d in DIRS]


def hex_dist(a: Pos, b: Pos) -> int:
    dq = a[0] - b[0]
    dr = a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def other(player: int) -> int:
    return 1 - player


class Move:
    """一步棋。

    kind == "place" : uid 落到 to
    kind == "move"  : uid 从 frm 走到 to
    kind == "toss"  : 鼠妇 uid(=aux) 把目标棋子 uid 从 frm 搬到 to
    """

    __slots__ = ("kind", "uid", "to", "frm", "aux")

    def __init__(self, kind: str, uid: int, to: Pos, frm: Optional[Pos] = None,
                 aux: Optional[int] = None):
        self.kind = kind
        self.uid = uid
        self.to = to
        self.frm = frm
        self.aux = aux

    def key(self):
        return (self.kind, self.uid, self.to, self.frm, self.aux)

    def __eq__(self, o):
        return isinstance(o, Move) and self.key() == o.key()

    def __hash__(self):
        return hash(self.key())

    def __repr__(self):
        return "Move(%s,u%d,%s<-%s)" % (self.kind, self.uid, self.to, self.frm)


class Game:
    def __init__(self, expansions=(), first_player: int = 0, names=None,
                 relaxed: bool = True):
        # 规则只有一套：官方规则（两侧同时被占才滑不过去）。
        # relaxed 参数只是历史残留，旧存档 / 旧分析脚本还传它，一律忽略。
        # 同名属性同样只为兼容旧读档代码而保留，恒为 True。
        self.relaxed = True
        exp = set(expansions)
        self.expansions = tuple(k for k in EXP_KINDS if k in exp)
        self.kinds = list(BASE_KINDS) + list(self.expansions)
        self.counts = dict(BASE_COUNTS)
        for k in self.expansions:
            self.counts[k] = 1

        self.pieces: Dict[int, Tuple[int, str]] = {}
        self.where: Dict[int, Optional[Pos]] = {}
        self.hand: Dict[int, List[int]] = {0: [], 1: []}
        uid = 0
        for owner in (0, 1):
            for k in self.kinds:
                for _ in range(self.counts[k]):
                    self.pieces[uid] = (owner, k)
                    self.where[uid] = None
                    self.hand[owner].append(uid)
                    uid += 1

        self.stacks: Dict[Pos, List[int]] = {}
        self.first_player = int(first_player) % 2
        self.turn = self.first_player
        self.turn_no = {0: 0, 1: 0}
        self.placed = {0: 0, 1: 0}
        self.queen_pos: Dict[int, Optional[Pos]] = {0: None, 1: None}
        self.moves: List[dict] = []
        self.result: Optional[str] = None      # None / "win" / "draw"
        self.winner: Optional[int] = None
        self.reason = ""
        self.last_toss: Optional[int] = None
        self._hashes: List[int] = []
        self._reps = {}
        self.names = names or ["白方", "黑方"]
        self.passes = 0
        self._record_hash()

    # ---------------------------------------------------------------- 基础查询
    def owner_of(self, uid: int) -> int:
        return self.pieces[uid][0]

    def kind_of(self, uid: int) -> str:
        return self.pieces[uid][1]

    def top(self, p: Pos) -> Optional[int]:
        st = self.stacks.get(p)
        return st[-1] if st else None

    def height(self, p: Pos) -> int:
        return len(self.stacks.get(p, ()))

    def ground_cells(self) -> Set[Pos]:
        return set(self.stacks.keys())

    def owner_top(self, p: Pos) -> Optional[int]:
        t = self.top(p)
        return None if t is None else self.pieces[t][0]

    def queen_surrounded(self, owner: int) -> bool:
        q = self.queen_pos[owner]
        if q is None:
            return False
        return all(n in self.stacks for n in neighbors(q))

    def queen_near_death(self, owner: int) -> int:
        """蜂后周围已被占据的格子数。"""
        q = self.queen_pos[owner]
        if q is None:
            return 0
        return sum(1 for n in neighbors(q) if n in self.stacks)

    def on_board(self, owner: int) -> List[int]:
        return [u for u, (o, _k) in self.pieces.items()
                if o == owner and self.where[u] is not None]

    # ---------------------------------------------------------------- 连通性
    @staticmethod
    def _connected(cells: Set[Pos]) -> bool:
        if not cells:
            return True
        seen = set()
        start = next(iter(cells))
        stack = [start]
        seen.add(start)
        while stack:
            c = stack.pop()
            for n in neighbors(c):
                if n in cells and n not in seen:
                    seen.add(n)
                    stack.append(n)
        return len(seen) == len(cells)

    def _removal_ok(self, uid: int) -> bool:
        """拿起 uid 之后，剩余蜂巢是否仍然连成一体（一巢规则）。"""
        p = self.where[uid]
        if p is None:
            return True
        cells = set(self.stacks.keys())
        if len(self.stacks[p]) == 1:
            cells.discard(p)
        return self._connected(cells)

    # ---------------------------------------------------------------- 滑动
    def _slide_ok(self, a: Pos, b: Pos, occ: Set[Pos]) -> bool:
        """a→b 滑行是否过得去（官方规则 / 自由移动）。

        共用边两侧各还挨着一个格子，那两个格子就是「门的两侧」：
        只有两侧**同时**被占，棋子才挤不过去；只被一侧挡住时可以侧身让过去。
        """
        d = sub(b, a)
        try:
            i = DIRS.index(d)
        except ValueError:
            return False
        blocked = 0
        for j in ((i - 1) % 6, (i + 1) % 6):
            if add(a, DIRS[j]) in occ:
                blocked += 1
        return blocked < 2

    def _perimeter(self, occ: Set[Pos]) -> Set[Pos]:
        """贴着蜂巢外缘的空格。棋子只能沿蜂巢边缘行走，不能滑进空旷地带。"""
        per: Set[Pos] = set()
        for c in occ:
            for n in neighbors(c):
                if n not in occ:
                    per.add(n)
        return per

    def _ant_dests(self, start: Pos, occ: Set[Pos]) -> Set[Pos]:
        per = self._perimeter(occ)
        seen = {start}
        out: Set[Pos] = set()
        stack = [start]
        while stack:
            c = stack.pop()
            for d in DIRS:
                n = (c[0] + d[0], c[1] + d[1])
                if n in occ or n in seen or n not in per:
                    continue
                if not self._slide_ok(c, n, occ):
                    continue
                seen.add(n)
                out.add(n)
                stack.append(n)
        return out

    def _spider_dests(self, start: Pos, occ: Set[Pos]) -> Set[Pos]:
        per = self._perimeter(occ)
        out: Set[Pos] = set()

        def walk(cur, depth, visited):
            if depth == 3:
                out.add(cur)
                return
            for d in DIRS:
                n = (cur[0] + d[0], cur[1] + d[1])
                if n in occ or n in visited or n not in per:
                    continue
                if not self._slide_ok(cur, n, occ):
                    continue
                walk(n, depth + 1, visited | {n})

        walk(start, 0, {start})
        out.discard(start)
        return out

    def _grasshopper_dests(self, start: Pos, occ: Set[Pos]) -> List[Pos]:
        out = []
        for d in DIRS:
            c = (start[0] + d[0], start[1] + d[1])
            if c not in occ:
                continue
            while c in occ:
                c = (c[0] + d[0], c[1] + d[1])
            out.append(c)
        return out

    def _beetle_dests(self, start: Pos, occ: Set[Pos], h: int) -> List[Pos]:
        out = []
        for d in DIRS:
            n = (start[0] + d[0], start[1] + d[1])
            if h > 0:
                out.append(n)          # 在顶层，任意相邻格都能爬
            elif n in occ:
                out.append(n)          # 爬上去
            elif self._slide_ok(start, n, occ):
                out.append(n)          # 在地面滑一格
        return out

    def _ladybug_dests(self, start: Pos, occ: Set[Pos]) -> Set[Pos]:
        per = self._perimeter(occ)
        out: Set[Pos] = set()
        lvl1 = set()
        for d in DIRS:
            lvl1.add((start[0] + d[0], start[1] + d[1]))
        lvl2 = set()
        for a in lvl1:
            for d in DIRS:
                lvl2.add((a[0] + d[0], a[1] + d[1]))
        for b in lvl2:
            for d in DIRS:
                c = (b[0] + d[0], b[1] + d[1])
                if c in occ or c == start or c not in per:
                    continue
                out.add(c)
        return out

    # ---------------------------------------------------------------- 走法生成
    def _adjacent_kinds(self, pos: Pos) -> Set[str]:
        ks = set()
        for n in neighbors(pos):
            t = self.top(n)
            if t is not None:
                k = self.pieces[t][1]
                if k != "mosquito":
                    ks.add(k)
        return ks

    def _raw_dests(self, uid: int, occ: Set[Pos], h: int) -> Set[Pos]:
        """不考虑一巢规则的候选目的地。"""
        p = self.where[uid]
        k = self.pieces[uid][1]
        if k == "queen":
            return {n for n in neighbors(p)
                    if n not in occ and self._slide_ok(p, n, occ)}
        if k == "ant":
            return self._ant_dests(p, occ)
        if k == "spider":
            return self._spider_dests(p, occ)
        if k == "grasshopper":
            return set(self._grasshopper_dests(p, occ))
        if k == "beetle":
            return set(self._beetle_dests(p, occ, h))
        if k == "ladybug":
            return self._ladybug_dests(p, occ)
        if k == "pillbug":
            return {n for n in neighbors(p)
                    if n not in occ and self._slide_ok(p, n, occ)}
        if k == "mosquito":
            dests: Set[Pos] = set()
            if h > 0:
                dests |= set(self._beetle_dests(p, occ, h))
            for ak in self._adjacent_kinds(p):
                if ak == "mosquito":
                    continue
                if ak == "beetle":
                    dests |= set(self._beetle_dests(p, occ, h))
                elif ak == "queen":
                    dests |= {n for n in neighbors(p)
                              if n not in occ and self._slide_ok(p, n, occ)}
                elif ak == "pillbug":
                    dests |= {n for n in neighbors(p)
                              if n not in occ and self._slide_ok(p, n, occ)}
                elif ak == "ant":
                    dests |= self._ant_dests(p, occ)
                elif ak == "spider":
                    dests |= self._spider_dests(p, occ)
                elif ak == "grasshopper":
                    dests |= set(self._grasshopper_dests(p, occ))
                elif ak == "ladybug":
                    dests |= self._ladybug_dests(p, occ)
            dests.discard(p)
            return dests
        return set()

    def placement_spots(self, owner: Optional[int] = None) -> List[Pos]:
        owner = self.turn if owner is None else owner
        if not self.stacks:
            return [(0, 0)]
        cand: Set[Pos] = set()
        for c in self.stacks:
            for n in neighbors(c):
                if n not in self.stacks:
                    cand.add(n)
        both = self.placed[0] >= 1 and self.placed[1] >= 1
        if both:
            ok = set()
            for n in cand:
                os_ = set()
                for m in neighbors(n):
                    o = self.owner_top(m)
                    if o is not None:
                        os_.add(o)
                if owner in os_ and os_ == {owner}:
                    ok.add(n)
            cand = ok
        return sorted(cand)

    def _pillbug_tosses(self, pb_uid: int, occ: Set[Pos]) -> List[Move]:
        out: List[Move] = []
        p = self.where[pb_uid]
        own = self.pieces[pb_uid][0]
        dests = [n for n in neighbors(p) if n not in occ]
        for n in neighbors(p):
            tgt = self.top(n)
            if tgt is None:
                continue
            if self.pieces[tgt][1] == "pillbug":
                continue
            if self.last_toss == tgt:
                continue
            if not self._removal_ok(tgt):
                continue
            for d in dests:
                if d == n:
                    continue
                out.append(Move("toss", tgt, d, frm=n, aux=pb_uid))
        return out

    def legal_moves(self, owner: Optional[int] = None) -> List[Move]:
        owner = self.turn if owner is None else owner
        if self.result:
            return []
        out: List[Move] = []

        # --- 放置
        if self.hand[owner]:
            forced = (self.queen_pos[owner] is None and self.turn_no[owner] >= 3)
            spots = self.placement_spots(owner)
            q_uid = self._queen_in_hand(owner)
            if forced and q_uid is not None and spots:
                # 第四回合，蜂后必须落子
                out += [Move("place", q_uid, s) for s in spots]
            else:
                for uid in self.hand[owner]:
                    for s in spots:
                        out.append(Move("place", uid, s))

        # --- 移动
        if self.queen_pos[owner] is not None:
            for uid in self.on_board(owner):
                p = self.where[uid]
                h = self.stacks[p].index(uid)
                if h != len(self.stacks[p]) - 1:
                    continue                      # 被压住，动不了
                if not self._removal_ok(uid):
                    continue
                # 抬起棋子后它原来的格子就是空的，滑行判定要用“空出后”的棋盘
                occ = set(self.stacks.keys())
                if len(self.stacks[p]) == 1:
                    occ.discard(p)
                for d in self._raw_dests(uid, occ, h):
                    if d == p:
                        continue
                    # 落点必须贴着剩下的蜂巢，否则会把蜂巢拆成两半
                    if not any(n in occ for n in neighbors(d)):
                        continue
                    out.append(Move("move", uid, d, frm=p))
                if self.pieces[uid][1] == "pillbug":
                    out += self._pillbug_tosses(uid, set(self.stacks.keys()))

        # 去重
        seen = set()
        uniq: List[Move] = []
        for m in out:
            k = m.key()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(m)
        return uniq

    def _queen_in_hand(self, owner: int) -> Optional[int]:
        for u in self.hand[owner]:
            if self.pieces[u][1] == "queen":
                return u
        return None

    # ---------------------------------------------------------------- 执行
    def apply(self, mv: Move) -> dict:
        if self.result:
            raise RuntimeError("对局已结束")
        owner = self.pieces[mv.uid][0]
        kind = self.pieces[mv.uid][1]
        if mv.kind == "place":
            self.hand[owner].remove(mv.uid)
            self.stacks.setdefault(mv.to, []).append(mv.uid)
            self.where[mv.uid] = mv.to
            self.placed[owner] += 1
            if kind == "queen":
                self.queen_pos[owner] = mv.to
            rec = {"p": owner, "k": kind, "uid": mv.uid,
                   "frm": None, "to": list(mv.to), "aux": None}
        elif mv.kind == "move":
            frm = self.where[mv.uid]
            st = self.stacks[frm]
            st.remove(mv.uid)
            if not st:
                del self.stacks[frm]
            self.stacks.setdefault(mv.to, []).append(mv.uid)
            self.where[mv.uid] = mv.to
            if kind == "queen":
                self.queen_pos[owner] = mv.to
            rec = {"p": owner, "k": kind, "uid": mv.uid,
                   "frm": list(frm), "to": list(mv.to), "aux": None}
        elif mv.kind == "toss":
            frm = self.where[mv.uid]
            st = self.stacks[frm]
            st.remove(mv.uid)
            if not st:
                del self.stacks[frm]
            self.stacks.setdefault(mv.to, []).append(mv.uid)
            self.where[mv.uid] = mv.to
            rec = {"p": owner, "k": kind, "uid": mv.uid,
                   "frm": list(frm), "to": list(mv.to), "aux": mv.aux}
        else:
            raise ValueError(mv.kind)

        rec["n"] = len(self.moves) + 1
        self.moves.append(rec)
        self.turn_no[owner] += 1
        self.turn = other(owner)
        self.last_toss = mv.uid if mv.kind == "toss" else None
        self.passes = 0
        self._record_hash()
        self._evaluate()
        return rec

    def _evaluate(self):
        if self.result:
            return
        mover = other(self.turn)      # 刚走完的一方
        opp = self.turn              # 即将行动的一方
        if self.queen_surrounded(opp):
            self.result = "win"
            self.winner = mover
            self.reason = "%s的蜂后被围死了！%s 获胜" % (self.names[opp], self.names[mover])
            return
        if self.queen_surrounded(mover):
            self.result = "win"
            self.winner = opp
            self.reason = "%s的蜂后被围死了！%s 获胜" % (self.names[mover], self.names[opp])
            return
        cnt = self._reps.get(self._hashes[-1], 0)
        if cnt >= 3:
            self.result = "draw"
            self.reason = "同一局面出现三次，和棋"
            return

    # ---------------------------------------------------------------- 重复局面
    def _hash_now(self) -> int:
        items = []
        for p, st in self.stacks.items():
            items.append((p, tuple(self.pieces[u] for u in st)))
        items.sort()
        return hash((tuple(items), self.turn, tuple(sorted(self.hand[0])),
                     tuple(sorted(self.hand[1]))))

    def _record_hash(self):
        h = self._hash_now()
        self._hashes.append(h)
        self._reps[h] = self._reps.get(h, 0) + 1

    # ---------------------------------------------------------------- 存档
    def options(self) -> dict:
        return {"expansions": list(self.expansions),
                "first_player": 0, "names": list(self.names)}

    def to_save(self, extra=None) -> dict:
        d = {
            "app": "虫虫蜂房",
            "format": 1,
            "options": {"expansions": list(self.expansions),
                        "names": list(self.names),
                        # 历史字段（旧版读档要看），官方规则恒为 True
                        "relaxed": True,
                        "first": self.first_player},
            "moves": [dict(m) for m in self.moves],
            "result": self.result,
            "winner": self.winner,
            "reason": self.reason,
        }
        if extra:
            d.update(extra)
        return d

    @staticmethod
    def from_save(d: dict) -> "Game":
        opts = d.get("options") or {}
        exp = opts.get("expansions") or []
        names = opts.get("names") or ["白方", "黑方"]
        recs = d.get("moves") or []
        first = opts.get("first")
        if first is None:
            # 老存档没记先手，用第一手的颜色推回去
            first = recs[0]["p"] if recs else 0
        g = Game(exp, int(first) % 2, names=names,
                 relaxed=True)          # 官方规则，老存档里的开关不再生效
        for rec in recs:
            uid = rec["uid"]
            if rec.get("frm") is None:
                mv = Move("place", uid, tuple(rec["to"]))
            elif rec.get("aux") is not None:
                mv = Move("toss", uid, tuple(rec["to"]),
                          frm=tuple(rec["frm"]), aux=rec["aux"])
            else:
                mv = Move("move", uid, tuple(rec["to"]), frm=tuple(rec["frm"]))
            g.apply(mv)
        return g


# -------------------------------------------------------------------- 记谱
def coord_text(p: Pos) -> str:
    return "(%d,%d)" % (p[0], p[1])


def move_text(g: Game, rec: dict) -> str:
    """把一步棋转成中文着法文本。"""
    k = KIND_NAMES.get(rec["k"], rec["k"])
    to = "(%d,%d)" % (rec["to"][0], rec["to"][1])
    if rec.get("frm") is None:
        return "%s落子%s" % (k, to)
    frm = "(%d,%d)" % (rec["frm"][0], rec["frm"][1])
    if rec.get("aux") is not None:
        return "鼠妇搬%s %s→%s" % (k, frm, to)
    return "%s%s→%s" % (k, frm, to)

