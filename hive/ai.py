# -*- coding: utf-8 -*-
"""电脑对手（第二版模型）。

相对第一版的改动：
1. 「死子」改成真正的判据：桥（抬起来会断巢），用 Tarjan 割点一次算完。
2. 去掉「靠近对方蜂后」项，换成「控制」：被我一枚子彻底封死的对方子数
   （严格版，只在根节点算，见 control_gain）。
3. 手牌不只看数量，还看构成（蚂蚁最值钱）。
4. 甲虫在第二层及以上额外加分（谁也锁不住它）。
5. 重复局面扣分，避免来回倒子。
6. 所有权重放在 W 里，由标定脚本覆盖。
"""

from __future__ import annotations

import random
import time

from . import book as booklib
from .rules import Game, Move, hex_dist, neighbors, other

INF = 10 ** 6

# ---- 权重（先用旧的手拍值占位，标定脚本会覆盖）
W = {
    # 正号 = 对我有利，负号 = 对我不利（评估是 W 和特征的点积，符号必须写对）
    "opp_block": 30.0,        # 对方蜂后每被占一个邻格
    "my_block": -26.0,        # 自己蜂后每被占一个邻格
    "my_tight": -110.0,       # 自己蜂后只剩一口气（比被占一格严重得多）
    "beetle_on_opp": 68.4982,    # 甲虫压在对方蜂后上
    "beetle_on_me": -130.0,   # 对方甲虫压在我蜂后上
    "beetle_near_opp": 0,  # 甲虫贴对方蜂后
    "beetle_near_me": -40.0,  # 对方甲虫贴我蜂后
    "own_on_queen": -130.0,   # 自家棋子压在自家蜂后头上（自钉死，1614 的败因）
    "q_place_ok": 40.0,       # 蜂后落点：≥5 口气且没有敌子能一手塞进气口
    "q_place_bad": -80.0,     # 落点结构不安全（1614 第 7 手）
    "beetle_high": 22.0,      # 甲虫爬到第 2 层及以上，每高一层
    "new_bridge": 0,       # 这一手让我方新增几枚桥（额外的结构惩罚）
    "bridge_me": -1.98075,       # 我方桥（抬起来会断巢 = 死子）——两次拟合都更强
    "bridge_opp": 6.0,       # 对方桥对我极有利——数据比手拍强 3 倍
    "my_ring_own": -8.0,      # 自家棋子占着我蜂后的邻格（早期多半是好事，轻罚）
    "immobile_me": -27.0,      # 我方一步都走不了的子
    "immobile_opp": 0,
    "early_ant": -25.0,       # 前 3 回合摆蚂蚁额外扣分：那个位置是"基石"
    "board_value": 10.2662,        # 场上的子按价值算：蚂蚁 3×5=15，蜘蛛 2×5=10
    "hand_count": 0,        # 双方已落子数差（摆出去才产生价值）
    "hand_value": 0.0,       # 手里留着强子（蚂蚁）是好事：
                              #   前两手会变成"基石"，尽量别拿高价值棋去填
    "mobility": 0,          # 双方"还能动的子力价值"之差（根节点算）
    "queen_mobile_me": 20.0,
    "queen_mobile_opp": -10.0,
    "opp_queen_none": 40.0,   # 对方还没落蜂后
    "my_queen_none": -160.0,  # 自己还没落蜂后（先手轴的一部分：早落蜂后＝早解锁走子）
    "rep": -85.0,             # 重复局面
    "control": 5.0,           # 根节点：新封死对方子（按价值）
    "control_threat": 3.0,    # 封死的如果是"能叫杀我蜂后"的子，价值翻 3 倍
                              #（老师：蚂蚁只该去控制会叫杀的棋，不该见子就控）
    "control_lost": 8.0,      # 根节点：放跑原本被封住的对方子（更贵）
    "opp_moves": 1.85246,         # 根节点：对方剩余着法数
                              #（2026-11-14 一度降到 0.6，导致"不控棋、不进攻"，
                              #  按老师要求还原到 v2037 的水平）
    "mobility": 9.0,          # 根节点：对方"还能动的子力价值"（原来只算到对手一侧，
                              # 现在写成显式的 opp_mobility，数值与 v2037 完全一致）
    "ant_late": 0.0,        # 第 5 回合起手里还留着蚂蚁：机动性白放着
    "gate_opp": 3.0,          # 中后期：把对方堵进窄门（每条方向）
    "gate_me": -3.0,         # 根节点：对方剩余着法数（含窄门压缩的效果）      # 根节点：放跑原本被封住的对方子（更贵）           # 根节点：封死对方子，按对方的"子力价值"累加
    "hole_gift": 0.0,        # 我方蜂后身边「白方可以直接落子」的格子，每个都是隐患
    "support_me": 0.0,         # 守在自家蜂后 2~3 格内的子（护驾）
    "beetle_guard": 0.0,      # 自家甲虫守在蜂后附近（反制对方甲虫）
    "squeeze_opp": 45.0,      # 对方蜂后气数 <=3 时，持续加压有额外价值
    "squeeze_me": -45.0,      # 自己蜂后气数 <=3 时，危险
    "tempo_attack": 60.0,     # 轮到我、对方蜂后快没气了 -> 该进攻
    "tempo_danger": -60.0,    # 轮到他、我蜂后快没气了 -> 该防守
    "ant_initiative": 10.0,   # 递减计分已写在函数里（第1只6、第2只3、第3只1）
    "queen_far": 12.0,        # 开局蜂后离敌方棋子远一点，免得一落子就被贴住
    "queen_grab": 0.0,        # 已停用：它是「对手能填我几个气口」的格子版近似，
                              # 由下面的分级预警接管
    "counter_ready": 60.0,    # 敌甲虫压着我蜂后、而我的甲虫就在旁边（能反压）
    "liberty_adv": 12.0,      # 我方蜂后气数 − 对方蜂后气数
    "threat_opp": 12.0,       # 对方蜂后邻格里，我能两步内够到的个数
    "threat_me": 0.0,         # 已停用：改用下面的分级预警（T/TT/TTT）替代
    # ---- 分级预警（老师的设计）：离"被围死"还有几步
    #      T=一步被杀 / TT=两步 / TTT=三步；对称地 V/VV/VVV=我还差几步围死对手
    #      先手比较内建在数值里：V>T, VV>TT, VVV>TTT（我快一手就不必理会他的威胁）
    #      量级锚定 v2037 的叠加总量
    "t1": -300.0, "t2": -150.0, "t3": -60.0,
    "v1": 450.0, "v2": 250.0, "v3": 120.0,
    # ---- 先手轴（老师：先走蜂后+蚂蚁的优势非常大）
    #      my_mobility − opp_mobility；蜂后没落子时我这侧恒为 0 → 早落蜂后自动加分
    "initiative": 6.0,
    # 旧的近似项全部归零，由分级预警接管（避免重复计分）
    "ring_fill": 0.0, "ring_hurry": 0.0, "ring_escape": 0.0, "ring_lost": 0.0,
    "atk_fill": 0.0, "atk_hurry": 0.0, "atk_lost": 0.0,
}

