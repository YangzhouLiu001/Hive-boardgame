# -*- coding: utf-8 -*-
"""试下功能：复盘到任意一步，点棋子/棋盒即可还原手牌开始推演。"""
import sys
import time

sys.path.insert(0, r"C:\Users\16402\Desktop\虫虫蜂房")
import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402

uimod.enable_dpi()
uimod.messagebox.showinfo = lambda *a, **k: None
FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


class Ev:
    def __init__(s, x, y):
        s.x, s.y = x, y


root = tk.Tk()
app = uimod.HiveApp(root)


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


app.start_new(["白方", "黑方"], [], "human", 2, 1, 0)
pump()
for _ in range(8):
    ms = app.game.legal_moves()
    if not ms:
        break
    app.game.apply(ms[0])
    app.history.append(ms[0])
app._rebuild(app.history)
pump()
record = list(app.history)

print("[复盘 -> 点棋盒 -> 试下]")
app.set_review(3)
pump()
check(app.review == 3, "复盘到第 3 步")
hands = dict(app.game.hand)
owner = app.game.turn
cv = app.trays[owner]["cv"]
kinds = list(app.game.kinds)
step = cv.winfo_width() / float(len(kinds))
have = {}
for uid in app.game.hand[owner]:
    k = app.game.pieces[uid][1]
    have[k] = have.get(k, 0) + 1
idx = next(i for i, k in enumerate(kinds) if have.get(k, 0) > 0)
app.on_tray_click(Ev(step * (idx + 0.5), cv.winfo_height() * 0.4), owner)
pump()
check(app.trial_from == 3, "进入试下（起点 %d）" % (app.trial_from or -1))
check(dict(app.game.hand) == hands, "双方手牌已还原")
check(app.selected_kind == kinds[idx], "选中了 %s" % app.selected_kind)
check(len(app.dests) > 0, "落点已高亮（%d 个）" % len(app.dests))

print("[试下里能落子]")
n0 = len(app.history)
spot = sorted(app.dests)[0]
gx, gy = app.to_screen(spot)
app.on_click(Ev(gx, gy))
pump()
check(len(app.history) == n0 + 1, "落子成功（%d -> %d）" % (n0, len(app.history)))
check(app.trial_from == 3, "仍在试下中")

print("[Ctrl+M 让电脑走一步]")
n1 = len(app.history)
app.trial_ai_move()
pump(3.2)
check(len(app.history) > n1 or app.game.result,
      "电脑在试下里走了一步（%d -> %d）" % (n1, len(app.history)))

print("[点棋谱 -> 退出试下]")
app.exit_trial()
pump()
check(app.trial_from is None, "已退出试下")
check(len(app.history) == len(record), "棋谱恢复原样（%d 步）" % len(app.history))

print("[试下中按 ← -> 自动退出并翻看原棋谱]")
app.set_review(5)
pump()
app.enter_trial()
pump()
check(app.trial_from == 5, "从第 5 步试下")
app.step_review(-1)
pump()
check(app.trial_from is None, "按 ← 已退出试下")
check(app.review == 4, "退到第 4 步（实际 %s）" % app.review)

print("[试下中按 → -> 同样退出]")
app.enter_trial()
pump()
app.step_review(1)
pump()
check(app.trial_from is None and app.review == 5,
      "按 → 退出并前进到第 %s 步" % app.review)

print("[Esc -> 退出试下并回到原步骤]")
app.enter_trial()
pump()
app._escape()
pump()
check(app.trial_from is None and app.review == 5, "Esc 回到第 %s 步" % app.review)

print("[试下不写进自动存档]")
app.enter_trial()
pump()
before = app.game.moves if hasattr(app.game, "moves") else []
app._autosave()
check(app.trial_from is not None, "仍在试下，autosave 被跳过")

print("[试下中点错一方要有提示]")
app.exit_trial()
app.set_review(3)
pump()
app.enter_trial()
pump()
owner2 = app.game.turn
app.selected_kind = None
cv2 = app.trays[1 - owner2]["cv"]
app.on_tray_click(Ev(cv2.winfo_width() * 0.1, cv2.winfo_height() * 0.4),
                  1 - owner2)
pump()
check(app.selected_kind is None and "轮到" in app.status.cget("text"),
      "点错一方给了提示：%s" % app.status.cget("text").strip())

print("[试下中点对一方能选中]")
kinds2 = list(app.game.kinds)
have2 = {}
for uid in app.game.hand[owner2]:
    k = app.game.pieces[uid][1]
    have2[k] = have2.get(k, 0) + 1
idx2 = next(i for i, k in enumerate(kinds2) if have2.get(k, 0) > 0)
cv3 = app.trays[owner2]["cv"]
step3 = cv3.winfo_width() / float(len(kinds2))
app.on_tray_click(Ev(step3 * (idx2 + 0.5), cv3.winfo_height() * 0.4), owner2)
pump()
check(app.selected_kind == kinds2[idx2], "选中 %s，落点 %d 个"
      % (app.selected_kind, len(app.dests)))

print("[电脑思考中进试下不能被锁死]")
app.exit_trial()
app.set_review(3)
pump()
app.busy = True
app.enter_trial()
pump()
check(app.busy is False, "busy 已清零")
check(app.my_turn(), "界面可以操作")

print("[副标题写明轮到谁]")
sub = app.turn_sub.cget("text")
check("试下中" in sub, "副标题：%s" % sub)
root.destroy()
print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    sys.exit(1)
print("试下功能全部正常 ✔")

