# -*- coding: utf-8 -*-
"""联机自测：协议层（本机自连）+ 界面层（房主开房、客人裸会话加入）。

不依赖外网，全在 127.0.0.1 上跑。
"""
import os
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hive import net as netlib  # noqa: E402

FAILS = []


def check(c, m):
    print(("  ok    " if c else "  FAIL  ") + m)
    if not c:
        FAILS.append(m)


# ---------------------------------------------------------------- 协议层
print("[开房 / 连接 / 握手 / 走子]")
host = netlib.Host(0)
check(host.port > 0, "房主占到了端口 %d" % host.port)

box = {}


def accept_one():
    sess, addr = host.accept(timeout=8)
    box["sess"] = sess
    box["hello"] = netlib.wait_hello(sess) if sess else None


th = threading.Thread(target=accept_one, daemon=True)
th.start()

guest = netlib.connect("127.0.0.1", host.port)
check(guest.alive, "客人连上了房主")
guest.send(netlib.hello_msg("黑方客人", [], 0, 1))
th.join(10)
check(not th.is_alive(), "房主收到 hello")
host_sess = box.get("sess")
hello = box.get("hello")
check(host_sess is not None and host_sess.alive, "房主这边有会话了")
check(hello and hello.get("name") == "黑方客人", "hello 里的名字对上了")
check(hello and int(hello.get("proto", 0)) == netlib.PROTO, "协议版本对上了")

check(host_sess.send({"t": "start", "expansions": [], "first_player": 1,
                      "names": ["白方房主", "黑方客人"]}), "start 发出去了")
start = netlib.wait_start(guest, timeout=5)
check(start is not None and start.get("names")[1] == "黑方客人",
      "客人收到了开局设置（先手=%s）" % (start and start.get("first_player")))

check(host_sess.send({"t": "move", "n": 1,
                      "mv": {"kind": "place", "uid": 0, "to": [0, 0],
                             "frm": None, "aux": None},
                      "dg": 12345}), "move 发出去了")
got = []
end = time.time() + 5
while time.time() < end and not got:
    got = [m for m in guest.poll() if m.get("t") == "move"]
    time.sleep(0.01)
check(bool(got) and got[0].get("dg") == 12345, "客人收到了 move（含校验码）")

# 半包 / 粘包：把一帧拆成几次发，接收方要能拼回来
host2 = netlib.Host(0)
box2 = {}


def accept_three():
    s, _a = host2.accept(timeout=8)
    box2["sess"] = s


th2 = threading.Thread(target=accept_three, daemon=True)
th2.start()
g2raw = socket.create_connection(("127.0.0.1", host2.port), timeout=5)
th2.join(10)
s2 = box2.get("sess")
check(s2 is not None, "第二个房间也连上了")


def frame(obj):
    import json
    import struct
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack("!I", len(data)) + data


f = frame({"t": "move", "n": 2, "mv": {"kind": "move", "uid": 5, "to": [1, 0],
                                       "frm": [0, 0], "aux": None}, "dg": 777})
g2raw.sendall(f[:3])          # 先发半个长度头
time.sleep(0.05)
g2raw.sendall(f[3:7])         # 再发剩下的头 + 半个包
time.sleep(0.05)
g2raw.sendall(f[7:])
got2 = []
end = time.time() + 5
while time.time() < end and not got2:
    got2 = [m for m in s2.poll() if m.get("t") == "move"]
    time.sleep(0.01)
check(bool(got2) and got2[0].get("dg") == 777,
      "拆成三段发的一帧，接收方能拼回来")

print("[版本不一致 / 断线]")
host3 = netlib.Host(0)
box3 = {}


def accept_four():
    s, _a = host3.accept(timeout=8)
    box3["sess"] = s
    box3["hello"] = netlib.wait_hello(s, timeout=3)


th3 = threading.Thread(target=accept_four, daemon=True)
th3.start()
g3 = netlib.connect("127.0.0.1", host3.port)
g3.send({"t": "hello", "app": netlib.APP, "proto": netlib.PROTO + 99,
         "name": "老版本", "expansions": []})
th3.join(10)
check(box3.get("hello") is None, "版本不一样，房主拒绝握手")
check("版本" in (box3.get("sess").error if box3.get("sess") else ""),
      "拒绝原因写清楚了：%s" % (box3.get("sess").error if box3.get("sess") else ""))

g3.close("测试结束")
g2raw.close()
deadline = time.time() + 5
while time.time() < deadline and s2.alive:
    s2.poll()
    time.sleep(0.02)
check(not s2.alive, "对方关掉 socket 后，这边会收到「已断开」")
check(s2.error != "", "断开原因记下来了：%s" % s2.error)

for s in (host_sess, guest):
    try:
        s.close("收尾")
    except Exception:
        pass

# ---------------------------------------------------------------- 界面层
print("[界面：房主开房 → 客人裸会话加入 → 双方同步走子]")
import tkinter as tk  # noqa: E402
from hive import ui as uimod  # noqa: E402
from hive.rules import Game  # noqa: E402

uimod.enable_dpi()
popups = []
uimod.messagebox.showerror = lambda t, m, **k: popups.append(("err", t, m))
uimod.messagebox.showwarning = lambda t, m, **k: popups.append(("warn", t, m))
uimod.messagebox.showinfo = lambda t, m, **k: popups.append(("info", t, m))
uimod.messagebox.askyesno = lambda *a, **k: True

root = tk.Tk()
app = uimod.HiveApp(root)
root.update()


def pump(sec=1.2):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


check(app.net_host("白方房主", [], 0, 0), "房主开房成功")
pump(0.3)
check(app.net is None, "还没人进来时是「等对手」状态")
check(app.game.stacks == {}, "等待期间棋盘是空的")