# 手里棋子的分量（用于"手里留什么"）
HAND_VALUE = {"queen": 0.0, "ant": 1.0, "beetle": 0.7,
              "spider": 0.6, "grasshopper": 0.6, "ladybug": 0.7,
              "mosquito": 0.7, "pillbug": 0.6}

# 子力价值（用于"控制/机动"——蚂蚁和蚱蜢最能跑最能卡，最值钱）
PIECE_VALUE = {"queen": 0.0, "ant": 3.0, "grasshopper": 2.5,
               "beetle": 3.0, "ladybug": 2.5, "mosquito": 2.0,
               "spider": 2.0, "pillbug": 2.0}

TIME_BUDGET = {1: 0.05, 2: 1.2, 3: 6.0}
MAX_BRANCH = {1: 99, 2: 14, 3: 22}
DEPTH_CAP = {1: 1, 2: 10, 3: 16}


def clone(g: Game) -> Game:
    h = Game.__new__(Game)
    h.relaxed = g.relaxed
    h.expansions = g.expansions
    h.kinds = g.kinds
    h.counts = g.counts
    h.pieces = g.pieces
    h.names = g.names
    h.where = dict(g.where)
    h.hand = {0: list(g.hand[0]), 1: list(g.hand[1])}
    h.stacks = {k: list(v) for k, v in g.stacks.items()}
    h.turn = g.turn
    h.turn_no = dict(g.turn_no)
    h.placed = dict(g.placed)
    h.queen_pos = dict(g.queen_pos)
    h.moves = list(g.moves)
    h.result = g.result
    h.winner = g.winner
    h.reason = g.reason
    h.last_toss = g.last_toss
    h._hashes = list(g._hashes) if hasattr(g, "_hashes") else []
    h._reps = dict(g._reps) if hasattr(g, "_reps") else {}
    h.passes = g.passes
    return h


def _apply(g: Game, mv: Move) -> Game:
    h = clone(g)
    h.apply(mv)
    return h


# ---------------------------------------------------------------- 基础量
def _blocked(g: Game, pos) -> int:
    return 0 if pos is None else sum(1 for n in neighbors(pos) if n in g.stacks)


def _articulation(occ) -> set:
    """割点：摘掉这一格会让蜂巢断开（迭代版 Tarjan）。

    这正好是「桥」的格版本：一枚子在割点上、且那堆只有它一枚，
    抬起来就断巢 —— 那就是个死子。
    """
    if len(occ) <= 2:
        return set()
    disc, low, par = {}, {}, {}
    art = set()
    t = 0
    for root in occ:
        if root in disc:
            continue
        disc[root] = low[root] = t
        t += 1
        par[root] = None
        stack = [(root, iter([n for n in neighbors(root) if n in occ]))]
        while stack:
            v, it = stack[-1]
            advanced = False
            for w in it:
                if w not in disc:
                    disc[w] = low[w] = t
                    t += 1
                    par[w] = v
                    stack.append((w, iter([n for n in neighbors(w) if n in occ])))
                    advanced = True
                    break
                elif w != par.get(v):
                    if disc[w] < low.get(v, disc[w]):
                        low[v] = disc[w]
            if advanced:
                continue
            stack.pop()
            p = par.get(v)
            if p is not None:
                if low.get(v, 0) < low.get(p, 0):
                    low[p] = low[v]
                if par.get(p) is not None and low.get(v, 0) >= disc.get(p, 0):
                    art.add(p)
        kids = 0
        for w in occ:
            if par.get(w) == root:
                kids += 1
        if kids >= 2:
            art.add(root)
    return art


def _gate_count(g: Game, owner: int) -> int:
    """官方规则的窄门：这方有几枚棋子、有几个方向被「两侧同时被占」夹死。

    对每个相邻格 q，找出与 p、q 都相邻的那两个"边角"格子；
    两个都被占 -> 往 q 这条边挤不过去。
    """
    n = 0
    for u in g.on_board(owner):
        p = g.where[u]
        for q in neighbors(p):
            flanks = [c for c in neighbors(p)
                      if c != q and c in neighbors(q)]
            if len(flanks) == 2 and all(c in g.stacks for c in flanks):
                n += 1
    return n


def _bridges(g: Game, owner: int, art=None) -> float:
    """桥的代价 = 被桥住的各棋子价值之和（桥住蚂蚁比桥住蜘蛛严重）。"""
    if art is None:
        art = _articulation(set(g.stacks))
    v = 0.0
    for u in g.on_board(owner):
        p = g.where[u]
        st = g.stacks.get(p) or []
        if st and st[-1] == u and len(st) == 1 and p in art:
            v += max(1.0, PIECE_VALUE.get(g.pieces[u][1], 2.0))
    return v


def _immobile(g: Game, owner: int) -> int:
    art = _articulation(set(g.stacks))
    n = 0
    for u in g.on_board(owner):
        p = g.where[u]
        st = g.stacks.get(p) or []
        if not st or st[-1] != u:
            continue
        kind = g.pieces[u][1]
        if kind in ("grasshopper", "ladybug", "beetle", "spider"):
            continue                      # 会跳/会爬/会绕的，很难被彻底锁
        if len(st) == 1 and p in art:
            n += 1
            continue
        if all(x in g.stacks for x in neighbors(p)):
            n += 1
    return n


