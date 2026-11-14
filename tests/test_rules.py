# -*- coding: utf-8 -*-
"""虫虫蜂房规则内核自测。 运行： python -m tests.test_rules"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hive.rules import (  # noqa: E402
    Game, Move, neighbors, DIRS, hex_dist, move_text,
)

FAILS = []


def check(cond, msg):
    if cond:
        print("  ok   ", msg)
    else:
        print("  FAIL ", msg)
        FAILS.append(msg)


def force_place(g, owner, kind, pos):
    """绕过回合限制直接摆子，用于构造测试局面。"""
    uid = next(u for u in g.hand[owner] if g.pieces[u][1] == kind)
    g.hand[owner].remove(uid)
    g.stacks.setdefault(pos, []).append(uid)
    g.where[uid] = pos
    g.placed[owner] += 1
    if kind == "queen":
        g.queen_pos[owner] = pos
    return uid


def moves_of(g, owner=None):
    return g.legal_moves(owner)


def dests(g, uid):
    p = g.where[uid]
    h = g.stacks[p].index(uid)
    occ = set(g.stacks.keys())
    if len(g.stacks[p]) == 1:
        occ.discard(p)
    return g._raw_dests(uid, occ, h)


def test_setup():
    print("[初始设置]")
    g = Game()
    check(sum(len(v) for v in g.hand.values()) == 22, "基础版共 22 枚棋子")
    check(len(g.hand[0]) == 11 and len(g.hand[1]) == 11, "每方 11 枚")
    g2 = Game(["ladybug", "mosquito", "pillbug"])
    check(len(g2.hand[0]) == 14, "带三扩展时每方 14 枚")
    check(g.stacks == {}, "开局棋盘为空")
    check(g.turn == 0, "白方先手")


def test_opening():
    print("[开局放置]")
    g = Game()
    ms = g.legal_moves()
    dests_ = {m.to for m in ms}
    check(dests_ == {(0, 0)}, "第一手只能下在原点")
    check(len(ms) == 11, "第一手有 11 种选法")
    g.apply(Move("place", next(m.uid for m in ms if m.uid == 0), (0, 0)))
    ms = g.legal_moves()
    check(len({m.to for m in ms}) == 6, "黑方第一手只能贴着白子（6 个位置）")
    check(all(hex_dist(m.to, (0, 0)) == 1 for m in ms), "黑方落点均与原点相邻")


def test_own_colour_rule():
    print("[落子须贴己方、不可贴对方]")
    g = Game()
    force_place(g, 0, "queen", (0, 0))
    force_place(g, 1, "queen", (1, 0))
    spots = set(g.placement_spots(0))
    # 与黑后 (1,0) 相邻的格子不能下白棋
    for n in neighbors((1, 0)):
        check(n not in spots, "黑后邻格 %s 不可放白棋" % (n,))


def test_queen_deadline():
    print("[第四回合必须下蜂后]")
    g = Game()
    force_place(g, 1, "ant", (1, 0))
    force_place(g, 0, "ant", (0, 0))
    g.turn = 0
    g.turn_no[0] = 3          # 白方第 4 回合
    g.queen_pos[0] = None
    ms = g.legal_moves()
    kinds = {g.pieces[m.uid][1] for m in ms}
    check(kinds == {"queen"}, "第四回合只能落蜂后，实际=%s" % kinds)


def test_move_needs_queen():
    print("[未下蜂后不能动子]")
    g = Game()
    force_place(g, 0, "ant", (0, 0))
    force_place(g, 1, "queen", (1, 0))
    g.turn = 0
    g.queen_pos[0] = None
    ms = g.legal_moves()
    check(all(m.kind == "place" for m in ms), "蜂后未下时只能落子")


def test_queen_move():
    print("[蜂后走一格]")
    g = Game()
    q = force_place(g, 0, "queen", (0, 0))
    force_place(g, 0, "ant", (1, 0))
    force_place(g, 0, "ant", (0, 1))
    d = dests(g, q)
    check((1, 0) not in d and (0, 1) not in d, "不能走到已占据格")
    check((0, -1) in d, "蜂后可走向空格 (0,-1)")


def test_freedom_to_move():
    print("[自由移动规则：两侧同时被占才滑不过去]")
    g = Game()
    q = force_place(g, 0, "queen", (0, 0))
    # 蜂后东南这一格，共用边两侧是「东北」和「南」
    force_place(g, 1, "ant", (0, -1))     # 北
    force_place(g, 1, "ant", (1, -1))     # 东北：只挡住东南的一侧
    d = dests(g, q)
    check((1, 0) in d, "只被一侧挡着时可以挤过去（官方规则）")
    force_place(g, 1, "ant", (0, 1))      # 南：东南的另一侧
    d = dests(g, q)
    check((1, 0) not in d, "东北与南同时被占，东南方向就滑不过去")


def test_one_hive():
    print("[一巢规则]")
    g = Game()
    a = force_place(g, 0, "ant", (0, 0))
    q = force_place(g, 0, "queen", (1, 0))
    b = force_place(g, 0, "ant", (2, 0))
    check(g._removal_ok(a), "端点可以抬起")
    check(not g._removal_ok(q), "中间的桥接棋子不能抬（会断巢）")
    ms = [m for m in g.legal_moves(0) if m.uid == q]
    check(ms == [], "蜂后被判为不可移动")


def test_grasshopper():
    print("[蚱蜢跳跃]")
    g = Game()
    gh = force_place(g, 0, "grasshopper", (0, 0))
    force_place(g, 1, "ant", (1, 0))
    force_place(g, 1, "ant", (2, 0))
    d = dests(g, gh)
    check((3, 0) in d, "跳过两子后落点 (3,0)")
    check((1, 0) not in d, "不能落在被跳的棋子上")


SHORT = {"q": "queen", "b": "beetle", "s": "spider", "g": "grasshopper", "a": "ant"}


def load_board(g, spec):
    """按 {"q0": ...} 形式直接摆出一个局面。"""
    for pos, items in spec.items():
        for tag in items:
            kind = SHORT[tag[0]]
            owner = int(tag[1])
            uid = next(u for u in g.hand[owner] if g.pieces[u][1] == kind)
            g.hand[owner].remove(uid)
            g.stacks.setdefault(pos, []).append(uid)
            g.where[uid] = pos
            g.placed[owner] += 1
            if kind == "queen":
                g.queen_pos[owner] = pos


def uid_at(g, pos, kind=None, owner=None):
    for u in g.stacks.get(pos, []):
        if kind is not None and g.pieces[u][1] != kind:
            continue
        if owner is not None and g.pieces[u][0] != owner:
            continue
        return u
    raise KeyError((pos, kind, owner))


# 真实对局中截取的局面，兵蚁站在外缘拐角（官方规则下的可达格）
ANT_BOARD = {
    (-1, 1): ["s1"], (-1, 2): ["g1"], (0, -1): ["s0"], (0, 0): ["g0"],
    (0, 2): ["q1"], (1, -1): ["q0"], (1, 2): ["b1"], (2, -2): ["a0"],
    (2, 1): ["b1"], (3, -2): ["s0"], (3, 0): ["a1"], (4, -3): ["a0"],
}
ANT_EXPECT = [(-2, 1), (-2, 2), (-2, 3), (-1, -1), (-1, 0), (-1, 3),
              (0, -2), (0, 1), (0, 3), (1, -2), (1, 0), (1, 1),
              (1, 3), (2, -3), (2, -1), (2, 0), (2, 2), (3, -3),
              (3, -1), (3, 1), (4, -4), (4, -2), (5, -4), (5, -3)]

# 蜘蛛只有两条出路的局面（官方规则下的可达格）
SPIDER_BOARD = {
    (-3, 4): ["a0"], (-2, 2): ["s0"], (-2, 4): ["g0"], (-1, 1): ["a0"],
    (-1, 2): ["g0"], (-1, 3): ["q0", "b0"], (-1, 4): ["g0"], (0, 0): ["a0"],
    (1, 0): ["q1"], (1, 1): ["s1"], (2, -2): ["s1"], (2, -1): ["a1"],
    (2, 0): ["b1"], (2, 2): ["a1"], (3, -1): ["g1"], (3, 0): ["g1"],
    (3, 1): ["g1"],
}
SPIDER_EXPECT = [(0, 1), (0, 2), (0, 3), (0, 4),
                 (1, 2), (1, 3), (2, 1), (2, 3)]


def test_spider():
    print("[蜘蛛走三步]")
    g = Game()
    load_board(g, SPIDER_BOARD)
    sp = uid_at(g, (1, 1), "spider", 1)
    d = dests(g, sp)
    check(sorted(d) == SPIDER_EXPECT, "蜘蛛落点与已知局面一致: %s" % (d,))
    check((1, 1) not in d, "蜘蛛不会原地不动")
    check(all(hex_dist((1, 1), x) <= 3 for x in d), "蜘蛛落点距离不超过 3")


def test_beetle():
    print("[甲虫爬行]")
    g = Game()
    b1 = force_place(g, 0, "beetle", (0, 0))
    force_place(g, 1, "ant", (1, 0))
    d = dests(g, b1)
    check((1, 0) in d, "甲虫可爬上对方棋子")
    # 爬到顶上后
    g.apply(Move("move", b1, (1, 0), frm=(0, 0)))
    check(len(g.stacks[(1, 0)]) == 2, "甲虫叠在别人上面")
    check(g.top((1, 0)) == b1, "顶层是甲虫")
    d = dests(g, b1)
    check((0, 0) in d, "顶层的甲虫可爬回空格")


def test_ant():
    print("[兵蚁滑行]")
    g = Game()
    load_board(g, ANT_BOARD)
    a = uid_at(g, (3, 0), "ant", 1)
    check(g._removal_ok(a), "这枚兵蚁可以被抬起")
    d = dests(g, a)
    check(sorted(d) == ANT_EXPECT, "兵蚁可达格与已知局面一致: %s" % (d,))


def test_win():
    print("[胜负判定]")
    g = Game()
    force_place(g, 0, "queen", (0, 0))
    force_place(g, 1, "queen", (5, 0))
    # 白后四周先填满 5 格
    ring = neighbors((0, 0))
    plan = [(1, "ant"), (0, "ant"), (1, "grasshopper"), (0, "ant"), (1, "beetle")]
    for (owner, kind), n in zip(plan, ring[:-1]):
        force_place(g, owner, kind, n)
    g.turn_no[0] = 5
    g.turn_no[1] = 5
    g.turn = 1
    last = ring[-1]
    # 黑方用最后一枚兵蚁封死白后
    uid = next(u for u in g.hand[1] if g.pieces[u][1] == "ant")
    g.apply(Move("place", uid, last))
    check(g.result == "win", "蜂后被围死应判胜，实际=%s" % g.result)
    check(g.winner == 1, "黑方获胜，实际=%s" % g.winner)


def test_save_load():
    print("[存读档往返]")
    g = Game(["ladybug"])
    seq = []
    for i in range(8):
        ms = g.legal_moves()
        if not ms:
            break
        # 优先蜂后
        ms.sort(key=lambda m: (0 if g.pieces[m.uid][1] == "queen" else 1, m.to))
        mv = ms[0]
        seq.append(mv)
        g.apply(mv)
    d = g.to_save()
    g2 = Game.from_save(d)
    check(len(g2.moves) == len(g.moves), "着数一致")
    check(g2.stacks == g.stacks, "棋盘一致")
    check(g2.turn == g.turn, "轮次一致")
    check(g2.queen_pos == g.queen_pos, "蜂后位置一致")


def test_notation():
    print("[记谱]")
    g = Game()
    uid = next(u for u in g.hand[0] if g.pieces[u][1] == "queen")
    rec = g.apply(Move("place", uid, (0, 0)))
    txt = move_text(g, rec)
    check("蜂后" in txt, "谱面含棋子名：" + txt)


# 用户报的那个局面：黑蜂后被自己的蚱蜢和蜘蛛夹在三角形的角上
SANDWICH_BOARD = {
    (0, 0): ["q1"], (1, 0): ["g1"], (0, 1): ["s1"], (0, 2): ["g0"],
    (1, 2): ["b0"], (2, 1): ["q0"], (0, 3): ["g0"],
}

# 用户第二张图：黑蜂后四周被占 5 格，只剩北面一个口子
SURROUND_BOARD = {
    (0, 0): ["q1"], (1, -1): ["b0"], (1, 0): ["b0"], (0, 1): ["a0"],
    (-1, 1): ["b1"], (-1, 0): ["s1"], (-2, 0): ["s1"], (2, -1): ["q0"],
    (2, 0): ["g1"], (-2, 2): ["g0"],
}


def test_official_rule():
    print("[官方规则：两侧同时被占才滑不过去]")
    g = Game()
    load_board(g, SANDWICH_BOARD)
    g.turn_no = {0: 8, 1: 8}
    g.turn = 1
    q = g.queen_pos[1]
    # 被自家棋子在角上夹住，但两个出口都只被一侧挡着 → 能挪出去
    moves = sorted(m.to for m in g.legal_moves() if m.uid == g.top(q))
    check(moves == [(-1, 1), (1, -1)], "被夹在角上的蜂后仍能往东北/西南走（实际=%s）" % (moves,))

    # 一巢规则仍然生效：中间那枚蜘蛛抬起来会断巢
    check(not g._removal_ok(g.top((0, 1))), "蜘蛛仍因断巢不能动")
    sp = [m for m in g.legal_moves() if m.kind == "move"
          and g.pieces[m.uid][1] == "spider"
          and m.frm == (0, 1)]
    check(sp == [], "断巢的蜘蛛确实没有走法")

    # 蚱蜢是跳的，不受窄门规则影响
    gh = sorted(m.to for m in g.legal_moves() if m.kind == "move"
                and g.pieces[m.uid][1] == "grasshopper")
    check(len(gh) == 2, "蚱蜢跳跃不受窄门规则影响：%s" % (gh,))

    # 存读档往返
    d = g.to_save()
    check(Game.from_save(d).to_save()["options"]["relaxed"] is True,
          "存档只记官方规则")

    # 被四面围困、只剩一个口子的蜂后：两侧被占满，照样出不去
    g3 = Game()
    load_board(g3, SURROUND_BOARD)
    g3.turn_no = {0: 8, 1: 8}
    g3.turn = 1
    q3 = g3.queen_pos[1]
    check(g3.pieces[g3.top(q3)][1] == "queen", "围困局面里那个子是蜂后")
    check(sorted(m.to for m in g3.legal_moves() if m.uid == g3.top(q3)) == [],
          "被围 5 面的蜂后一步也走不了")


def test_random_games():
    print("[随机对局稳定性]")
    import random
    random.seed(7)
    bad = 0
    for t in range(12):
        g = Game(random.choice([[], ["ladybug"], ["mosquito"], ["pillbug"],
                                ["ladybug", "mosquito", "pillbug"]]))
        for step in range(250):
            if g.result:
                break
            ms = g.legal_moves()
            if not ms:
                # 必须能走；若不能走则判定为僵局，跳过回合
                g.turn = 1 - g.turn
                continue
            mv = random.choice(ms)
            g.apply(mv)
            # 每次落子后蜂巢都应连通
            cells = set(g.stacks.keys())
            if not Game._connected(cells):
                bad += 1
                print("     断巢！", t, step)
                break
            for p, st in g.stacks.items():
                if not st:
                    bad += 1
                    print("     空叠！", p)
    check(bad == 0, "30 局随机对局中蜂巢始终连通")


def main():
    for fn in (test_setup, test_opening, test_own_colour_rule, test_queen_deadline,
               test_move_needs_queen, test_queen_move, test_freedom_to_move,
               test_one_hive, test_grasshopper, test_spider, test_beetle,
               test_ant, test_win, test_save_load, test_notation,
               test_official_rule, test_random_games):
        fn()
    print()
    if FAILS:
        print("失败 %d 项：" % len(FAILS))
        for f in FAILS:
            print("  -", f)
        return 1
    print("全部通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())