port = app.net_room.port if app.net_room else 0
peer = netlib.connect("127.0.0.1", port)
peer.send(netlib.hello_msg("黑方客人", [], 0, 1))
start = netlib.wait_start(peer, timeout=5)
check(start is not None and start["names"] == ["白方房主", "黑方客人"],
      "房主把开局信息发给了客人：%s" % (start and start.get("names")))
pump(0.6)
check(app.net is not None and app.net.alive, "房主这边进入联机状态")
check(app.net_peer == "黑方客人", "房主看到对手名字")
check(app.game.names == ["白方房主", "黑方客人"], "棋盘上的名字换成了双方")
check(app.net_side == 0, "房主执白（先手）")
check("联机中" in app.status.cget("text"), "状态栏显示联机中")

# 房主走一步 → 客人应该收到 move
ms = app.game.legal_moves()
mv = [m for m in ms if m.kind == "place"][0]
app._play(mv)
got = []
end = time.time() + 5
while time.time() < end and not got:
    got = [m for m in peer.poll() if m.get("t") == "move"]
    time.sleep(0.02)
check(bool(got), "房主的着法同步到了客人那边")
dg_ok = bool(got) and got[0].get("dg") == netlib.position_digest(app.game)
check(dg_ok, "同步的校验码和房主盘面一致")

# 客人按同一套规则走一步（用裸会话 + 本地 Game 复现），房主要自动跟上
g2 = Game([], 0, names=["白方房主", "黑方客人"])
g2.apply(mv)
m2 = [m for m in g2.legal_moves() if m.kind == "place"][0]
peer.send({"t": "move", "n": 2,
           "mv": {"kind": m2.kind, "uid": m2.uid, "to": list(m2.to),
                  "frm": None, "aux": None},
           "dg": None})
pump(0.6)
check(len(app.history) == 2, "客人走完房主自动跟上（%d 步）" % len(app.history))
check(app.game.turn == 0, "又轮到房主")

# 不是自己回合：不能动棋子
check(not app.my_turn() or app.game.turn == app.net_side, "只能在自己回合动")
app.game.turn = 1
root.update()
check(app.my_turn() is False, "轮到对方时房主不能动")
app.game.turn = 0
root.update()

# 悔棋 / 试下被挡
n_before = len(app.history)
app.undo()
root.update()
check(len(app.history) == n_before, "联机时悔棋被挡（%d 步没变）" % len(app.history))
check("不能" in app.status.cget("text") or "联机" in app.status.cget("text"),
      "给了「联机不能用」的提示")

# 房主停一手 → 客人收到 pass，双方一起换手
turn_before = app.game.turn
app.pass_turn()
root.update()
check(app.game.turn == 1 - turn_before, "房主停一手，这边换手了")
got = []
end = time.time() + 5
while time.time() < end and not got:
    got = [m for m in peer.poll() if m.get("t") == "pass"]
    time.sleep(0.02)
check(bool(got), "停一手也同步给了客人")

# 客人断开 → 房主提示并回到单机状态
peer.close("打完收工")
pump(1.0)
check(app.net is None, "对方断线后联机状态清干净了")
check(any(k == "warn" for k, *_ in popups), "断线给了提示")
check(app.status.cget("text").strip() != "", "状态栏有说明：%s"
      % app.status.cget("text").strip()[:24])

# ---------------------------------------------------------------- 界面：客人
print("[界面：加入别人的房间（客人这一侧）]")
app.net_close("测试收尾", notify=False)
fake = netlib.Host(0)
fb = {}


def fake_host():
    s, _a = fake.accept(timeout=8)
    fb["sess"] = s
    fb["hello"] = netlib.wait_hello(s) if s else None
    if fb["hello"]:
        s.send({"t": "start", "expansions": [], "first_player": 1,
                "names": ["房主甲", "小客"]})


th = threading.Thread(target=fake_host, daemon=True)
th.start()
check(app.net_join("127.0.0.1", fake.port, "小客"), "客人发起加入")
pump(1.2)
check(app.net is not None and app.net.alive, "客人这侧进入联机状态")
check(app.net_side == 1, "客人执黑")
check(app.game.names == ["房主甲", "小客"], "客人这边的名字来自房主")
check(app.game.first_player == 1, "先手也是房主定的（黑方先）")
check(app.my_turn() is True, "黑方先，所以客人可以先动")

# 客人走一步 → 房主收到；房主再回一手 → 客人自动跟上
mv_b = [m for m in app.game.legal_moves() if m.kind == "place"][0]
app._play(mv_b)
got = []
end = time.time() + 5
while time.time() < end and not got:
    got = [m for m in fb["sess"].poll() if m.get("t") == "move"]
    time.sleep(0.02)
check(bool(got), "客人的着法同步到了房主那边")
check(bool(got) and got[0].get("dg") == netlib.position_digest(app.game),
      "校验码对得上")

gm = Game([], 1, names=["房主甲", "小客"])
gm.apply(mv_b)
mv_w = [m for m in gm.legal_moves() if m.kind == "place"][0]
fb["sess"].send({"t": "move", "n": 2,
                 "mv": {"kind": mv_w.kind, "uid": mv_w.uid,
                        "to": list(mv_w.to), "frm": None, "aux": None},
                 "dg": None})
pump(1.2)
check(len(app.history) == 2, "房主的应手在客人这边也落了（%d 步）"
      % len(app.history))
check(app.game.turn == 1, "又轮到客人（黑方）")
app.net_close("测试收尾", notify=False)

root.destroy()

print()
if FAILS:
    print("失败 %d 项" % len(FAILS))
    for f_ in FAILS:
        print(" -", f_)
    sys.exit(1)
print("联机自测全部通过 ✔")