def _immobile_value(g: Game, owner: int, art=None) -> float:
    """走不了的子，按价值累加：封住对方一只蚂蚁比封住一只蜘蛛值钱。"""
    if art is None:
        art = _articulation(set(g.stacks))
    total = 0.0
    for u in g.on_board(owner):
        p = g.where[u]
        st = g.stacks.get(p) or []
        if not st or st[-1] != u:
            continue
        kind = g.pieces[u][1]
        if kind in ("grasshopper", "ladybug", "beetle", "spider"):
            continue
        locked = (len(st) == 1 and p in art) or \
                 all(x in g.stacks for x in neighbors(p))
        if locked:
            total += max(1.5, PIECE_VALUE.get(kind, 2.0))
    return total


def _beetle_stats(g: Game, owner: int, queen_pos):
    on = near = high = 0
    if queen_pos is not None:
        for u in (g.stacks.get(queen_pos) or [])[1:]:
            if g.pieces[u][0] == owner and g.pieces[u][1] == "beetle":
                on += 1
    for u in g.on_board(owner):
        if g.pieces[u][1] != "beetle":
            continue
        p = g.where[u]
        lvl = g.stacks[p].index(u)
        if lvl > 0:
            high += 1          # 每只甲虫只算一次，按层数会诱发无限往上爬
        if p != queen_pos and queen_pos is not None and \
                any(n == queen_pos for n in neighbors(p)):
            near += 1
    return on, near, high


def _queen_uid(g: Game, owner: int):
    """找到蜂后那枚棋子（不能只看叠层顶端：上面可能压着自己的甲虫）。"""
    q = g.queen_pos[owner]
    if q is None:
        return None
    for u in g.stacks.get(q) or ():
        if g.pieces[u][1] == "queen" and g.pieces[u][0] == owner:
            return u
    return None


def _queen_can_move(g: Game, owner: int) -> bool:
    q = g.queen_pos[owner]
    if q is None:
        return False
    uid = _queen_uid(g, owner)
    if uid is None or g.top(q) != uid:
        return False                       # 被压住就是不能动
    if not g._removal_ok(uid):
        return False
    occ = set(g.stacks)
    if len(g.stacks[q]) == 1:
        occ.discard(q)
    for d in g._raw_dests(uid, occ, len(g.stacks[q]) - 1):
        if d != q and any(n in occ for n in neighbors(d)):
            return True
    return False


def _threat(g: Game, owner: int, enemy_queen) -> float:
    """我离「对方蜂后的空邻格」有多近 —— 按距离加权。

    距离 1 格算 3 分、2 格算 2 分、3 格算 1 分，超过 3 格不计。
    这就是「离对方蜂后近、两步就能压住」的量化版：不是数够不够得着，
    而是看贴得有多紧。
    """
    if enemy_queen is None:
        return 0.0
    holes = [c for c in neighbors(enemy_queen) if c not in g.stacks]
    if not holes:
        return 0.0
    mine = [g.where[u] for u in g.on_board(owner)]
    if not mine:
        return 0.0
    total = 0.0
    for c in holes:
        d = min(hex_dist(p, c) for p in mine)
        if d <= 3:
            total += 4.0 - d
    return total


def _hand_value(g: Game, owner: int) -> float:
    return sum(HAND_VALUE.get(g.pieces[u][1], 0.6) for u in g.hand[owner])


# ------------------------------------------------- 蜂后气口（去类型化的输棋预警）
# 老师的原则：输棋预警不分兵种 —— 甲虫压、草蜢跳、蚂蚁滑，只要会摘我一口
# 气，价码就该一样。甲虫自己的专项（压住蜂后 = 钉死）另算，这边只数「气」。
def _ring_cells(g: Game, owner: int) -> list:
    """蜂后的空邻格 = 还剩的气口。"""
    q = g.queen_pos[owner]
    if q is None:
        return []
    return [c for c in neighbors(q) if c not in g.stacks]


def _ring_fill_map(g: Game, victim: int, opp_moves=None) -> dict:
    """气口 -> 对手一手就能占进去的棋子 uid 集合（用合法着法精确算，不分兵种）。"""
    holes = _ring_cells(g, victim)
    if not holes:
        return {}
    hs = set(holes)
    if opp_moves is None:
        opp_moves = g.legal_moves(other(victim))
    out: dict = {}
    for mv in opp_moves:
        if mv.to in hs:
            out.setdefault(mv.to, set()).add(mv.uid)
    return out


def _max_match(cell2uids: dict) -> int:
    """气口 ↔ 棋子 的最大二分匹配：对手一手最多能同时盯住几个独立气口。"""
    match_u: dict = {}

    def try_cell(c, seen):
        for u in cell2uids[c]:
            if u in seen:
                continue
            seen.add(u)
            if u not in match_u or try_cell(match_u[u], seen):
                match_u[u] = c
                return True
        return False

    n = 0
    for c in cell2uids:
        if try_cell(c, set()):
            n += 1
    return n


def queen_escapes(g: Game, owner: int) -> int:
    """蜂后自己有几个合法落点（被压住时是 0）。只算蜂后自己，代价小。"""
    q = g.queen_pos[owner]
    if q is None:
        return 0
    uid = _queen_uid(g, owner)
    st = g.stacks.get(q) or []
    if uid is None or not st or st[-1] != uid:
        return 0                           # 头顶压着子（自己的也不行）＝动不了
    if not g._removal_ok(uid):
        return 0
    occ = set(g.stacks)
    if len(st) == 1:
        occ.discard(q)
    n = 0
    for d in g._raw_dests(uid, occ, len(st) - 1):
        if d != q and any(x in occ for x in neighbors(d)):
            n += 1
    return n


def ring_danger(g: Game, owner: int, opp_moves=None):
    """(libs, k, slack, esc)：气口数 / 对手能同时盯住几个 / 冗余攻击手 / 我的活路。

    k 就是「对手下一手能摘我几口气」的精确值，slack 是即便摘掉一个还剩几个
    候补攻击手 —— 这两个数完全不分兵种。
    """
    holes = _ring_cells(g, owner)
    if not holes:
        return (0, 0, 0, 0)
    fill = _ring_fill_map(g, owner, opp_moves)
    k = _max_match(fill)
    slack = sum(len(v) - 1 for v in fill.values() if len(v) > 1)
    return (len(holes), k, slack, queen_escapes(g, owner))


RING_KEYS = ("t1", "t2", "t3", "v1", "v2", "v3", "initiative")


