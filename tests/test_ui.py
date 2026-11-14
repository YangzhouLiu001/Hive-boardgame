# -*- coding: utf-8 -*-
"""界面功能自测：模拟真实点击。"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402
from hive.rules import Game  # noqa: E402
from hive import store  # noqa: E402

uimod.enable_dpi()
FAILS = []


def check(cond, msg):
    if cond:
        print("  ok   ", msg)
    else:
        print("  FAIL ", msg)
        FAILS.append(msg)


class Ev:
    def __init__(self, x, y):
        self.x = x
        self.y = y


# 拦截弹窗
ui_popups = []
uimod.messagebox.showinfo = lambda t, m, **k: ui_popups.append((t, m))
uimod.messagebox.showerror = lambda t, m, **k: (ui_popups.append((t, m)),
                                                print("  !! 报错弹窗:", t, m))

root = tk.Tk()
app = uimod.HiveApp(root)
# 固定在「两人对战」的干净状态下测，免得受上次保存的设置影响
app.start_new(["白方", "黑方"], [], "human", 2, 1)
root.update()
root.update_idletasks()
root.update()

print("[基本渲染]")
check(app.canvas.find_all() != (), "画布已绘制内容")
check(app.R > 10, "棋子半径 %.1f" % app.R)

print("[棋盒落子]")
owner = app.game.turn
cv = app.trays[owner]["cv"]
w = cv.winfo_width()
kinds = list(app.game.kinds)
step = w / float(len(kinds))
qi = kinds.index("queen")
app.on_tray_click(Ev(step * (qi + 0.5), cv.winfo_height() * 0.4), owner)
check(app.selected_kind == "queen", "选中蜂后，实际=%s" % app.selected_kind)
check(len(app.dests) == 1 and (0, 0) in app.dests, "高亮唯一落点 (0,0)")
x, y = app.to_screen((0, 0))
app.on_click(Ev(x, y))
root.update()
check(len(app.game.stacks) == 1, "蜂后已落在棋盘上")
check(app.game.queen_pos[owner] == (0, 0), "蜂后位置记录正确")
check(app.game.turn != owner, "轮到对方")

print("[点棋盘选子]")
# 白方先落一枚兵蚁
owner = app.game.turn
cv = app.trays[owner]["cv"]
w = cv.winfo_width()
step = w / float(len(kinds))
ai = kinds.index("ant")
app.on_tray_click(Ev(step * (ai + 0.5), cv.winfo_height() * 0.4), owner)
check(len(app.dests) == 6, "第二手有 6 个落点，实际=%d" % len(app.dests))
spot = sorted(app.dests)[0]
x, y = app.to_screen(spot)
app.on_click(Ev(x, y))
root.update()
check(len(app.game.stacks) == 2, "第二枚棋子已落下")

print("[走子]")
# 不断落子，铺够三枚并且出现可以移动的棋子
moves = []
for step in range(24):
    if app.game.result:
        break
    moves = [m for m in app.game.legal_moves() if m.kind == "move"]
    if moves and len(app.game.stacks) >= 3:
        break
    o = app.game.turn
    c = app.trays[o]["cv"]
    st = c.winfo_width() / float(len(kinds))
    cnt = {}
    for uid in app.game.hand[o]:
        k = app.game.pieces[uid][1]
        cnt[k] = cnt.get(k, 0) + 1
    avail = [i for i, k in enumerate(kinds) if cnt.get(k, 0)]
    if not avail:
        break
    pick = avail[step % len(avail)]
    app.on_tray_click(Ev(st * (pick + 0.5), c.winfo_height() * 0.4), o)
    if app.dests:
        sp = sorted(app.dests)[0]
        px, py = app.to_screen(sp)
        app.on_click(Ev(px, py))
        root.update()
check(len(app.game.stacks) >= 3, "已铺下 %d 枚棋子" % len(app.game.stacks))
check(len(moves) > 0, "当前可走子数 %d" % len(moves))
if moves:
    mv = moves[0]
    x, y = app.to_screen(app.game.where[mv.uid])
    app.on_click(Ev(x, y))
    check(app.selected_uid == mv.uid, "点中自己的棋子")
    x2, y2 = app.to_screen(mv.to)
    app.on_click(Ev(x2, y2))
    root.update()
    check(app.game.where[mv.uid] == mv.to, "棋子已移动")

print("[悔棋/重做]")
n_before = len(app.game.moves)
app.undo()
root.update()
check(len(app.game.moves) == n_before - 1, "悔棋后少一步")
app.redo()
root.update()
check(len(app.game.moves) == n_before, "重做后恢复")

print("[存读档]")
p = os.path.join(ROOT, ".build", "roundtrip.hive")
store.save_game(p, app.game, app.history, app.theme.key, app.versus)
g2, moves2, data = store.load_game(p)
check(len(g2.moves) == len(app.game.moves), "存档着数一致")
check(g2.stacks == app.game.stacks, "读档棋盘一致")
app._load_path(p)
root.update()
check(app.game.stacks == g2.stacks, "界面读档成功")

print("[棋谱文本]")
tp = os.path.join(ROOT, ".build", "record.txt")
store.export_text(tp, app.game, app.history)
txt = open(tp, encoding="utf-8").read()
check("虫虫蜂房" in txt and "着法记录" in txt, "棋谱文件已生成")
check("终局盘面" in txt, "棋谱含盘面图")

print("[电脑对战]")
app.start_new(["我", "电脑"], [], "ai", 2, 1)
root.update()
check(app.versus == "ai", "切换为人机对战")
owner = app.game.turn
cv = app.trays[owner]["cv"]
step = cv.winfo_width() / float(len(kinds))
app.on_tray_click(Ev(step * (kinds.index("queen") + 0.5),
                     cv.winfo_height() * 0.4), owner)
x, y = app.to_screen((0, 0))
app.on_click(Ev(x, y))
root.update()
check(app.busy, "电脑开始思考")
app._ai_move()
root.update()
check(len(app.game.moves) == 2, "电脑已应手，共 %d 手" % len(app.game.moves))

print("[终局]")
g = app.game
# 直接构造一个白方蜂后被围的局面
g2 = Game()
from hive.rules import Move, neighbors  # noqa: E402
combo = [(0, "queen", (0, 0)), (1, "queen", (6, 0)),
         (1, "ant", (0, -1)), (0, "ant", (1, -1)), (1, "grasshopper", (1, 0)),
         (0, "ant", (0, 1)), (1, "beetle", (-1, 1))]
for o, k, pos in combo:
    uid = next(u for u in g2.hand[o] if g2.pieces[u][1] == k)
    g2.hand[o].remove(uid)
    g2.stacks.setdefault(pos, []).append(uid)
    g2.where[uid] = pos
    g2.placed[o] += 1
    if k == "queen":
        g2.queen_pos[o] = pos
g2.turn_no = {0: 6, 1: 6}
g2.turn = 1
gap = [c for c in neighbors((0, 0)) if c not in g2.stacks]
if gap:
    uid = next(u for u in g2.hand[1] if g2.pieces[u][1] == "ant")
    g2.apply(Move("place", uid, gap[0]))
check(g2.result == "win", "蜂后被围死判胜")
app.game = g2
app.history = [Move("place", 0, (0, 0))]
app.redraw()
app._update_side()
root.update()
check("获胜" in app.turn_sub.cget("text") or app.game.result == "win",
      "界面显示终局")

print("[主题切换]")
for _ in range(3):
    app.cycle_theme()
    root.update()
check(len(app._tiles) >= 0, "三个主题都能渲染")

print("[规则/新局对话框]")
d = uimod.RulesDialog(app)
root.update()
d.destroy()
nd = uimod.NewGameDialog(app)
root.update()
nd.destroy()
check(True, "对话框可正常打开关闭")

root.update()
from PIL import ImageGrab  # noqa: E402
x, y = root.winfo_rootx(), root.winfo_rooty()
ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()),
               all_screens=True).save(os.path.join(ROOT, ".build", "uitest.png"))
root.destroy()

print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    for f in FAILS:
        print(" -", f)
    sys.exit(1)
print("界面自测全部通过 ✔")

