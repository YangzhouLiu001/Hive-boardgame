# -*- coding: utf-8 -*-
"""局域网联机：TCP + 长度前缀的 JSON 消息。

只有两件事：把一条 TCP 连接包成带后台收发的「会话」，以及两边商量的
几句协议。**不需要服务器** —— 房主开房（bind 一个端口），客人直接连过来。

消息（都是 dict，"t" 是类型）：
    hello   客人→房主：名字、协议版本、扩展棋子
    start   房主→客人：最终采用的扩展 / 先手 / 双方名字
    move    走了一步：{n, mv, dg}
    pass    停一手：{n, dg}
    resign  认输
    bye     主动离开
    error   出错了（附 why）

dg 是走完这一步之后盘面的校验码（见 position_digest）。两边的棋子 uid
是同一套发牌顺序生成的，所以校验码可以直接比 —— 一比对不上就说明两边
下岔了，宁可停下也不要把棋谱写坏。
"""

from __future__ import annotations

import json
import queue
import socket
import struct
import threading
import time
import zlib

APP = "虫虫蜂房"
PROTO = 1
MAX_MSG = 1 << 20          # 单条消息上限 1MB，防止对方乱发把内存吃光


class NetError(Exception):
    pass


# ------------------------------------------------------------------ 校验码
def position_digest(g) -> int:
    """盘面校验码：双方各自算，必须一致（不依赖 hash() 的随机化）。"""
    items = []
    for p, st in g.stacks.items():
        items.append((p, tuple((g.pieces[u][0], g.pieces[u][1]) for u in st)))
    items.sort()
    s = repr((tuple(items), g.turn, tuple(sorted(g.hand[0])),
              tuple(sorted(g.hand[1]))))
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


# ------------------------------------------------------------------ 会话
class NetSession:
    """一条联机连接。收发都在后台线程，界面只从 inbox 取消息。"""

    def __init__(self, sock, peer=""):
        self.sock = sock
        self.peer = peer
        self.alive = True
        self.error = ""
        self.inbox: "queue.Queue[dict]" = queue.Queue()
        self._buf = b""
        self._send_lock = threading.Lock()
        try:
            self.sock.settimeout(None)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._rx = threading.Thread(target=self._recv_loop, daemon=True)
        self._rx.start()

    # -------------------------------------------------------------- 发送
    def send(self, obj: dict) -> bool:
        if not self.alive:
            return False
        try:
            data = json.dumps(obj, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            return False
        if len(data) > MAX_MSG:
            self._die("消息过大，没有发出去")
            return False
        frame = struct.pack("!I", len(data)) + data
        try:
            with self._send_lock:
                self.sock.sendall(frame)
            return True
        except OSError as e:
            self._die("发送失败：%s" % e)
            return False

    # -------------------------------------------------------------- 接收
    def _recv_loop(self):
        try:
            while self.alive:
                chunk = self.sock.recv(65536)
                if not chunk:
                    self._die("对方断开了连接")
                    return
                self._buf += chunk
                while len(self._buf) >= 4:
                    n = struct.unpack("!I", self._buf[:4])[0]
                    if n == 0 or n > MAX_MSG:
                        self._die("对方发来的消息长度不对")
                        return
                    if len(self._buf) < 4 + n:
                        break                       # 半包，等下一块
                    body = self._buf[4:4 + n]
                    self._buf = self._buf[4 + n:]
                    try:
                        msg = json.loads(body.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        self._die("对方发来的消息看不懂")
                        return
                    if isinstance(msg, dict):
                        self.inbox.put(msg)
        except OSError as e:
            self._die("连接中断：%s" % e)

    def _die(self, why: str):
        if not self.alive:
            return
        self.alive = False
        self.error = why
        self.inbox.put({"_closed": True})
        try:
            self.sock.close()
        except OSError:
            pass

    # -------------------------------------------------------------- 对外
    def poll(self) -> list:
        """把收到的消息全取出来（不阻塞）。"""
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self, why="主动离开"):
        if not self.alive:
            return
        self.send({"t": "bye"})
        self._die(why)

    def __repr__(self):
        return "NetSession(%s, %s)" % (self.peer or "?", "alive" if self.alive else "closed")


# ------------------------------------------------------------------ 开房 / 连接
def local_ip() -> str:
    """本机在局域网里的地址（只查路由表，不真的发数据）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class Host:
    """房主：占一个端口等客人进来。"""

    def __init__(self, port: int = 0):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.srv.bind(("0.0.0.0", int(port)))
            self.srv.listen(1)
        except OSError as e:
            try:
                self.srv.close()
            except OSError:
                pass
            raise NetError("端口 %s 用不了（%s）。换一个端口试试" % (port, e))
        self.port = self.srv.getsockname()[1]
        self.error = ""
        self._closed = False

    def accept(self, timeout=None):
        """等一个客人。返回 (会话, 对方 IP)；出错/被取消返回 (None, None)。"""
        try:
            if timeout:
                self.srv.settimeout(timeout)
            s, addr = self.srv.accept()
        except OSError as e:
            self.error = "已取消" if self._closed else str(e)
            return None, None
        finally:
            self.close()
        return NetSession(s, addr[0]), addr[0]

    def close(self):
        self._closed = True
        try:
            self.srv.close()
        except OSError:
            pass


def connect(ip: str, port: int, timeout: float = 6.0) -> NetSession:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.connect((str(ip).strip(), int(port)))
    except (OSError, ValueError) as e:
        try:
            s.close()
        except OSError:
            pass
        raise NetError("连不上 %s:%s（%s）" % (ip, port, e))
    return NetSession(s, str(ip))


# ------------------------------------------------------------------ 握手
def hello_msg(name: str, expansions, first_player: int, side: int) -> dict:
    return {"t": "hello", "app": APP, "proto": PROTO,
            "name": str(name or "对手"),
            "expansions": list(expansions or []),
            "first_player": int(first_player) % 2,
            "side": int(side) % 2}


def _wait_for(sess: NetSession, kind: str, timeout: float = 8.0):
    """在后台线程里等某类消息；超时返回 None。"""
    end = time.time() + timeout
    while time.time() < end and sess.alive:
        for msg in sess.poll():
            if msg.get("t") == kind:
                return msg
            if msg.get("t") == "error":
                sess.error = str(msg.get("why") or "对方报错")
                return None
            if msg.get("_closed"):
                return None
        time.sleep(0.02)
    return None


def wait_hello(sess: NetSession, timeout: float = 8.0):
    """房主等客人的 hello，顺便查版本。"""
    msg = _wait_for(sess, "hello", timeout)
    if msg is None:
        return None
    if msg.get("app") != APP:
        sess.error = "连上来的不是虫虫蜂房"
        return None
    try:
        proto = int(msg.get("proto", 0))
    except (TypeError, ValueError):
        proto = 0
    if proto != PROTO:
        sess.error = "两边版本不一样（对方协议 %s，本机 %s），用同一个包再试" % (
            msg.get("proto"), PROTO)
        return None
    return msg


def wait_start(sess: NetSession, timeout: float = 8.0):
    """客人等房主的 start。"""
    return _wait_for(sess, "start", timeout)