def _surround_dist(g: Game, victim: int, attacker_moves) -> int:
    """victim 的蜂后还要几步才会被围死（不分兵种）。9 = 还早着/数不清。"""
    libs, k, slack, esc = ring_danger(g, victim, attacker_moves)
    if not libs:
        return 9
    d = libs
    if k == 0:
        d += 2          # 现在一口都盯不住，得先把子调过来
    if esc > 0:
        d += 1          # 她的蜂后还能跑一手
    return min(d, 9)


def _movable_value(g: Game, owner: int, moves) -> float:
    tops = {u for u in g.on_board(owner)
            if (g.stacks.get(g.where[u]) or [None])[-1] == u}
    mv = {m.uid for m in moves}
    return sum(PIECE_VALUE.get(g.pieces[u][1], 2.0) for u in tops if u in mv)


def race_terms(g: Game, me: int, omoves, mmoves) -> dict:
    """分级预警（T/TT/TTT vs V/VV/VVV）+ 先手轴。"""
    out = {}
    d_opp = _surround_dist(g, me, omoves)        # 我被围死还差几步
    d_me = _surround_dist(g, other(me), mmoves)  # 对手被围死还差几步
    if 1 <= d_opp <= 3:
        out["t%d" % d_opp] = W["t%d" % d_opp]
    if 1 <= d_me <= 3:
        out["v%d" % d_me] = W["v%d" % d_me]
    # 先手轴：还能动的子力价值之差（蜂后没落子时我方恒 0 → 早落蜂后自动加分）
    opp = other(me)
    init = (_movable_value(g, me, mmoves) - _movable_value(g, opp, omoves))
    if init:
        out["initiative"] = init * W["initiative"]
    return out


def ring_terms(g: Game, me: int, opp_moves=None) -> dict:
    """蜂后气口的分项（根节点独占）。

    只有当「对手能摘的气口数」逼近「我剩下的气口数」时才算重罚 ——
    气口还剩 4 个、对手只能盯 1 个时，那叫压力，不叫危险（否则蜂后会为了
    把 k 从 2 降到 1 而白走一步，正是老师说的"无意义躲蜂后"）。
    """
    libs, k, slack, esc = ring_danger(g, me, opp_moves)
    if not libs:
        return {}
    out = {}
    if k:
        out["ring_fill"] = W["ring_fill"] * k
    gap = libs - k          # 对手一口气摘完"能同时盯住的"之后，还剩几口缓冲
    if gap <= 0:
        if esc == 0:
            out["ring_lost"] = W["ring_lost"]     # 气口全被盯住、又跑不掉
        else:
            out["ring_hurry"] = W["ring_hurry"]   # 只能靠蜂后下一手逃
    elif gap == 1 and esc == 0:
        out["ring_hurry"] = W["ring_hurry"]       # 再添一个攻击手就要命
    if esc and gap <= 1:
        out["ring_escape"] = W["ring_escape"] * min(esc, 2)
    return out


def atk_ring_terms(g: Game, victim: int, attacker_moves) -> dict:
    """把同一套气口指标照到对手身上：对方蜂后越危险，我方进攻分越高。

    这就是「往对方蜂后那边下」的分数来源 —— 没有它，安静的局面上所有着法
    都是噪声级差别，AI 就会来回倒子（老师说的"缓手"）。
    """
    libs, k, slack, esc = ring_danger(g, victim, attacker_moves)
    if not libs:
        return {}
    out = {}
    if k:
        out["atk_fill"] = W["atk_fill"] * k
    gap = libs - k
    if gap <= 0 and esc == 0:
        out["atk_lost"] = W["atk_lost"]
    elif gap <= 0 or (gap == 1 and esc == 0):
        out["atk_hurry"] = W["atk_hurry"]
    return out


def _ring_libs_after(g: Game, me: int, mv: Move) -> int:
    """估算走完这一手我蜂后还剩几口气；蜂后自己动就返回 -1（要真算）。"""
    q = g.queen_pos[me]
    if q is None:
        return 9
    if g.pieces[mv.uid][1] == "queen":
        return -1
    ring = set(neighbors(q))
    occ = sum(1 for c in ring if c in g.stacks)
    if mv.to in ring and mv.to not in g.stacks:
        occ += 1
    if mv.frm is not None and mv.frm in ring:
        st = g.stacks.get(mv.frm) or []
        if len(st) == 1:
            occ -= 1
    return 6 - occ


# ---------------------------------------------------------------- 特征
FEATURES = ["opp_block", "my_block", "my_tight", "beetle_on_opp",
            "beetle_on_me", "beetle_near_opp", "beetle_near_me",
            "beetle_high", "hand_count", "hand_value", "bridge_me",
            "bridge_opp", "immobile_me", "immobile_opp",
            "queen_mobile_me", "queen_mobile_opp",
            "opp_queen_none", "my_queen_none",
            "threat_opp", "threat_me",
            "tempo_attack", "tempo_danger", "squeeze_opp", "squeeze_me",
            "support_me", "beetle_guard", "hole_gift",
            "gate_opp", "gate_me", "ant_late", "board_value",
            "liberty_adv", "ant_initiative", "queen_far",
            "queen_grab", "counter_ready", "own_on_queen"]


def features(g: Game, me: int) -> dict:
    """把局面拆成特征字典 —— 评估就是 W 和它的内积，方便标定。"""
    opp = other(me)
    mq, oq = g.queen_pos[me], g.queen_pos[opp]
    f = {k: 0.0 for k in FEATURES}
    # 割点只算一次，四个分项共用（原先每项各跑一遍 Tarjan，等于白烧 3/4 的时间）
    art = _articulation(set(g.stacks))

    if oq is None:
        f["opp_queen_none"] = 1.0
    else:
        f["opp_block"] = float(_blocked(g, oq))
        f["queen_mobile_opp"] = 1.0 if _queen_can_move(g, opp) else 0.0
    if mq is None:
        # 前两回合不催她落蜂后：否则首手就把蜂后扔出去，等于另一种浪费。
        if g.turn_no.get(me, 0) >= 2:
            f["my_queen_none"] = 1.0
    else:
        b = _blocked(g, mq)
        own_ring = 0
        for n in neighbors(mq):
            st = g.stacks.get(n) or []
            if st and g.pieces[st[-1]][0] == me:
                own_ring += 1
        f["my_block"] = float(b - own_ring)     # 敌方占我蜂后邻格
        # 自家棋子占气口：早期便宜，气越少越致命。
        # 气 4+ -> 1 倍，气 3 -> 3 倍，气 2 及以下 -> 6 倍。
        lib_left = 6 - b
        if lib_left <= 2:
            scale = 6.0
        elif lib_left <= 3:
            scale = 3.0
        else:
            scale = 1.0
        f["my_ring_own"] = float(own_ring) * scale
        f["_my_total"] = float(b)               # 总气口占用，供 my_tight 用
        f["my_tight"] = 1.0 if b >= 5 else 0.0
        # 自家棋子压在自家蜂后头上 = 自钉死：蜂后永远不能动，还给对方甲虫搭梯子
        #（1614 第 29 手就是这么输的；`beetle_on_me` 只算敌方甲虫，漏了这一项）
        qu = _queen_uid(g, me)
        sq = g.stacks.get(mq) or []
        if qu is not None and qu in sq:
            i = sq.index(qu)
            f["own_on_queen"] = float(sum(1 for u in sq[i + 1:]
                                          if g.pieces[u][0] == me))
        # 「蜂后能动」只在第 3 回合起才加分：
        # 否则首手摆蜂后先天比别的棋子多 20 分，成了最划算的一手。
        if g.turn_no.get(me, 0) >= 2 and _queen_can_move(g, me):
            f["queen_mobile_me"] = 1.0

    my_on, my_near, my_high = _beetle_stats(g, me, oq)
    op_on, op_near, op_high = _beetle_stats(g, opp, mq)
    f["beetle_on_opp"] = float(my_on)
    f["beetle_near_opp"] = float(my_near)
    f["beetle_high"] = float(my_high - op_high)
    f["beetle_on_me"] = float(op_on)
    f["beetle_near_me"] = float(op_near)

    f["hand_count"] = float(len(g.hand[opp]) - len(g.hand[me]))
    f["hand_value"] = _hand_value(g, opp) - _hand_value(g, me)

    # 护驾：蜂后身边的子力是资产（1 格内的会被 my_block 罚，这里只算 2~3 格）
    sup = 0
    bgd = 0
    if mq is not None:
        for u in g.on_board(me):
            d = hex_dist(g.where[u], mq)
            if 2 <= d <= 3:
                sup += 1
            if d <= 2 and g.pieces[u][1] == "beetle":
                bgd += 1
    f["support_me"] = float(sup)
    f["beetle_guard"] = float(bgd)

    # 「白送的落点」：我方蜂后的空邻格里，白方可以直接落子的那些。
    # 落子规则要求「不碰对方棋子」，所以我方棋子贴着这些格子时，
    # 对方只能走子过来、不能直接落子 —— 这就是护驾的真正价值。
    gift = 0
    if mq is not None:
        # 注意：必须排除蜂后自己 —— 每个邻格当然都贴着蜂后，
        # 否则这个计数永远是 0。
        # 按格子排除蜂后自己（不能用 stack[-1]，那可能是压在
        # 蜂后头上的敌子），否则每个邻格都贴着蜂后，结果恒为 0。
        mine_pos = [g.where[u] for u in g.on_board(me)
                    if g.where[u] != mq]
        for c in neighbors(mq):
            if c in g.stacks:
                continue
            if not any(hex_dist(p, c) == 1 for p in mine_pos):
                gift += 1
    f["hole_gift"] = float(gift)

    f["threat_opp"] = float(_threat(g, me, oq))
    f["threat_me"] = float(_threat(g, opp, mq))

    # 气数 / 先手：谁的蜂后快没气了，而且现在轮到谁
    opp_lib = 6 - int(f["opp_block"]) if oq is not None else 6
    my_lib = 6 - int(f.pop("_my_total", f["my_block"] + f["my_ring_own"])) \
        if mq is not None else 6
    if oq is not None and opp_lib <= 3:
        f["squeeze_opp"] = 1.0
        if opp_lib <= 2 and g.turn == me:
            f["tempo_attack"] = 1.0
    if mq is not None and my_lib <= 3:
        f["squeeze_me"] = 1.0
        if my_lib <= 2 and g.turn != me:
            f["tempo_danger"] = 1.0

    # 窄门只在中后期算：开局棋子少，两侧同时被占多是巧合，不是战术。
    if (g.turn_no.get(0, 0) + g.turn_no.get(1, 0)) >= 10:
        f["gate_opp"] = float(_gate_count(g, opp))
        f["gate_me"] = float(_gate_count(g, me))

    # 第 5 回合起，手里还压着蚂蚁要扣分（象棋谚语：三步不出车，一盘臭棋）
    if g.turn_no.get(me, 0) >= 3:
        f["ant_late"] = float(sum(1 for u in g.hand[me]
                                  if g.pieces[u][1] == "ant"))

    # 场上 vs 手里的价值差：越有价值的棋子摆到场上收益越大，
    # 但能不能发挥作用由搜索决定 —— 不写死"第几回合出蚂蚁"。
    f["board_value"] = (
        sum(PIECE_VALUE.get(g.pieces[u][1], 2.0) for u in g.on_board(me))
        - sum(PIECE_VALUE.get(g.pieces[u][1], 2.0) for u in g.on_board(opp)))

    # 蚂蚁是"特种兵"：第一只最值钱，第二只价值减半，第三只几乎不值。
    def _ant_val(n):
        v = 0.0
        if n >= 1:
            v += 6.0
        if n >= 2:
            v += 3.0
        if n >= 3:
            v += 1.0
        return v

    f["ant_initiative"] = (_ant_val(sum(1 for u in g.on_board(me)
                                       if g.pieces[u][1] == "ant"))
                           - _ant_val(sum(1 for u in g.on_board(opp)
                                          if g.pieces[u][1] == "ant")))

    # 开局六回合内，蜂后落点要离敌方棋子远一些，否则一落子就被贴住/控制。
    if mq is not None and g.turn_no.get(me, 0) < 6:
        enemy_pos = [g.where[u] for u in g.on_board(opp)]
        if enemy_pos:
            f["queen_far"] = float(min(4, min(hex_dist(mq, p) for p in enemy_pos)))

    if mq is not None:
        enemy_pos = [g.where[u] for u in g.on_board(opp)]
        # 敌人一步就能摘掉的气：我方蜂后空邻格里，有敌方棋子贴着。
        grab = 0
        if enemy_pos:
            for c in neighbors(mq):
                if c in g.stacks:
                    continue
                if any(hex_dist(p, c) == 1 for p in enemy_pos):
                    grab += 1
        f["queen_grab"] = float(grab)

        # 反压制：敌甲虫压在我蜂后头上，而我的甲虫就在旁边 -> 下一手能反压回去。
        st = g.stacks.get(mq) or []
        enemy_beetle_on_top = False
        if len(st) >= 2:
            top = st[-1]
            if g.pieces[top][0] == opp and g.pieces[top][1] == "beetle":
                enemy_beetle_on_top = True
        if enemy_beetle_on_top:
            my_beetles = [g.where[u] for u in g.on_board(me)
                          if g.pieces[u][1] == "beetle"]
            if any(hex_dist(p, mq) == 1 for p in my_beetles):
                f["counter_ready"] = 1.0

    # 气数差：我不危险、他落后时，继续压缩他的走法会自然更有吸引力。
    if mq is not None and oq is not None:
        f["liberty_adv"] = float(_blocked(g, oq) - _blocked(g, mq))

    f["bridge_me"] = float(_bridges(g, me, art))
    f["bridge_opp"] = float(_bridges(g, opp, art))
    f["immobile_me"] = _immobile_value(g, me, art)
    f["immobile_opp"] = _immobile_value(g, opp, art)
    return f


def evaluate(g: Game, me: int) -> float:
    if g.result == "win":
        return INF if g.winner == me else -INF
    if g.result == "draw":
        return 0.0
    f = features(g, me)
    s = 0.0
    for k, v in f.items():
        if v:
            s += W.get(k, 0.0) * v
    try:
        rep = g._reps.get(g._hashes[-1], 0)
    except Exception:
        rep = 0
    if rep >= 2:
        # 符号修过：W["rep"] 本身是负数，这里必须"加"，原来是减 →
        # 结果每重复一次反而白送 85 分，等于奖励来回倒子。
        s += (rep - 1) * W["rep"]
    return s

# ------------------------------------------------- 严格控制（只在根节点用）
def _immobile_pieces(g: Game, owner: int, moves=None) -> set:
    """严格版：用合法着法算，真正一步都走不了的子。"""
    tops = set()
    for u in g.on_board(owner):
        p = g.where[u]
        st = g.stacks.get(p) or []
        if st and st[-1] == u:
            tops.add(u)
    if moves is None:
        moves = g.legal_moves()
    movable = set()
    for mv in moves:
        if mv.uid in tops:
            movable.add(mv.uid)
    return tops - movable


def control_gain(g_before: Game, g_after: Game, me: int) -> float:
    """这一手封死了对方多少"价值"。

    按老师的原则：用低价值的子锁死对方高价值的子是赚的；
    锁死蚂蚁/蚱蜢（3 分）比锁死蜘蛛（2 分）值钱。
    """
    opp = other(me)
    before = _immobile_pieces(g_before, opp)
    after = _immobile_pieces(g_after, opp)
    gain = 0.0
    for u in after - before:
        gain += PIECE_VALUE.get(g_after.pieces[u][1], 2.0)
    return gain


def control_loss(g_before: Game, g_after: Game, me: int,
                 origin=None) -> float:
    """这一手放跑了多少原本被我封住的对方棋子。

    对应老师说的"别用有战术任务的棋子去干别的"：一只锁着白蚂蚁的黑蚂蚁，
    调走它就等于把那只白蚂蚁放出来，代价要算清楚。
    """
    opp = other(me)
    before = _immobile_pieces(g_before, opp)
    after = _immobile_pieces(g_after, opp)
    lost = 0.0
    for u in before - after:
        # 只算"这枚棋子本来压着、现在放跑"的：被解封的敌子必须在原位附近。
        # 否则一只路过的蚂蚁也会被算成放跑了全盘的敌子，结果蚂蚁全被钉死。
        if origin is not None and hex_dist(g_after.where[u], origin) > 2:
            continue
        lost += max(1.0, PIECE_VALUE.get(g_after.pieces[u][1], 2.0))
    return lost


def mobility_value(g: Game, owner: int) -> float:
    """owner 还有几步可走的子，按价值累加（老师的第二个关注点）。"""
    movable = set()
    for mv in g.legal_moves():
        movable.add(mv.uid)
    v = 0.0
    for u in g.on_board(owner):
        if u in movable:
            v += PIECE_VALUE.get(g.pieces[u][1], 2.0)
    return v


# ---------------------------------------------------------------- 搜索
def _order_key(g: Game, mv: Move, me: int, maxing: bool):
    tgt = g.queen_pos[other(me)] if maxing else g.queen_pos[me]
    d = hex_dist(mv.to, tgt) if tgt is not None else 0
    return (d, 0 if mv.kind == "place" else 1)


def _search(g: Game, me: int, depth: int, alpha: float, beta: float,
            deadline: float, nodes: list, tt: dict):
    nodes[0] += 1
    if g.result == "win":
        # 带着"还有几层"来算：赢就不愿意拖（INF-剩余层），输就尽量拖
        # （-INF+剩余层）。否则一堆必败手都是 -INF 同等分，AI 会随便乱走，
        # 看上去就像"无动于衷"。
        return (INF - depth) if g.winner == me else (-INF + depth)
    if depth <= 0:
        return evaluate(g, me)

    key = (g.turn, g._hashes[-1] if g._hashes else 0)
    hit = tt.get(key)
    if hit is not None and hit[0] >= depth:
        _d, val, flag = hit
        if flag == 0:
            return val
        if flag == 1 and val > alpha:
            alpha = val
        elif flag == 2 and val < beta:
            beta = val
        if alpha >= beta:
            return val

    moves = g.legal_moves()
    if not moves:
        # 老师定的规则：一方无棋可动就判负。搜索里必须当成终局，
        # 否则引擎既不会去把对手困死，也不会提防自己被困死
        #（实战里近三成对局是以「无棋可动」结束的）。
        return (INF - depth) if g.turn != me else (-INF + depth)

    maxing = (g.turn == me)
    moves.sort(key=lambda m: _order_key(g, m, me, maxing))
    if len(moves) > MAX_BRANCH[3]:
        moves = moves[:MAX_BRANCH[3]]

    orig_alpha, orig_beta = alpha, beta
    if maxing:
        best = -INF
        for mv in moves:
            v = _search(_apply(g, mv), me, depth - 1, alpha, beta,
                        deadline, nodes, tt)
            if v > best:
                best = v
            if best > alpha:
                alpha = best
            if alpha >= beta or time.time() > deadline:
                break
    else:
        best = INF
        for mv in moves:
            v = _search(_apply(g, mv), me, depth - 1, alpha, beta,
                        deadline, nodes, tt)
            if v < best:
                best = v
            if best < beta:
                beta = best
            if beta <= alpha or time.time() > deadline:
                break

    if best <= orig_alpha:
        flag = 2
    elif best >= orig_beta:
        flag = 1
    else:
        flag = 0
    if len(tt) < 400000:
        tt[key] = (depth, best, flag)
    return best


# ---- T/V 分级：必须是"搜到的必胜/必输路线"，不是静态估算
def _fill_moves(g: Game, victim: int):
    q = g.queen_pos[victim]
    if q is None:
        return []
    holes = {c for c in neighbors(q) if c not in g.stacks}
    return [m for m in g.legal_moves(other(victim)) if m.to in holes]


def _def_moves(g: Game, defender: int):
    q = g.queen_pos[defender]
    legal = g.legal_moves(defender)
    if q is None:
        return legal
    ring = set(neighbors(q))
    near = set()
    for c in ring:
        near.update(neighbors(c))
    out = [m for m in legal
           if m.to in ring or m.frm in ring or m.to == q or m.to in near]
    return out


def _mate_defend(g: Game, attacker: int, plies: int, nodes) -> bool:
    """守方能否撑过 plies 层。"""
    if plies <= 0:
        return True
    defender = other(attacker)
    moves = _def_moves(g, defender)
    if not moves:
        return False                     # 无棋可动 = 输
    for mv in moves:
        nodes[0] += 1
        if nodes[0] > 1500:
            raise RuntimeError
        h = _apply(g, mv)
        if h.result == "win" and h.winner == attacker:
            continue
        if h.result:
            return True
        if not _mate_attack(h, attacker, plies - 1, nodes):
            return True
    return False


def _mate_attack(g: Game, attacker: int, plies: int, nodes) -> bool:
    """攻方能否在 plies 层内强行围死对方蜂后。"""
    if plies <= 0:
        return False
    for mv in _fill_moves(g, other(attacker)):
        nodes[0] += 1
        if nodes[0] > 1500:
            raise RuntimeError
        h = _apply(g, mv)
        if h.result == "win" and h.winner == attacker:
            return True
        if h.result:
            continue
        if not _mate_defend(h, attacker, plies - 1, nodes):
            return True
    return False


_RACE_DEADLINE = [0.0]      # T/V 搜索的总闸门（由 choose_move 设置）


def forced_level(g: Game, attacker: int, max_n: int = 3) -> int:
    """attacker 最快几步能围死对方（1/2/3），搜不到返回 0。"""
    for n in range(1, max_n + 1):
        if _RACE_DEADLINE[0] and time.time() > _RACE_DEADLINE[0]:
            return 0                     # 预算用完就不做证明，宁可不给 T/V
        nodes = [0]
        try:
            if _mate_attack(g, attacker, 2 * n - 1, nodes):
                return n
        except RuntimeError:
            return 0
    return 0


def root_terms(g: Game, me: int, mv: Move, level: int = 2, cache=None):
    """根节点一手棋的静态分 + 分项贡献（choose_move 与分析脚本共用）。

    返回 (value, 走完之后的局面, {项: 贡献})。
    这样"为什么这手比那手高"可以逐项拆出来，不用靠猜。
    cache 用来在各条候选之间共享"走棋之前"的那份着法表。
    """
    h = _apply(g, mv)
    terms: dict = {}
    if h.result:
        return (INF if h.winner == me else -INF), h, terms
    for k, val in features(h, me).items():
        if val:
            d = W.get(k, 0.0) * val
            terms[k] = d
    try:
        rep = h._reps.get(h._hashes[-1], 0)
    except Exception:
        rep = 0
    if rep >= 2:
        terms["rep"] = (rep - 1) * W["rep"]        # W 是负数 → 这是扣分
    if level >= 2:
        # 这一手如果把我方子变成桥（以后再也动不了），额外扣分
        if (mv.frm is None and g.pieces[mv.uid][1] == "ant"
                and g.turn_no[me] <= 3):
            # 前两个回合几乎是禁止的：那两手会变成"基石"，蚂蚁放那儿就废了。
            # 第三、四回合开始只是不鼓励。
            if g.turn_no[me] <= 0:
                terms["early_ant_hard"] = -20.0
        grew = _bridges(h, me) - _bridges(g, me)
        if grew > 0:
            terms["new_bridge"] = -grew * W["new_bridge"]
        # 走完这一手就轮到对手，所以这一份着法表两边都能用：
        # 封死了谁（control）、对手还剩多少路（opp_moves）、他能不能叫杀（fillers）。
        opp = other(me)
        omoves = h.legal_moves()
        after_imm = _immobile_pieces(h, opp, omoves)
        if cache is not None:
            before_imm = cache.get("before_imm")
            if before_imm is None:
                before_imm = _immobile_pieces(g, opp)
                cache["before_imm"] = before_imm
        else:
            before_imm = _immobile_pieces(g, opp)
        holes = set(_ring_cells(h, me))
        fillers = {m.uid for m in omoves if m.to in holes} if holes else set()
        cg = 0.0
        for u in after_imm - before_imm:
            v = PIECE_VALUE.get(h.pieces[u][1], 2.0)
            if u in fillers:
                v *= W["control_threat"]
            cg += v
        if cg:
            terms["control"] = cg * W["control"]
        cl = 0.0
        is_q_place = (mv.frm is None and g.pieces[mv.uid][1] == "queen")
        for u in before_imm - after_imm:
            # 只算"这枚棋子本来压着、现在放跑"的：被解封的敌子必须在原位附近。
            if mv.frm is not None and hex_dist(h.where[u], mv.frm) > 2:
                continue
            cl += max(1.0, PIECE_VALUE.get(h.pieces[u][1], 2.0))
        if cl:
            terms["control_lost"] = -cl * W["control_lost"]
        terms["opp_moves"] = -len(omoves) * W["opp_moves"]
        # 对方的"机动子力价值"：走不动的子按价值扣它的分（v2037 的 mobility 项）。
        # 注意按**棋子**累加，不是按着法累加 —— 一个子有 5 条着法也只算一次。
        opp_top = {u for u in h.on_board(opp)
                   if (h.stacks.get(h.where[u]) or [None])[-1] == u}
        opp_movable = {mv2.uid for mv2 in omoves}
        opp_mob = 0.0
        for u in opp_top:
            if u in opp_movable:
                opp_mob += PIECE_VALUE.get(h.pieces[u][1], 2.0)
        terms["opp_mobility"] = -opp_mob * W["mobility"]
        # 分级预警：只有**真搜到**必胜/必输路线才给 T/V（老师的要求）
        if (_ring_libs_after(g, me, mv) <= 3
                or len(_ring_cells(h, me)) <= 3
                or len(_ring_cells(h, opp)) <= 3):
            mmoves = h.legal_moves(me)
            terms["initiative"] = (_movable_value(h, me, mmoves)
                                   - _movable_value(h, opp, omoves)) * W["initiative"]
            lv = forced_level(h, me, 3)          # 我最快几步杀
            if lv:
                terms["v%d" % lv] = W["v%d" % lv]
            lt = forced_level(h, opp, 3)         # 对手最快几步杀我
            if lt:
                terms["t%d" % lt] = W["t%d" % lt]
            if is_q_place:
                lq, kq, _sl, _eq = ring_danger(h, me, omoves)
                if lq >= 5 and kq == 0:
                    terms["q_place_ok"] = W["q_place_ok"]
                else:
                    terms["q_place_bad"] = W["q_place_bad"]
        else:
            # 不紧张时只算先手轴（需要双方着法表；我方着法表这里才生成）
            mmoves = h.legal_moves(me)
            init = (_movable_value(h, me, mmoves)
                    - _movable_value(h, opp, omoves))
            if init:
                terms["initiative"] = init * W["initiative"]
    return sum(terms.values()), h, terms


def choose_move(g: Game, level: int = 2, rng: random.Random | None = None,
                use_book: bool = True):
    rng = rng or random.Random()
    me = g.turn
    moves = g.legal_moves()
    if not moves:
        return None

    for mv in moves:
        h = _apply(g, mv)
        if h.result == "win" and h.winner == me:
            return mv
        # 把对手走成「无棋可动」也是赢（老师定的规则）
        if not h.result and not h.legal_moves():
            return mv

    if use_book and level >= 3:
        try:
            mv = booklib.lookup(booklib.get_book(), g)
        except Exception:
            mv = None
        if mv is not None:
            return mv

    budget = TIME_BUDGET.get(level, 1.2)
    deadline = time.time() + budget
    _RACE_DEADLINE[0] = time.time() + budget * 0.25   # T/V 证明只用前 1/4 预算
    depth_cap = DEPTH_CAP.get(level, 6)
    branch = MAX_BRANCH.get(level, 14)

    scored = []
    priors = {}
    term_cache: dict = {}
    for mv in moves:
        v, h, t = root_terms(g, me, mv, level, term_cache)
        scored.append((v, mv))
        # 气口危险度是根节点独占的先验：后面几层搜索也要带上它，
        # 否则「子节点只按叶评估」会把这里算出来的危险度冲掉。
        p = sum(val for k, val in t.items() if k in RING_KEYS)
        if p:
            priors[mv.key()] = p
    scored.sort(key=lambda x: -x[0])

    # 一手棋的价值往往要到几步之后才显出来（摆子尤其如此），
    # 所以用「两层搜索」重排前 24 名：把对方的应手也算进去。
    # 只重排前面的，代价可控；后面的本来就是候选外。
    if level >= 2 and len(scored) > 4:
        cut = min(24, len(scored))
        top = scored[:cut]
        nodes2 = [0]
        tt2 = {}
        dl2 = min(deadline, time.time() + budget * 0.35)
        re_scored = []
        for v1, mv in top:
            if time.time() > dl2:
                re_scored.append((v1, mv))
                continue
            h = _apply(g, mv)
            if h.result:
                re_scored.append((v1, mv))
                continue
            v2 = _search(h, me, 2, -INF, INF, dl2, nodes2, tt2)
            re_scored.append((v2 + priors.get(mv.key(), 0.0), mv))
        re_scored.sort(key=lambda x: -x[0])
        scored = re_scored + scored[cut:]

    roots = [m for _s, m in scored[:max(branch, 4)]]

    # 蜂后吃紧时保底：静态分常被 opp_moves / immobile 这些大数字压住，
    # 万一唯一的救命手（蜂后自己跑、把自堵气口的子撤走）排在候选外，
    # 后面的搜索再深也看不见它。这几类手无条件塞进候选。
    if priors:
        seen = {m.key() for m in roots}
        qpos = g.queen_pos[me]
        spare = []
        for mv in moves:
            if qpos is None:
                break
            if mv.frm == qpos:
                spare.append(mv)                       # 蜂后自己跑
            elif mv.frm is not None and mv.frm in neighbors(qpos) \
                    and len(g.stacks.get(mv.frm) or ()) == 1:
                spare.append(mv)                       # 把自堵气口的子撤走
            if len(spare) >= 4:
                break
        for mv in spare:
            if mv.key() not in seen:
                roots.append(mv)
                seen.add(mv.key())

    if level <= 1:
        top = scored[: max(1, len(scored) // 3)]
        return rng.choice(top)[1]

    best_mv = roots[0]
    nodes = [0]
    tt: dict = {}
    for depth in range(1, depth_cap + 1):
        alpha, beta = -INF, INF
        cur_best, cur_val = None, -INF
        for mv in roots:
            h = _apply(g, mv)
            if h.result == "win" and h.winner == me:
                return mv
            v = (_search(h, me, depth - 1, alpha, beta, deadline, nodes, tt)
                 + priors.get(mv.key(), 0.0))
            if v > cur_val:
                cur_val, cur_best = v, mv
            if v > alpha:
                alpha = v
            if time.time() > deadline:
                break
        if cur_best is not None and cur_val > -INF:
            best_mv = cur_best
        if time.time() > deadline:
            break
    return best_mv
