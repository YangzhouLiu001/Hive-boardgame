# -*- coding: utf-8 -*-
"""虫虫蜂房 —— 图形界面（tkinter + Pillow 贴图）。"""

from __future__ import annotations

import ctypes
import math
import os
import queue
import random
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, font as tkfont, messagebox

from PIL import ImageTk

from . import ai as ailib
from . import art, net as netlib, store
from .rules import (DIRS, KIND_DESC, KIND_NAMES, Game, Move, move_text, neighbors)

SQ3 = math.sqrt(3.0)
BASE_R = 46
MIN_R = 20


def _is_light(c):
    if isinstance(c, tuple):
        r, g, b = c[:3]
    else:
        c = c.lstrip("#")
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 140


def enable_dpi():
    """让窗口按真实像素渲染，避免系统拉伸导致画面发虚。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def work_area():
    """任务栏之外的可用桌面区域（物理像素）。"""
    try:
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                      ctypes.byref(r), 0):
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------- 主程序
class HiveApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.s = self._scale()
        self.settings = store.load_settings()
        self.theme = art.THEME_BY_KEY.get(self.settings.get("theme", "mahjong"),
                                         art.THEMES[0])
        self.fam = self._pick_font()

        self.versus = self.settings.get("versus", "human")
        self.ai_level = int(self.settings.get("ai_level", 2))
        self.ai_side = 1

        self.R = self.px(BASE_R)
        self.origin = (0, 0)
        self._bg = None
        self._bg_size = None
        self._tiles = {}
        self._tray = {}
        self._dots = {}
        self._photos = {}

        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hover = None
        self.hint_mv = None
        self.busy = False
        self._tray_ready = False
        self.history: list = []
        self.future: list = []
        self.review = None          # None=实时；数字=正在复盘到第几步
        self.trial_from = None      # 试下的起点（棋谱第几步）；None=不在试下
        self._ai_thread = None      # 正在跑的思考线程
        self._beat = time.time()    # 心跳，用来发现界面卡死
        self._last_action = "启动"
        self.record = None          # 试下期间保存的原始棋谱
        self.carry_uid = None       # 鼠妇正在搬的那枚棋子
        self.carryable = {}         # 鼠妇能搬的棋子 uid -> 位置
        self.carry_dests = {}       # 搬运的落点
        self.path_hint = None       # 蜘蛛三步路线预览

        # 联机对战：self.net 是 hive.net.NetSession；None = 单机
        self.net = None
        self.net_side = 0           # 我是哪一方（0=白方 房主 / 1=黑方 客人）
        self.net_peer = ""          # 对手名字
        self.net_room = None        # 正在等人加入的 Host
        self._net_events: "queue.Queue[tuple]" = queue.Queue()
        self._net_waiting = ""      # 正在开房/连接的提示语

        self.game = Game(names=self._names_from_settings())
        self._apply_chrome()
        self._build_window()
        self._bind_keys()
        self.redraw()
        self._update_side()
        self.root.after(500, self._heartbeat)
        self.root.after(900, self._watchdog)
        self.root.after(120, self._net_tick)
        # 从 棋谱\ 里学开局（棋谱比库新就重建），放在启动后跑，不挡界面
        self.root.after(4000, self._learn_book)

    def _learn_book(self):
        """开局库重建放后台线程，绝不能挡住界面。"""
        def work():
            t0 = time.time()
            try:
                ailib.booklib.ensure_book()
                self._ai_log("开局库检查完成 %.2fs" % (time.time() - t0))
            except Exception:
                self._ai_log("开局库失败：\n%s" % traceback.format_exc())
        threading.Thread(target=work, daemon=True).start()

    def _apply_chrome(self):
        ch = self.theme.chrome
        self.col_bar = ch["bar"]
        self.col_bar_ink = ch["bar_ink"]
        self.col_bar_hover = ch["bar_hover"]
        self.col_panel = ch["panel"]
        self.col_text = ch["panel_ink"]
        self.col_dim = ch["panel_dim"]
        self.col_card = ch["card"]
        self.col_line = ch["line"]
        self.col_w_ink = ch["w_ink"]
        self.col_b_ink = ch["b_ink"]
        self.light_ui = _is_light(ch["panel"])

    # ----------------------------------------------------------------- 基础
    def px(self, v):
        return int(round(v * self.s))

    def _scale(self):
        try:
            dpi = self.root.winfo_fpixels("1i")
        except Exception:
            dpi = 96.0
        return max(1.0, min(3.0, dpi / 96.0))

    def _pick_font(self):
        fams = set(tkfont.families(self.root))
        for cand in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑",
                     "Segoe UI", "Arial"):
            if cand in fams:
                return cand
        return "TkDefaultFont"

    def _names_from_settings(self):
        n = self.settings.get("names") or ["白方", "黑方"]
        return [n[0] or "白方", n[1] or "黑方"]

    def f(self, size, bold=False):
        return (self.fam, size, "bold" if bold else "normal")

    # ----------------------------------------------------------------- 窗口
    def _build_window(self):
        r = self.root
        r.title("虫虫蜂房 · Hive")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        wa = work_area()
        if wa:
            wx, wy, ww, wh = wa
        else:
            wx, wy, ww, wh = 0, 0, sw, sh - self.px(46)
        title_h = self.px(34)
        cw = min(int(ww * 0.94), 2400)
        ch = min(int(wh * 0.94) - title_h, 1500)
        geo = self.settings.get("geometry")
        if not geo or not self._geo_ok(geo, wx, wy, ww, wh):
            geo = "%dx%d+%d+%d" % (cw, ch,
                                   wx + max(0, (ww - cw) // 2),
                                   wy + max(0, (wh - ch - title_h) // 2))
        r.geometry(geo)
        r.minsize(self.px(900), self.px(620))
        r.configure(bg=self.theme.bg2)
        try:
            r.iconbitmap(self._ensure_ico())
        except Exception:
            pass

        bar = tk.Frame(r, bg=self.col_bar, height=self.px(54))
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        self.topbar = bar

        tk.Label(bar, text="虫虫蜂房", bg=self.col_bar, fg=self.col_bar_ink,
                 font=self.f(15, True)).pack(side="left", padx=(self.px(18), 0))
        tk.Label(bar, text="HIVE", bg=self.col_bar, fg=self.col_dim,
                 font=self.f(8, True)).pack(side="left", padx=(self.px(6), 0),
                                            pady=(self.px(6), 0))

        btns = tk.Frame(bar, bg=self.col_bar)
        btns.pack(side="right", padx=self.px(14))
        # 按钮从右往左排：元组里越靠前，界面上越靠右。
        # 最右边是「规则」，紧挨着「配色」；「停一手」是个下拉菜单，
        # 里面放「停一手」和「认输」。
        for text, cmd in (("规则", self.show_rules),
                          ("配色", self.cycle_theme),
                          ("__more__", None),
                          ("读档", self.load_dialog),
                          ("存档", self.save_dialog),
                          ("棋谱", self.export_dialog),
                          ("悔棋", self.undo),
                          ("新局", self.new_game_dialog),
                          ("联机", self.net_dialog)):
            if text == "__more__":
                mb = tk.Menubutton(
                    btns, text="停一手 \u25be", bg=self.col_bar,
                    fg=self.col_bar_ink, activebackground=self.col_card,
                    activeforeground=self.col_text, relief="flat", bd=0,
                    font=self.f(10), padx=self.px(8), pady=self.px(2),
                    highlightthickness=0)
                menu = tk.Menu(mb, tearoff=0)
                menu.add_command(label="停一手（交给对方）",
                                 command=self.pass_turn)
                menu.add_separator()
                menu.add_command(label="认输", command=self.resign)
                mb.configure(menu=menu)
                mb.pack(side="right", padx=self.px(2))
                continue
            self._button(btns, text, cmd).pack(side="right", padx=self.px(2))

        body = tk.Frame(r, bg=self.theme.bg2)
        self.status = tk.Label(r, text="", bg=self.col_bar, fg=self.col_bar_ink,
                               anchor="w", font=self.f(9), padx=self.px(16),
                               height=1, bd=0)
        self.status.pack(side="bottom", fill="x")
        body.pack(side="top", fill="both", expand=True)
        self.body = body

        self.canvas = tk.Canvas(body, bg=self._hexc(self.theme.bg2), highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", lambda e: self.clear_selection())
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(None))

        self.side_w = self.px(340)
        side = tk.Frame(body, bg=self.col_dark, width=self.side_w)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        self._build_side(side)

    @property
    def col_dark(self):
        return self.col_panel

    def _geo_ok(self, geo, wx, wy, ww, wh):
        try:
            parts = geo.replace("x", "+").split("+")
            w, h = int(parts[0]), int(parts[1])
            x = int(parts[2]) if len(parts) > 2 else 0
            y = int(parts[3]) if len(parts) > 3 else 0
        except Exception:
            return False
        return (w <= ww and h <= wh - self.px(30) and
                wx <= x <= wx + ww - self.px(120) and
                wy <= y <= wy + wh - self.px(120))

    def _build_side(self, side):
        # 回合卡
        card = tk.Frame(side, bg=self.col_card,
                        highlightbackground=self.col_line, highlightthickness=1)
        card.pack(fill="x", pady=(self.px(14), self.px(10)), padx=self.px(14))
        self.turn_lab = tk.Label(card, text="", bg=self.col_card, fg=self.col_text,
                                 font=self.f(13, True), anchor="w",
                                 padx=self.px(14))
        self.turn_lab.pack(fill="x", pady=(self.px(10), 0))
        self.turn_sub = tk.Label(card, text="", bg=self.col_card, fg=self.col_dim,
                                 font=self.f(9), anchor="w", padx=self.px(14),
                                 justify="left", wraplength=self.px(285))
        self.turn_sub.pack(fill="x", pady=(self.px(3), self.px(10)))

        # 双方棋盒
        self.trays = {}
        for owner in (1, 0):
            head = tk.Frame(side, bg=self.col_dark)
            head.pack(fill="x", padx=self.px(16), pady=(self.px(6), 0))
            lab = tk.Label(head, text="", bg=self.col_dark, fg=self.col_dim,
                           font=self.f(9, True), anchor="w")
            lab.pack(side="left")
            self.trays[owner] = {"head": lab}
            cv = tk.Canvas(side, bg=self.col_dark, height=self.px(72),
                           highlightthickness=0, bd=0)
            cv.pack(fill="x", padx=self.px(10), pady=(self.px(2), self.px(2)))
            cv.bind("<Button-1>", lambda e, o=owner: self.on_tray_click(e, o))
            cv.bind("<Configure>",
                    lambda e, o=owner: self._safe_tray(o))
            self.trays[owner]["cv"] = cv

        # 棋谱
        tk.Label(side, text="棋谱", bg=self.col_dark, fg=self.col_dim,
                 font=self.f(9, True), anchor="w").pack(
            fill="x", padx=self.px(22), pady=(self.px(10), self.px(2)))
        wrap = tk.Frame(side, bg=self.col_card)
        wrap.pack(fill="both", expand=True, padx=self.px(14),
                  pady=(0, self.px(14)))
        self.log = tk.Text(wrap, bg=self.col_card, fg=self.col_text, bd=0,
                           highlightthickness=0, font=self.f(9), wrap="none",
                           padx=self.px(10), pady=self.px(8), spacing1=2,
                           spacing3=2, insertbackground=self.col_text,
                           state="disabled", cursor="hand2", height=6,
                           width=10, takefocus=0)
        sb = tk.Scrollbar(wrap, command=self.log.yview, width=self.px(10))
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)
        self.log.bind("<Button-1>", self._on_log_click)
        self.log.tag_configure("cur", background=self._hexc(self.theme.accent),
                               foreground="#FFFFFF")
        if self.light_ui:
            self.log.tag_configure("w", foreground="#2C6E4F")
            self.log.tag_configure("b", foreground="#2A4F7C")
            self.log.tag_configure("dim", foreground="#9A8A6E")
        else:
            self.log.tag_configure("w", foreground="#F2E6CF")
            self.log.tag_configure("b", foreground="#A9C0D8")
            self.log.tag_configure("dim", foreground="#8A7E6E")

    def _button(self, parent, text, cmd):
        lab = tk.Label(parent, text=text, bg=self.col_bar, fg=self.col_bar_ink,
                       font=self.f(9, True), padx=self.px(11), pady=self.px(6),
                       cursor="hand2")
        lab.bind("<Button-1>", lambda e: cmd())
        lab.bind("<Enter>", lambda e: lab.configure(bg=self.col_bar_hover))
        lab.bind("<Leave>", lambda e: lab.configure(bg=self.col_bar))
        return lab

    def toggle_fullscreen(self):
        """F11：全屏（录制视频时用）。

        全屏时把顶上的菜单条收起来，棋盘会重新按整个屏幕铺满，
        状态栏保留，录出来的画面干净又能看到轮到谁。
        """
        self.fullscreen = not getattr(self, "fullscreen", False)
        try:
            self.root.attributes("-fullscreen", self.fullscreen)
        except Exception:
            pass
        if self.fullscreen:
            self.topbar.pack_forget()
        else:
            self.topbar.pack(side="top", fill="x", before=self.body)
        self.root.update_idletasks()
        self.redraw()
        self.status.configure(
            text="  全屏模式（F11 退出）" if self.fullscreen else "  已退出全屏")

    def _bind_keys(self):
        r = self.root
        for seq, fn in (("<Control-z>", self.undo), ("<Control-Z>", self.undo),
                        ("<Control-y>", self.redo), ("<Control-s>", self.save_dialog),
                        ("<Control-o>", self.load_dialog),
                        ("<Control-n>", self.new_game_dialog),
                        ("<Escape>", self._escape),
                        ("<F5>", self.cycle_theme), ("<Control-h>", self.hint),
                        ("<Left>", lambda: self.step_review(-1)),
                        ("<Right>", lambda: self.step_review(1)),
                        ("<F11>", self.toggle_fullscreen),
                        ("<Control-m>", self.trial_ai_move),
                        ("<Home>", lambda: self.set_review(0)),
                        ("<End>", lambda: self.set_review(len(self.history)))):
            r.bind(seq, lambda e, fn=fn: fn())

    @staticmethod
    def _hexc(c):
        if isinstance(c, str):
            return c
        return "#%02X%02X%02X" % (c[0], c[1], c[2])

    def _ensure_ico(self):
        p = os.path.join(store.app_dir(), "app.ico")
        if not os.path.exists(p):
            art.render_icon(256).save(
                p, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                          (128, 128), (256, 256)])
        return p

    # ----------------------------------------------------------------- 尺寸
    def _on_resize(self, ev):
        self.redraw()

    def board_size(self):
        return (max(1, self.canvas.winfo_width()),
                max(1, self.canvas.winfo_height()))

    def _layout(self):
        """算缩放和原点：保证整个蜂巢（含叠起来的棋子）都在可视区域内。"""
        w, h = self.board_size()
        cells = list(self.game.stacks.keys()) or [(0, 0)]
        xs = [1.5 * p[0] for p in cells]
        ys = [SQ3 * (p[1] + p[0] / 2.0) for p in cells]
        # 叠起来的棋子会往上长
        top_stack = max((len(v) for v in self.game.stacks.values()), default=1)
        stack_up = (top_stack - 1) * 0.13
        # 单位都是「一枚棋子的半径 R」
        sx = (max(xs) - min(xs)) + 2.4          # 左右各半枚 + 阴影余量
        sy = (max(ys) - min(ys)) + SQ3 + 0.5 + stack_up
        pad = self.px(16)
        avail_w = max(self.px(60), w - 2 * pad)
        avail_h = max(self.px(60), h - 2 * pad)
        r = min(self.px(92), avail_w / sx, avail_h / sy)
        r = max(self.px(10), r)                 # 再大也缩，但不至于缩没
        self.R = r
        cxu = (max(xs) + min(xs)) / 2.0
        cyu = (max(ys) + min(ys)) / 2.0 - stack_up / 2.0
        self.origin = (w / 2.0 - cxu * r, h / 2.0 - cyu * r)
        return r

    def to_screen(self, p):
        return (self.origin[0] + 1.5 * self.R * p[0],
                self.origin[1] + SQ3 * self.R * (p[1] + p[0] / 2.0))

    def to_cell(self, sx, sy):
        x = (sx - self.origin[0]) / self.R
        y = (sy - self.origin[1]) / self.R
        q = 2.0 / 3.0 * x
        r = y / SQ3 - q / 2.0
        cx, cz = q, r
        cy = -cx - cz
        rx, ry, rz = round(cx), round(cy), round(cz)
        dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy > dz:
            ry = -rx - rz
        else:
            rz = -rx - ry
        return (int(rx), int(rz))

    # ----------------------------------------------------------------- 贴图
    def tile(self, kind, owner):
        key = (kind, owner, round(self.R))
        img = self._tiles.get(key)
        if img is None:
            pil, ctr = art.render_piece(kind, owner, self.theme, r=round(self.R))
            img = (ImageTk.PhotoImage(pil), ctr)
            self._tiles[key] = img
        return img

    def tray_tile(self, kind, owner):
        r = self.px(19)
        key = (kind, owner, r)
        img = self._tray.get(key)
        if img is None:
            pil, _c = art.render_piece(kind, owner, self.theme, r=r, shadow=False)
            img = ImageTk.PhotoImage(pil)
            self._tray[key] = img
        return img

    def dot(self, color, r=7, ring=False, width=2.4):
        key = (color, round(r), ring, round(width * 10))
        img = self._dots.get(key)
        if img is None:
            pil = art.render_marker(color, r=r, ring=ring, width=width)
            img = ImageTk.PhotoImage(pil)
            self._dots[key] = img
        return img

    def glow(self, color, r):
        key = ("glow", color, round(r))
        img = self._photos.get(key)
        if img is None:
            pil = art.render_glow(color, r=r)
            img = ImageTk.PhotoImage(pil)
            self._photos[key] = img
        return img

    def background(self, w, h):
        if self._bg is None or self._bg_size != (w, h):
            self._bg = ImageTk.PhotoImage(art.render_background(w, h, self.theme))
            self._bg_size = (w, h)
        return self._bg

    # ----------------------------------------------------------------- 绘制
    def redraw(self):
        """画界面。画图异常一律吞掉并记日志。

        画不出来可以忍，但绝不能让异常打断 _play 后面的流程——曾经因为
        dash 传浮点数抛 TclError，导致电脑再也没被叫醒，看起来像"卡死"。
        """
        try:
            self._redraw()
        except Exception:
            try:
                self._ai_log("redraw 异常：\n%s" % traceback.format_exc())
            except Exception:
                pass

    def _redraw(self):
        w, h = self.board_size()
        if w < 10 or h < 10:
            return
        self.canvas.delete("all")
        self._layout()
        self.canvas.create_image(0, 0, image=self.background(w, h), anchor="nw")

        accent = self._hexc(self.theme.accent)
        # 空格落点：小圆点（画在棋子下面没关系）
        for pos in self.dests:
            if pos in self.game.stacks:
                continue
            x, y = self.to_screen(pos)
            self.canvas.create_image(
                x, y, image=self.dot(accent, r=max(4, self.R * 0.16)))

        # 棋子
        order = sorted(self.game.stacks.keys(),
                       key=lambda p: (SQ3 * (p[1] + p[0] / 2.0), p[0]))
        for pos in order:
            st = self.game.stacks[pos]
            x, y = self.to_screen(pos)
            for lvl, uid in enumerate(st):
                dy = -lvl * self.R * 0.13
                photo, _ctr = self.tile(self.game.pieces[uid][1],
                                        self.game.pieces[uid][0])
                self.canvas.create_image(x, y + dy, image=photo, anchor="center")
            if len(st) > 1:
                self._stack_badge(x, y, len(st))

        # 被占格子的落点（甲虫爬上去）：必须画在棋子上面，否则会被盖住
        for pos in self.dests:
            if pos not in self.game.stacks:
                continue
            x, y = self.to_screen(pos)
            dy = -(len(self.game.stacks[pos]) - 1) * self.R * 0.13
            self.canvas.create_image(
                x, y + dy, image=self.dot(accent, r=self.R * 0.84, ring=True,
                                          width=max(2.0, self.R * 0.10)))

        # 鼠妇能搬的棋子：画一个橙色圈，点它才进搬运模式
        for uid, p in self.carryable.items():
            if uid == self.carry_uid:
                continue
            x, y = self.to_screen(p)
            lvl = self.game.stacks[p].index(uid) if uid in self.game.stacks.get(p, []) else 0
            self.canvas.create_image(
                x, y - lvl * self.R * 0.13,
                image=self.dot("#E8912E", r=self.R * 0.86, ring=True,
                               width=max(2.0, self.R * 0.09)))

        # 搬运落点
        for pos in self.carry_dests:
            x, y = self.to_screen(pos)
            self.canvas.create_image(
                x, y, image=self.dot("#E8912E", r=max(5, self.R * 0.19)))

        # 选中光晕
        if self.selected_uid is not None or self.carry_uid is not None:
            uid = self.carry_uid if self.carry_uid is not None else self.selected_uid
            p = self.game.where.get(uid)
            if p is not None:
                lvl = self.game.stacks.get(p, [0]).index(uid) \
                    if uid in self.game.stacks.get(p, []) else 0
                x, y = self.to_screen(p)
                self.canvas.create_image(
                    x, y - lvl * self.R * 0.13,
                    image=self.glow("#E8912E" if self.carry_uid is not None
                                    else accent, self.R + self.px(6)))

        if self.hint_mv is not None:
            self._draw_hint(self.hint_mv)

        # 蜘蛛的三步路线（鼠标停在落点上时显示）
        if self.path_hint and len(self.path_hint) > 1:
            pts = [self.to_screen(c) for c in self.path_hint]
            self.canvas.create_line(
                [(x, y) for x, y in pts], fill="#E8912E",
                width=max(2, int(self.R * 0.09)), smooth=False,
                dash=(int(max(3, self.R * 0.18)),
                      int(max(2, self.R * 0.10))))
            for i, (x, y) in enumerate(pts):
                rr = self.R * (0.16 if i in (0, len(pts) - 1) else 0.10)
                self.canvas.create_oval(x - rr, y - rr, x + rr, y + rr,
                                        fill="#E8912E", outline="")

        # 上一步标记
        if self.game.moves:
            rec = self.game.moves[-1]
            for key in ("frm", "to"):
                if rec.get(key):
                    x, y = self.to_screen(tuple(rec[key]))
                    self.canvas.create_image(
                        x, y, image=self.dot(accent, r=self.R * 0.86, ring=True,
                                             width=max(1.2, self.R * 0.05)))

        self._thinking_badge()
        self._update_status()

    def _stack_badge(self, x, y, n):
        r = max(self.px(7), self.R * 0.19)
        ox, oy = x + self.R * 0.55, y + self.R * 0.42
        self.canvas.create_oval(ox - r, oy - r, ox + r, oy + r, fill="#1A1512",
                                outline=self._hexc(self.theme.accent),
                                width=max(1, int(r * 0.20)))
        self.canvas.create_text(ox, oy, text=str(n), fill="#F5E9D2",
                                font=self.f(max(6, int(6 * self.s)), True))

    def _draw_hint(self, mv):
        color = "#6FD79B"
        if mv.frm is not None:
            a = self.to_screen(mv.frm)
            b = self.to_screen(mv.to)
            self.canvas.create_line(a[0], a[1], b[0], b[1], fill=color,
                                    width=max(2, self.px(2)), dash=(6, 4))
        x, y = self.to_screen(mv.to)
        self.canvas.create_image(x, y, image=self.dot(color, r=self.R * 0.34,
                                                      ring=True,
                                                      width=max(2, self.R * 0.10)))

    # ----------------------------------------------------------------- 状态
    def _update_status(self):
        g = self.game
        if g.result == "win":
            txt = "%s 获胜 —— %s" % (g.names[g.winner], g.reason)
        elif g.result == "draw":
            txt = "和棋 —— %s" % g.reason
        else:
            txt = "轮到 %s" % g.names[g.turn]
            if self.busy:
                txt += " · 电脑思考中…"
            elif g.queen_pos[g.turn] is None:
                left = 4 - g.turn_no[g.turn]
                txt += " · 蜂后必须在前 4 回合落下（还剩 %d 回合）" % max(0, left)
            if self.hint_mv is not None:
                txt += " · 绿圈就是提示的走法"
            if not g.legal_moves():
                txt += " · 已无棋可走，可点「停一手」"
        txt += "　|　官方规则（两侧同时被占才滑不过去）"
        if self.net is not None:
            txt += "　|　联机中 · 对手「%s」" % (self.net_peer or "?")
        elif self._net_waiting:
            txt += "　|　" + self._net_waiting
        self.status.configure(text="  " + txt)

    def _update_side(self):
        g = self.game
        if g.result:
            self.turn_lab.configure(text="对局结束",
                                    fg=self._hexc(self.theme.accent))
            self.turn_sub.configure(text=g.reason)
        else:
            color = self.col_w_ink if g.turn == 0 else self.col_b_ink
            self.turn_lab.configure(text="● " + g.names[g.turn] + " 行棋",
                                    fg=color)
            bits = []
            if g.queen_pos[g.turn] is None:
                bits.append("蜂后须在 %d 回合内落下"
                            % max(1, 4 - g.turn_no[g.turn]))
            if self.busy:
                bits.append("电脑正在思考…")
            if self.net is not None and g.turn != self.net_side:
                bits.insert(0, "联机：等「%s」落子…" % (self.net_peer or "对手"))
            if not g.legal_moves():
                bits.insert(0, "「%s」已无棋可走 —— 点「停一手」交给对方"
                            % g.names[g.turn])
            if self.trial_from is not None:
                bits.insert(0, "试下中 · 从第 %d 步开始 · 轮到「%s」· "
                               "Ctrl+M 让电脑走"
                            % (self.trial_from, g.names[g.turn]))
                bits.append("点 %s 那一侧的棋盒落子" % g.names[g.turn])
            else:
                bits.append("点己方棋子看走法，点棋盒落子")
            self.turn_sub.configure(text=" · ".join(bits))

        for owner in (0, 1):
            dot = "●"
            self.trays[owner]["head"].configure(
                text="%s %s" % (dot, g.names[owner]),
                fg=self.col_w_ink if owner == 0 else self.col_b_ink)
            self._draw_tray(owner)
        self._refresh_log()
        self._tray_ready = True
        self._arm_ai()

    def _draw_tray(self, owner):
        cv = self.trays[owner]["cv"]
        cv.delete("all")
        g = self.game
        kinds = list(g.kinds)
        counts = {}
        for uid in g.hand[owner]:
            k = g.pieces[uid][1]
            counts[k] = counts.get(k, 0) + 1
        active = (not g.result) and g.turn == owner and self.my_turn()
        w = cv.winfo_width()
        if w < 20:
            w = self.side_w - self.px(20)
        step = w / float(max(1, len(kinds)))
        hh = cv.winfo_height() or self.px(72)
        img0 = self.tray_tile(kinds[0], owner) if kinds else None
        tw = img0.width() if img0 else self.px(38)
        for i, k in enumerate(kinds):
            cx = step * (i + 0.5)
            ty = hh * 0.40
            n = counts.get(k, 0)
            sel = self.selected_kind == k and g.turn == owner
            if n <= 0:
                # 已经下完的棋子：只留一个淡淡的轮廓，别抢眼
                rr = tw * 0.46
                cv.create_polygon(
                    cx, ty - rr, cx + rr * 0.88, ty - rr * 0.5,
                    cx + rr * 0.88, ty + rr * 0.5, cx, ty + rr,
                    cx - rr * 0.88, ty + rr * 0.5, cx - rr * 0.88, ty - rr * 0.5,
                    outline=self.col_line, fill="", width=1, dash=(3, 3))
                cv.create_text(cx, ty, text="—", fill=self.col_dim,
                               font=self.f(8))
            else:
                if sel or active:
                    cv.create_rectangle(
                        cx - tw / 2 - 2, ty - tw / 2 - 2,
                        cx + tw / 2 + 2, ty + tw / 2 + 2,
                        outline=self._hexc(self.theme.accent) if sel
                        else self.col_line,
                        width=2 if sel else 1)
                cv.create_image(cx, ty, image=self.tray_tile(k, owner),
                                anchor="center")
                bx, by = cx + tw * 0.34, ty + tw * 0.30
                br = max(self.px(7), tw * 0.17)
                cv.create_oval(bx - br, by - br, bx + br, by + br,
                               fill="#171310",
                               outline=self._hexc(self.theme.accent), width=1)
                cv.create_text(bx, by, text=str(n), fill="#F5E9D2",
                               font=self.f(7, True))
            cv.create_text(cx, hh * 0.88, text=KIND_NAMES[k],
                           fill=self.col_dim if n > 0 else self.col_line,
                           font=self.f(7))

    def _safe_tray(self, owner):
        if getattr(self, "_tray_ready", False):
            self._draw_tray(owner)

    def _rec_of(self, mv):
        """从着法对象还原一条可显示的记录（复盘时也用它）。"""
        owner, kind = self.game.pieces[mv.uid]
        return {"p": owner, "k": kind, "uid": mv.uid,
                "frm": list(mv.frm) if mv.frm is not None else None,
                "to": list(mv.to), "aux": mv.aux}

    def _refresh_log(self):
        g = self.game
        shown = self.record if self.trial_from is not None else self.history
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        for i, mv in enumerate(shown):
            rec = self._rec_of(mv)
            tag = "w" if rec["p"] == 0 else "b"
            self.log.insert("end", "%3d  " % (i + 1), "dim")
            self.log.insert("end", ("白 " if rec["p"] == 0 else "黑 "), tag)
            self.log.insert("end", move_text(g, rec) + "\n", tag)
        if self.game.result:
            self.log.insert("end", "\n" + (self.game.reason or "") + "\n", "dim")
        if self.trial_from is not None:
            self.log.insert("end", "\n【试下中】从第 %d 步开始推演\n"
                            % self.trial_from, "dim")
        # 高亮当前复盘到的那一行
        if self.trial_from is not None:
            cur = self.trial_from
        elif self.review is not None:
            cur = self.review
        else:
            cur = len(shown)
        if 1 <= cur <= len(shown):
            self.log.tag_add("cur", "%d.0" % cur, "%d.end" % cur)
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----------------------------------------------------------------- 复盘
    def _review_state(self):
        return self.review if self.review is not None else len(self.history)

    # ------------------------------------------------------------- 试下
    def enter_trial(self, k=None):
        """从棋谱第 k 步开始试下：还原双方当时的手牌，可以随便摆。"""
        if self._net_busy_hint():
            return
        if self.trial_from is not None:
            return
        if self.review is None:
            return
        k = self.review if k is None else int(k)
        rec = list(self.history)
        self.busy = False           # 别让「电脑思考中」把试下锁死
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.record = rec
        self.trial_from = k
        self.review = None
        self._rebuild(rec[:k], keep=rec[:k])
        self.history = rec[:k]
        self.status.configure(
            text="  试下中（从第 %d 步开始，双方手牌已还原）　Ctrl+M 让电脑走一步，"
                 "点棋谱或按 ← → 退出" % k)
        self._update_side()

    def exit_trial(self):
        """退出试下，回到原始棋谱。"""
        if self.trial_from is None:
            return False
        rec = list(self.record or [])
        self.trial_from = None
        self.record = None
        self._rebuild(rec)
        self.history = rec
        self.review = None
        self._update_side()
        return True

    def trial_ai_move(self):
        """试下时让电脑在当前位置走一步（双方都能让它走）。"""
        if self.trial_from is None:
            self.status.configure(
                text="  先点棋谱任意一行进入复盘，再点棋子或棋盒开始试下")
            return
        if self.game.result:
            return
        self._set_thinking(True)
        mv, dt = self._compute_ai_move(self.game)
        self._ai_log("（试下）难度 %s 思考 %.2fs" % (self.ai_level, dt))
        self.busy = False
        try:
            self.canvas.configure(cursor="")
        except Exception:
            pass
        if mv is not None:
            self._play(mv)
        else:
            self._update_status()

    def set_review(self, k):
        """把棋盘回放到第 k 步（0=开局）。k == 总步数就是回到实时。"""
        if self.trial_from is not None:
            self.exit_trial()
        total = len(self.history)
        k = max(0, min(total, int(k)))
        if k == total:
            if self.review is None:
                return
            self.review = None
            self._rebuild(self.history)
            # 回到实时后，如果正好轮到电脑，得重新叫醒它
            self._maybe_ai()
            return
        if self.review == k:
            return
        full = list(self.history)
        self.review = k
        self.busy = False          # 正在飞的电脑回合作废（_ai_move 会自己退出）
        self._rebuild(full[:k], keep=full)
        self.status.configure(text="  复盘：第 %d / %d 步　（← → 翻看，Esc 回当前）"
                                   % (k, total))

    def step_review(self, delta):
        self.set_review(self._review_state() + delta)

    def exit_review(self):
        if self.review is not None:
            self.set_review(len(self.history))

    def _escape(self):
        if self.trial_from is not None:
            k = self.trial_from
            self.exit_trial()
            self.set_review(k)
            return
        if self.review is not None:
            self.exit_review()
        else:
            self.clear_selection()

    def _on_log_click(self, ev):
        src = self.record if self.trial_from is not None else self.history
        if not src:
            return
        try:
            line = int(self.log.index("@%d,%d" % (ev.x, ev.y)).split(".")[0])
        except Exception:
            return
        if 1 <= line <= len(src):
            self.exit_trial()
            self.set_review(line)

    def _set_hover(self, cell):
        self.hover = cell
        if cell is None:
            self.canvas.configure(cursor="")
        elif cell in self.dests or self.game.top(cell) is not None:
            self.canvas.configure(cursor="hand2")
        else:
            self.canvas.configure(cursor="")

    def _spider_path(self, start, dest):
        """找一条从 start 到 dest 的合法三步路线（蜘蛛 / 复制蜘蛛的蚊子）。"""
        g = self.game
        occ = set(g.stacks)
        st = g.stacks.get(start) or []
        if len(st) <= 1:
            occ.discard(start)
        per = g._perimeter(occ)
        seen = {start}

        def walk(cur, depth, acc):
            if depth == 3:
                return acc if cur == dest else None
            for d in DIRS:
                n = (cur[0] + d[0], cur[1] + d[1])
                if n in occ or n in seen or n not in per:
                    continue
                if not g._slide_ok(cur, n, occ):
                    continue
                seen.add(n)
                r = walk(n, depth + 1, acc + [n])
                seen.discard(n)
                if r:
                    return r
            return None

        return walk(start, 0, [start])

    def on_motion(self, ev):
        cell = self.to_cell(ev.x, ev.y)
        self._set_hover(cell)
        old = self.path_hint
        self.path_hint = None
        if (cell in self.dests and self.selected_uid is not None
                and self.game.pieces[self.selected_uid][1] == "spider"):
            start = self.game.where.get(self.selected_uid)
            if start is not None:
                self.path_hint = self._spider_path(start, cell)
        if self.path_hint != old:
            self.redraw()

    def _thinking_badge(self):
        """电脑思考时在棋盘上方挂一个横幅，让人知道它在算，不是卡住了。"""
        if not self.busy or self.game.result:
            return
        txt = "电脑思考中…"
        ft = self.f(12, True)
        tw = tkfont.Font(family=self.fam, size=12, weight="bold").measure(txt)
        pw = tw + self.px(66)
        ph = self.px(34)
        x0 = (self.canvas.winfo_width() - pw) / 2.0
        y0 = self.px(16)
        self.canvas.create_rectangle(x0, y0, x0 + pw, y0 + ph,
                                     fill=self._hexc(self.theme.accent),
                                     outline="")
        self.canvas.create_text(x0 + pw / 2, y0 + ph / 2, text=txt,
                                fill="#FFFFFF", font=ft)

    def _set_thinking(self, on):
        """统一开关「思考中」：光标变等待 + 棋盘横幅 + 立刻刷出来。"""
        self.busy = on
        try:
            self.canvas.configure(cursor="watch" if on else "")
        except Exception:
            pass
        self.redraw()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    # ----------------------------------------------------------------- 交互
    def clear_selection(self):
        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hint_mv = None
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.redraw()

    def my_turn(self):
        g = self.game
        if g.result or self.busy or self.review is not None:
            return False
        if self.net is not None:
            # 联机：只能在自己的回合动；试下会跟对家下岔，直接禁掉
            if not self.net.alive or self.trial_from is not None:
                return False
            return g.turn == self.net_side
        if (self.versus == "ai" and g.turn == self.ai_side
                and self.trial_from is None):
            return False
        return True

    def _dest_map(self, moves):
        d = {}
        for mv in moves:
            d.setdefault(mv.to, mv)
        return d

    def on_tray_click(self, ev, owner):
        if self.review is not None:
            # 复盘状态下点棋盒 = 从这一步开始试下
            if owner != self.game.turn:
                self.status.configure(
                    text="  复盘：这一步轮到 %s，点它那侧的棋盒才能试下"
                         % self.game.names[self.game.turn])
                return
            self.enter_trial()
            if self.trial_from is None:
                return
            self.on_tray_click(ev, owner)
            return
        if owner != self.game.turn:
            if self.trial_from is not None:
                self.status.configure(
                    text="  试下中：现在轮到「%s」，请点 %s 那一侧的棋盒"
                         % (self.game.names[self.game.turn],
                            self.game.names[self.game.turn]))
            return
        if not self.my_turn():
            if self.trial_from is not None:
                self.status.configure(
                    text="  试下中：电脑正在算，稍等一下（或按 Esc 退出试下）")
            return
        g = self.game
        kinds = list(g.kinds)
        counts = {}
        for uid in g.hand[owner]:
            k = g.pieces[uid][1]
            counts[k] = counts.get(k, 0) + 1
        cv = self.trays[owner]["cv"]
        w = cv.winfo_width() or self.px(300)
        step = w / float(len(kinds))
        idx = int(ev.x // step)
        if idx < 0 or idx >= len(kinds):
            return
        k = kinds[idx]
        if counts.get(k, 0) <= 0:
            return
        if self.selected_kind == k:
            self.clear_selection()
            return
        moves = [m for m in g.legal_moves()
                 if m.kind == "place" and g.pieces[m.uid][1] == k]
        self.selected_kind = k
        self.selected_uid = None
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.dests = self._dest_map(moves)
        if not moves:
            self.status.configure(text='  ' + KIND_NAMES[k] + '现在没有可以落子的位置')
        self.redraw()
        self._draw_tray(owner)
        self._draw_tray(1 - owner)

    def _select_uid(self, uid, owner):
        g = self.game
        self.selected_uid = uid
        self.selected_kind = None
        self.carry_uid = None
        self.carry_dests = {}
        # 鼠妇的搬运着法挂在「被搬的那枚棋子」名下，所以要按 aux 找回来
        moves = [m for m in g.legal_moves()
                 if m.uid == uid or (m.kind == "toss" and m.aux == uid)]
        self.dests = self._dest_map([m for m in moves if m.kind != "toss"])
        self.carryable = {}
        for m in moves:
            if m.kind == "toss":
                self.carryable[m.uid] = g.where[m.uid]
        self.redraw()
        self._draw_tray(owner)
        self._draw_tray(1 - owner)
        if not self.dests and not self.carryable:
            self.status.configure(text="  " + self.stuck_reason(uid))
        elif self.carryable:
            self.status.configure(
                text="  鼠妇能搬旁边橙圈圈的棋子：点它，再点落点")

    def _start_carry(self, target_uid):
        g = self.game
        moves = [m for m in g.legal_moves()
                 if m.kind == "toss" and m.uid == target_uid]
        if not moves:
            return
        self.carry_uid = target_uid
        self.carry_dests = self._dest_map(moves)
        self.selected_uid = None
        self.selected_kind = None
        self.dests = {}
        self.carryable = {}
        self.redraw()
        self.status.configure(text="  正在搬运：点橙色小圆点放下")

    def stuck_reason(self, uid) -> str:
        """解释这枚棋子为什么动不了。"""
        g = self.game
        p = g.where.get(uid)
        if p is None:
            return ""
        name = KIND_NAMES[g.pieces[uid][1]]
        st = g.stacks.get(p) or []
        if st and st[-1] != uid:
            return "%s被压在下面，动不了" % name
        if not g._removal_ok(uid):
            return "%s不能动：抬起它会把蜂巢断成两半（一巢规则）" % name
        occ = set(g.stacks)
        if len(st) == 1:
            occ.discard(p)
        pinch, detach = [], []
        for i, d in enumerate(DIRS):
            n = (p[0] + d[0], p[1] + d[1])
            if n in occ:
                continue
            corners = [(p[0] + DIRS[(i - 1) % 6][0], p[1] + DIRS[(i - 1) % 6][1]),
                       (p[0] + DIRS[(i + 1) % 6][0], p[1] + DIRS[(i + 1) % 6][1])]
            if all(c in occ for c in corners):
                pinch.append(n)          # 官方规则：两侧同时被占才挤不过去
            elif not any((n[0] + dd[0], n[1] + dd[1]) in occ for dd in DIRS):
                detach.append(n)
        if pinch and detach:
            return "%s走不了：有方向被两侧的棋子同时占住（自由移动规则），另外几个方向会断开蜂巢" % name
        if pinch:
            return "%s走不了：每个方向的两侧都被棋子同时占住了（自由移动规则）" % name
        if detach:
            return "%s走不了：能去的格子都不挨着蜂巢，走了会断开（一巢规则）" % name
        return "%s现在走不了" % name

    def on_click(self, ev):
        if self.review is not None:
            cell = self.to_cell(ev.x, ev.y)
            if cell in self.game.stacks or cell in self.dests:
                self.enter_trial()
                if self.trial_from is not None:
                    self.on_click(ev)
                return
            self.status.configure(
                text="  复盘：点棋子或棋盒即可从这一步开始试下；← → 翻看原棋谱")
            return
        if not self.my_turn():
            return
        cell = self.to_cell(ev.x, ev.y)
        g = self.game

        # 1) 搬运落点
        if self.carry_uid is not None and cell in self.carry_dests:
            self._play(self.carry_dests[cell])
            return

        # 2) 点到了鼠妇能搬的棋子
        if self.carryable:
            for uid in reversed(g.stacks.get(cell) or []):
                if uid in self.carryable:
                    self._start_carry(uid)
                    return

        # 3) 普通落点
        if cell in self.dests:
            self._play(self.dests[cell])
            return

        if cell in g.stacks:
            for uid in reversed(g.stacks[cell]):
                if g.pieces[uid][0] == g.turn:
                    if uid == self.selected_uid:
                        self.clear_selection()
                        return
                    self._select_uid(uid, g.turn)
                    return
        self.clear_selection()

    def _play(self, mv: Move, remote: bool = False):
        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hint_mv = None
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.game.apply(mv)
        self.history.append(mv)
        self.future.clear()
        self._last_action = "落子 %s" % (mv,)
        if self.net is not None and not remote:
            self._net_send_move(mv)
        self.redraw()
        self._update_side()
        if self._adjudicate_stuck():
            self.redraw()
            self._update_side()
            self._autosave()
            self._announce()
            return
        self._autosave()
        if self.game.result:
            self._announce()
        else:
            self._maybe_ai()

    def _announce(self):
        g = self.game
        if g.result == "win":
            messagebox.showinfo("对局结束",
                                "%s 获胜！\n\n%s" % (g.names[g.winner], g.reason))
        else:
            messagebox.showinfo("对局结束", g.reason)

    def _autosave(self):
        if self.trial_from is not None:
            return          # 试下是推演，不写进存档
        try:
            store.save_game(store.autosave_path(), self.game, self.history,
                            self.theme.key, self.versus)
        except Exception:
            pass

    # ----------------------------------------------------------------- 电脑
    def _ai_log(self, msg):
        """把电脑思考的情况记下来，出问题时能查。"""
        try:
            p = os.path.join(store.app_dir(), "ai.log")
            if os.path.exists(p) and os.path.getsize(p) > 200 * 1024:
                os.replace(p, p + ".old")
            with open(p, "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    def _compute_ai_move(self, g):
        """带硬超时的思考：跑在后台线程里，超时就拿一个合法着法顶上。

        正常情况 choose_move 自己有 0.05/1.2/3.0 秒预算，这里只是兜底，
        防止任何意外（异常、死循环、其它代码抢锁）把界面永远卡住。
        """
        old = getattr(self, "_ai_thread", None)
        if old is not None and old.is_alive():
            self._ai_log("上一次思考还没结束（线程仍在跑），本次直接用随机着法"
                         "，避免越积越卡")
            moves = g.legal_moves()
            return (random.choice(moves) if moves else None), 0.0
        level = self.ai_level
        budget = ailib.TIME_BUDGET.get(level, 1.2)
        cap = max(5.0, budget * 3 + 2.0)
        box = {}

        def work():
            try:
                box["mv"] = ailib.choose_move(g, level, random.Random())
            except Exception:
                box["err"] = traceback.format_exc()

        th = threading.Thread(target=work, daemon=True)
        self._ai_thread = th
        t0 = time.time()
        th.start()
        th.join(cap)
        dt = time.time() - t0
        if "err" in box:
            self._ai_log("难度 %s 抛异常（%.2fs）：\n%s" % (level, dt, box["err"]))
            return None, dt
        if th.is_alive():
            self._ai_log("难度 %s 超时 %.2fs（上限 %.1fs），改用随机合法着法"
                         % (level, dt, cap))
            moves = g.legal_moves()
            return (random.choice(moves) if moves else None), dt
        return box.get("mv"), dt

    def _maybe_ai(self):
        g = self.game
        if self.busy or self.review is not None or self.trial_from is not None:
            return
        if self.versus != "ai" or g.result or g.turn != self.ai_side:
            return
        self.busy = True
        self._update_status()
        self._update_side()
        try:
            self.canvas.configure(cursor='watch')
        except Exception:
            pass
        self.redraw()          # 先把「电脑思考中」画出来，再去算
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self.root.after(120, self._ai_move)

    def _heartbeat(self):
        """每 0.5 秒打一次点；如果两次之间隔了很久，说明界面被堵住了。"""
        try:
            now = time.time()
            gap = now - self._beat
            if gap > 6.0:
                self._ai_log("界面卡了 %.1f 秒！卡之前的动作：%s（步数 %d，轮到 %d）"
                             % (gap, self._last_action,
                                len(self.history), self.game.turn))
            self._beat = now
        except Exception:
            pass
        self.root.after(500, self._heartbeat)

    def _watchdog(self):
        """每 700 毫秒兜一次底：只要轮到电脑又没人管，就把它叫醒。

        这是最后一道保险，任何路径（新局/读档/复盘/悔棋/异常）漏了触发，
        这里都能把棋局从「黑方行棋但没动静」里救回来。
        """
        try:
            g = self.game
            if (self.versus == "ai" and self.review is None and not self.busy
                    and self.trial_from is None
                    and not g.result and g.turn == self.ai_side):
                self._maybe_ai()
        except Exception:
            pass
        self.root.after(700, self._watchdog)

    def _arm_ai(self):
        """只要界面上显示「轮到电脑」，就保证电脑一定会被叫醒。

        每次刷新界面都检查一次，任何路径（复盘、悔棋、读档、重做）漏了调
        _maybe_ai 都会被这里补上，不会再出现「黑方行棋但没动静」。
        """
        if self.busy or self.review is not None or self.trial_from is not None:
            return
        g = self.game
        if self.versus == "ai" and not g.result and g.turn == self.ai_side:
            self.root.after(30, self._maybe_ai)

    def _ai_move(self):
        g = self.game
        # 复盘时棋盘是历史局面，这时候绝不能落子（否则棋谱会被写乱）
        if self.review is not None or self.trial_from is not None:
            self.busy = False
            return
        if g.result or self.versus != "ai" or g.turn != self.ai_side:
            self.busy = False
            return
        mv, dt = self._compute_ai_move(g)
        self._ai_log("难度 %s 思考 %.2fs，着法 %s"
                     % (self.ai_level, dt,
                        None if mv is None else (mv.kind, mv.frm, mv.to)))
        self.busy = False
        try:
            self.canvas.configure(cursor="")
        except Exception:
            pass
        if mv is None:
            g.turn = 1 - g.turn
            self.redraw()
            self._update_side()
            return
        try:
            g.apply(mv)
        except Exception:
            self._ai_log("着法执行失败：%s\n%s"
                         % (mv, traceback.format_exc()))
            g.turn = 1 - g.turn          # 这一步跳过，绝不停在原地重试
            self.redraw()
            self._update_side()
            return
        self.history.append(mv)
        self.future.clear()
        self._last_action = "电脑落子 %s" % (mv,)
        self.redraw()
        self._update_side()
        self._autosave()
        if self._adjudicate_stuck():
            self.redraw()
            self._update_side()
            self._announce()
        elif g.result:
            self._announce()

    def hint(self):
        g = self.game
        if g.result:
            self.status.configure(text="  对局已结束")
            return
        if self.busy or (self.versus == "ai" and g.turn == self.ai_side
                         and self.review is None and self.trial_from is None):
            self.status.configure(text="  现在轮到电脑，等它走完再点提示")
            return
        self.status.configure(text="  电脑正在算这一步…")
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        mv = ailib.choose_move(g, 2, random.Random())
        if mv is None:
            self.hint_mv = None
            self.status.configure(text="  这一步没有可走的棋，点「停一手」")
        else:
            self.hint_mv = mv
            self.status.configure(
                text="  提示：绿圈就是电脑建议的走法（%s→%s）"
                     % (mv.frm or "手上", mv.to))
        self.redraw()
        self.redraw()

    # ----------------------------------------------------------------- 悔棋
    def _adjudicate_stuck(self):
        """一方无棋可动就判负（老师定的规则）。"""
        g = self.game
        if g.result:
            return False
        if g.legal_moves():
            return False
        g.result = "win"
        g.winner = 1 - g.turn
        g.reason = "%s 无棋可动，判负" % g.names[g.turn]
        return True

    def resign(self):
        """认输：直接判负。联机时算「我」认输，并告诉对方。"""
        g = self.game
        if g.result:
            return
        if self.net is not None:
            who = g.names[self.net_side]
            if not messagebox.askyesno("认输", "确定认输吗？（对方会被判胜）"):
                return
            g.result = "win"
            g.winner = 1 - self.net_side
            g.reason = "%s 认输" % who
            self.net.send({"t": "resign"})
            self.redraw()
            self._update_side()
            self._announce()
            self._autosave()
            return
        who = g.names[g.turn]
        if not messagebox.askyesno("认输", "确定由「%s」认输吗？" % who):
            return
        g.result = "win"
        g.winner = 1 - g.turn
        g.reason = "%s 认输" % who
        self.redraw()
        self._update_side()
        self._announce()

    def pass_turn(self):
        """停一手：把回合交给对方。"""
        g = self.game
        if g.result:
            self.status.configure(text="  对局已结束")
            return
        if self.busy:
            self.status.configure(text="  电脑正在思考，稍等一下")
            return
        if self.net is not None and g.turn != self.net_side:
            self.status.configure(text="  联机：等对方落子，不能替他停一手")
            return
        moves = g.legal_moves()
        if moves:
            if not messagebox.askyesno(
                    "停一手", "「%s」现在还有 %d 种走法，确定要停一手吗？"
                    % (g.names[g.turn], len(moves))):
                return
        g.turn = 1 - g.turn
        g.passes = getattr(g, "passes", 0) + 1
        self.clear_selection()
        if self.net is not None:
            self._net_send_pass()
        self.redraw()
        self._update_side()
        self.status.configure(text="  %s 停一手，轮到 %s"
                                   % (g.names[1 - g.turn], g.names[g.turn]))
        if self._adjudicate_stuck():
            self.redraw()
            self._update_side()
            self._announce()
            return
        self._maybe_ai()

    def _rebuild(self, moves, keep=None):
        g = Game(self.game.expansions, self.game.first_player,
                 names=list(self.game.names))
        for mv in moves:
            g.apply(mv)
        self.game = g
        self.history = list(keep if keep is not None else moves)
        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hint_mv = None
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.redraw()
        self._update_side()

    def undo(self):
        self.exit_review()
        if self._net_busy_hint():
            return
        if not self.history or self.busy:
            return
        n = 1
        if self.versus == "ai" and self.game.turn != self.ai_side:
            n = 2
        n = min(n, len(self.history))
        moved = self.history[-n:]
        self.future = list(reversed(moved)) + self.future
        self._rebuild(self.history[:-n])
        try:
            store.save_game(store.autosave_path(), self.game, self.history,
                            self.theme.key, self.versus)
        except Exception:
            pass

    def redo(self):
        self.exit_review()
        if self._net_busy_hint():
            return
        if self.busy:
            self.status.configure(text="  电脑正在思考，稍等一下")
            return
        if not self.future:
            self.status.configure(
                text="  没有可重做的着法（重做只对「刚悔掉的棋」有效）")
            return
        mv = self.future.pop(0)
        self.game.apply(mv)
        self.history.append(mv)
        self.redraw()
        self._update_side()
        self._autosave()
        if self.game.result:
            self._announce()
        else:
            self._maybe_ai()

    # ----------------------------------------------------------------- 菜单
    def cycle_theme(self):
        idx = art.THEMES.index(self.theme)
        self.theme = art.THEMES[(idx + 1) % len(art.THEMES)]
        self.settings["theme"] = self.theme.key
        store.save_settings(self.settings)
        self._apply_chrome()
        self._clear_caches()
        for w in list(self.root.winfo_children()):
            w.destroy()
        self._tray_ready = False
        self._build_window()
        self.redraw()
        self._update_side()
        self.status.configure(text="  配色：%s" % self.theme.name)

    def _clear_caches(self):
        self._bg = None
        self._bg_size = None
        self._tiles.clear()
        self._tray.clear()
        self._dots.clear()
        self._photos.clear()

    def save_dialog(self):
        self.exit_trial()
        self.exit_review()
        if not self.history:
            messagebox.showinfo("存盘", "还没有走子，不用存。")
            return
        d = store.record_dir()
        name = "%s vs %s %s.hive" % (self.game.names[0], self.game.names[1],
                                     _stamp())
        path = filedialog.asksaveasfilename(
            title="保存对局", initialdir=d, initialfile=name,
            defaultextension=".hive",
            filetypes=[("虫虫蜂房存档", "*.hive"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            store.save_game(path, self.game, self.history, self.theme.key,
                            self.versus)
            self.status.configure(text="  已保存：%s" % path)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def export_dialog(self):
        self.exit_trial()
        self.exit_review()
        if not self.history:
            messagebox.showinfo("棋谱", "还没有走子。")
            return
        d = store.record_dir()
        name = "%s vs %s %s.txt" % (self.game.names[0], self.game.names[1],
                                    _stamp())
        path = filedialog.asksaveasfilename(
            title="导出棋谱（文本）", initialdir=d, initialfile=name,
            defaultextension=".txt",
            filetypes=[("文本棋谱", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            store.export_text(path, self.game, self.history)
            self.status.configure(text="  棋谱已导出：%s" % path)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def load_dialog(self):
        path = filedialog.askopenfilename(
            title="读取对局", initialdir=store.record_dir(),
            filetypes=[("虫虫蜂房存档", "*.hive"), ("所有文件", "*.*")])
        if path:
            self._load_path(path)

    def _load_path(self, path):
        try:
            g, moves, data = store.load_game(path)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        self.net_close("读了别的棋谱，联机已断开", notify=False)
        self.game = g
        self.history = list(moves)
        self.future.clear()
        self.versus = data.get("versus", self.versus)
        if data.get("theme") in art.THEME_BY_KEY:
            self.theme = art.THEME_BY_KEY[data["theme"]]
            self._clear_caches()
            self._tray.clear()
            self._dots.clear()
            self._photos.clear()
        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hint_mv = None
        # 读档要把「复盘 / 思考中 / 搬运」这些临时状态清干净，
        # 否则 review 一旦留着，所有操作都会被当成复盘挡掉，看起来就是卡死
        self.review = None
        self.trial_from = None
        self.record = None
        self.busy = False
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.redraw()
        self._update_side()
        self.status.configure(text="  已读取：%s" % path)

    # ----------------------------------------------------------------- 新局
    def new_game_dialog(self):
        NewGameDialog(self)

    def _reset_game(self, names, expansions, first):
        """把界面和棋局都重置成新开一局的样子（单机 / 联机共用）。"""
        self.game = Game(expansions, int(first) % 2, names=names)
        self.history = []
        self.future = []
        self.review = None
        self.trial_from = None
        self.record = None
        self.carry_uid = None
        self.carry_dests = {}
        self.carryable = {}
        self.selected_kind = None
        self.selected_uid = None
        self.dests = {}
        self.hint_mv = None
        self.busy = False
        self.redraw()
        self._update_side()

    def start_new(self, names, expansions, versus, ai_level, side, first=0):
        self.versus = versus
        self.ai_level = ai_level
        self.ai_side = side
        self.settings["names"] = names
        self.settings["versus"] = versus
        self.settings["ai_level"] = ai_level
        self.settings.pop("relaxed", None)      # 旧设置里的规则开关作废
        self.settings["first"] = int(first) % 2
        store.save_settings(self.settings)
        self.net_close("开了新局，联机已断开", notify=False)
        self._reset_game(names, expansions, first)
        self._autosave()
        self._maybe_ai()

    def show_rules(self):
        RulesDialog(self)

    # ----------------------------------------------------------------- 联机
    def net_dialog(self):
        NetDialog(self)

    def _net_event(self, *ev):
        """后台线程往界面递消息（线程里绝不能直接碰控件）。"""
        self._net_events.put(ev)

    def _net_tick(self):
        """定时收：后台事件 + 对家发来的消息。"""
        try:
            while True:
                self._net_handle_event(*self._net_events.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            self._ai_log("联机事件处理出错：\n%s" % traceback.format_exc())
        sess = self.net
        if sess is not None:
            try:
                for msg in sess.poll():
                    self._net_handle_msg(msg)
            except Exception:
                self._ai_log("联机消息处理出错：\n%s" % traceback.format_exc())
                self.net_close("消息出错，联机已断开")
        try:
            self.root.after(80, self._net_tick)
        except tk.TclError:
            pass

    # ---------------------------------------------------------- 开房 / 加入
    def net_host(self, name, expansions, first, port=8765):
        """开房：占端口 → 显示 IP:端口 → 后台等对手进来。"""
        self.net_close("重新开房", notify=False)
        try:
            room = netlib.Host(port)
        except netlib.NetError as e:
            messagebox.showerror("开不了房", str(e))
            return False
        self.net_room = room
        self.versus = "net"
        self.net_side = 0
        self.net_peer = ""
        self._reset_game([name, "等待对手…"], expansions, first)
        self._net_waiting = "房间已开：%s:%d，等对方加入" % (netlib.local_ip(), room.port)
        self._update_status()
        self.status.configure(
            text="  房间已开：%s:%d —— 把 IP 和端口告诉对方，等他点「加入」"
                 % (netlib.local_ip(), room.port))
        threading.Thread(target=self._net_host_worker,
                         args=(room, name, expansions, first),
                         daemon=True).start()
        return True

    def _net_host_worker(self, room, name, expansions, first):
        sess, addr = room.accept()
        if sess is None:
            self._net_event("err", "开房失败：%s" % (room.error or "没有等到连接"))
            return
        hello = netlib.wait_hello(sess)
        if hello is None:
            why = sess.error or "对方没说上话就断开"
            sess.close(why)
            self._net_event("err", why)
            return
        peer = str(hello.get("name") or "对手")
        if list(hello.get("expansions") or []) != list(expansions):
            sess.send({"t": "error", "why": "扩展棋子不一致"})
            sess.close("扩展棋子不一致")
            self._net_event("err", "对手开的扩展棋子和房主不同，先统一再开房")
            return
        names = [name, peer]
        if not sess.send({"t": "start", "expansions": list(expansions),
                          "first_player": int(first) % 2, "names": names}):
            self._net_event("err", "开局信息没发出去（连接已断）")
            return
        self._net_event("ready", sess, 0, names)

    def net_join(self, ip, port, name):
        """加入：连房主，后台握手。"""
        self.net_close("重新加入", notify=False)
        self.versus = "net"
        self.net_side = 1
        self.net_peer = ""
        self._net_waiting = "正在连 %s:%s …" % (ip, port)
        self._update_status()
        self.status.configure(text="  正在连 %s:%s …" % (ip, port))
        threading.Thread(target=self._net_join_worker,
                         args=(ip, port, name), daemon=True).start()
        return True

    def _net_join_worker(self, ip, port, name):
        try:
            sess = netlib.connect(ip, port)
        except netlib.NetError as e:
            self._net_event("err", str(e))
            return
        if not sess.send(netlib.hello_msg(name, [], 0, 1)):
            self._net_event("err", "连上去了但没说上话")
            return
        start = netlib.wait_start(sess)
        if start is None:
            why = sess.error or "房主没有开始（可能版本不一样）"
            sess.close(why)
            self._net_event("err", why)
            return
        names = list(start.get("names") or ["房主", name])
        if len(names) != 2:
            names = ["房主", name]
        self._net_event("ready", sess, 1, names, start)

    # ---------------------------------------------------------- 事件 / 消息
    def _net_handle_event(self, kind, *rest):
        if kind == "err":
            why = rest[0] if rest else "联机失败"
            self._net_waiting = ""
            self.net_room = None
            self._ai_log("联机失败：%s" % why)
            self._update_status()
            self.status.configure(text="  " + why)
            messagebox.showerror("联机失败", why)
            return
        if kind == "ready":
            sess, side, names = rest[0], rest[1], rest[2]
            start = rest[3] if len(rest) > 3 else None
            self.net_room = None
            self._net_waiting = ""
            self.net = sess
            self.net_side = int(side)
            self.net_peer = names[1] if self.net_side == 0 else names[0]
            if start is not None:
                exps = list(start.get("expansions") or [])
                first = int(start.get("first_player", 0)) % 2
                self._reset_game(names, exps, first)
            else:
                # 房主这边棋盘已经摆好了，只把「等待对手…」换成对方名字
                self.game.names = list(names)
                self.redraw()
                self._update_side()
            self._ai_log("联机开始：对手 %s，我是%s方" % (
                self.net_peer, "白" if self.net_side == 0 else "黑"))
            self._update_status()
            self._autosave()
            self.status.configure(
                text="  联机中：对手「%s」，你是%s方 —— 对方走完你这边会自动更新"
                     % (self.net_peer,
                        "白" if self.net_side == 0 else "黑"))
            return

    def _net_handle_msg(self, msg):
        t = msg.get("t")
        if msg.get("_closed") or t == "bye":
            self.net_close("对方离开了联机", notify=True)
            return
        if t == "error":
            self.net_close("对方说：%s" % (msg.get("why") or "出错了"), notify=True)
            return
        if t == "move":
            self._net_recv_move(msg)
            return
        if t == "pass":
            if self.game.result:
                return
            self.game.turn = 1 - self.game.turn
            self.game.passes = getattr(self.game, "passes", 0) + 1
            self.clear_selection()
            self.redraw()
            self._update_side()
            self.status.configure(
                text="  %s 停一手，轮到 %s"
                     % (self.game.names[1 - self.game.turn],
                        self.game.names[self.game.turn]))
            self._net_check(msg)
            return
        if t == "resign":
            g = self.game
            if g.result:
                return
            g.result = "win"
            g.winner = self.net_side
            g.reason = "对方认输"
            self.redraw()
            self._update_side()
            self._announce()
            self._autosave()
            return
        # 其它类型（比如晚到的 start）忽略

    def _net_recv_move(self, msg):
        g = self.game
        mv = msg.get("mv") or {}
        try:
            m = Move(str(mv["kind"]), int(mv["uid"]), tuple(mv["to"]),
                     frm=tuple(mv["frm"]) if mv.get("frm") else None,
                     aux=int(mv["aux"]) if mv.get("aux") is not None else None)
        except (KeyError, TypeError, ValueError):
            self.net_close("对方发来的着法看不懂，为免下岔先断开")
            return
        if g.result or g.turn == self.net_side:
            self.net_close("两边轮次对不上，为免下岔先断开")
            return
        if not any(x.key() == m.key() for x in g.legal_moves()):
            self.net_close("对方走了一步不合法棋，为免下岔先断开")
            return
        self._play(m, remote=True)
        self._net_check(msg)

    def _net_check(self, msg):
        """比对盘面校验码：对不上说明两边下岔了。"""
        dg = msg.get("dg")
        if dg is None:
            return
        if dg != netlib.position_digest(self.game):
            self.net_close("两边棋盘对不上了（校验码不同），为免下岔先断开")

    def _net_send_move(self, mv: Move):
        sess = self.net
        if sess is None:
            return
        if not sess.send({"t": "move",
                          "n": len(self.game.moves),
                          "mv": {"kind": mv.kind, "uid": mv.uid,
                                 "to": list(mv.to),
                                 "frm": list(mv.frm) if mv.frm else None,
                                 "aux": mv.aux},
                          "dg": netlib.position_digest(self.game)}):
            self.net_close("消息没发出去，连接已经断了")

    def _net_send_pass(self):
        sess = self.net
        if sess is None:
            return
        if not sess.send({"t": "pass", "n": len(self.game.moves),
                          "dg": netlib.position_digest(self.game)}):
            self.net_close("消息没发出去，连接已经断了")

    def net_close(self, why="联机已断开", notify=False):
        """收尾：断开、清状态、把提示写出来。"""
        sess = self.net
        self.net = None
        self.net_peer = ""
        self._net_waiting = ""
        if self.net_room is not None:
            try:
                self.net_room.close()
            except Exception:
                pass
            self.net_room = None
        if sess is not None:
            sess.close(why)
            self._ai_log("联机结束：%s" % why)
            self.status.configure(text="  " + why)
            try:
                self._update_side()
                self.redraw()
            except Exception:
                pass
            if notify:
                messagebox.showwarning("联机中断", why + "\n\n棋盘留在原处，可以存档或复盘。")
        else:
            self._update_status()

    def _net_busy_hint(self):
        """联机时想做不能做的事（悔棋 / 试下）就统一提示。"""
        if self.net is None:
            return False
        self.status.configure(
            text="  联机对战中：悔棋、重做、试下都不能用（会把对方的棋盘搞乱）")
        return True


# --------------------------------------------------------------------- 对话框
def _stamp():
    import time
    return time.strftime("%Y%m%d-%H%M")


class ToggleRow(tk.Frame):
    """自己画的勾选项：选中时填主题色 + 白勾，两套配色下都看得清。"""

    def __init__(self, parent, app, text, variable):
        super().__init__(parent, bg=app.col_dark)
        self.app = app
        self.var = variable
        size = app.px(17)
        self.box = tk.Canvas(self, width=size, height=size, bg=app.col_dark,
                             highlightthickness=0, bd=0)
        self.box.pack(side="left", padx=(app.px(2), app.px(8)))
        self.lab = tk.Label(self, text=text, bg=app.col_dark,
                            fg=app.col_text, font=app.f(9), anchor="w")
        self.lab.pack(side="left")
        for w in (self, self.box, self.lab):
            w.bind("<Button-1>", self._toggle)
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass
        self.var.trace_add("write", lambda *a: self._draw())
        self._draw()

    def _toggle(self, ev=None):
        self.var.set(not bool(self.var.get()))

    def _draw(self):
        app = self.app
        s = app.px(17)
        self.box.delete("all")
        if bool(self.var.get()):
            accent = app._hexc(app.theme.accent)
            self.box.create_rectangle(1, 1, s - 1, s - 1, fill=accent,
                                      outline=accent)
            self.box.create_line(s * 0.24, s * 0.52, s * 0.43, s * 0.72,
                                 s * 0.77, s * 0.30, fill="#FFFFFF",
                                 width=max(2, app.px(2)),
                                 capstyle="round", joinstyle="round")
        else:
            self.box.create_rectangle(1, 1, s - 1, s - 1, fill=app.col_card,
                                      outline=app.col_line)


class ChipRow(tk.Frame):
    """一排可选标签，代替系统单选按钮（系统圆点在不同配色下看不清）。"""

    def __init__(self, parent, app, options, variable, bg=None):
        super().__init__(parent, bg=bg or app.col_dark)
        self.app = app
        self.var = variable
        self.chips = []
        for value, label in options:
            lab = tk.Label(self, text=label, font=app.f(9, True),
                           padx=app.px(12), pady=app.px(5), cursor="hand2")
            lab.pack(side="left", padx=(0, app.px(9)))
            lab.bind("<Button-1>", lambda e, v=value: self.var.set(v))
            self.chips.append((value, lab))
        self.var.trace_add("write", lambda *a: self._style())
        self._style()

    def _style(self):
        app = self.app
        accent = app._hexc(app.theme.accent)
        for value, lab in self.chips:
            if self.var.get() == value:
                lab.configure(bg=accent, fg="#FFFFFF")
            else:
                lab.configure(bg=app.col_card, fg=app.col_text)


class _Dialog(tk.Toplevel):
    def __init__(self, app, title, w, h):
        super().__init__(app.root)
        self.app = app
        self.title(title)
        self.configure(bg=app.col_dark)
        self.transient(app.root)
        self.grab_set()
        self.geometry("%dx%d" % (app.px(w), app.px(h)))
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        ww, wh = app.px(w), app.px(h)
        x = app.root.winfo_rootx() + (app.root.winfo_width() - ww) // 2
        y = app.root.winfo_rooty() + (app.root.winfo_height() - wh) // 3
        self.geometry("+%d+%d" % (max(0, min(x, sw - ww)), max(0, min(y, sh - wh))))


class NewGameDialog(_Dialog):
    def __init__(self, app):
        super().__init__(app, "新对局", 500, 470)
        f, bg, card = app.f, app.col_dark, app.col_card
        tk.Label(self, text="新对局", bg=bg, fg=app.col_text,
                 font=f(14, True)).pack(anchor="w", padx=app.px(22),
                                        pady=(app.px(16), 2))
        tk.Label(self, text="棋子套装与对手", bg=bg, fg=app.col_dim,
                 font=f(9)).pack(anchor="w", padx=app.px(22))

        box = tk.Frame(self, bg=card)
        box.pack(fill="x", padx=app.px(18), pady=app.px(10))
        self.names = []
        for i, lab in ((0, "白方"), (1, "黑方")):
            row = tk.Frame(box, bg=card)
            row.pack(fill="x", padx=app.px(12), pady=app.px(6))
            tk.Label(row, text=lab, bg=card, fg=app.col_dim, font=f(9),
                     width=4, anchor="w").pack(side="left")
            e = tk.Entry(row, bg=app.col_card, fg=app.col_text, bd=0,
                         insertbackground=app.col_text, font=f(10),
                         relief="flat", highlightthickness=1,
                         highlightbackground=app.col_line,
                         highlightcolor=app._hexc(app.theme.accent))
            e.insert(0, app.game.names[i])
            e.pack(side="left", fill="x", expand=True, ipady=app.px(3),
                   padx=(app.px(6), 0))
            self.names.append(e)

        tk.Label(self, text="扩展棋子", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(22),
                                       pady=(app.px(8), 2))
        ex = tk.Frame(self, bg=bg)
        ex.pack(fill="x", padx=app.px(18))
        self.exp = {}
        for k in ("ladybug", "mosquito", "pillbug"):
            v = tk.BooleanVar(value=k in app.game.expansions)
            ToggleRow(ex, app, "%s · %s" % (KIND_NAMES[k], KIND_DESC[k]),
                      v).pack(anchor="w", pady=app.px(1))
            self.exp[k] = v

        tk.Label(self, text="对手", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(22),
                                       pady=(app.px(12), 2))
        opp = tk.Frame(self, bg=bg)
        opp.pack(fill="x", padx=app.px(18))
        self.mode = tk.StringVar(value=app.versus)
        self.level = tk.IntVar(value=app.ai_level)
        self.first = tk.IntVar(value=int(app.settings.get("first", 0)) % 2)
        ChipRow(opp, app, [("human", "两人对战"), ("ai", "人机对战")],
                self.mode, bg).pack(side="left")
        lv = tk.Frame(self, bg=bg)
        lv.pack(fill="x", padx=app.px(18), pady=(app.px(6), 0))
        ChipRow(lv, app, [(1, "简单"), (2, "普通"), (3, "困难")],
                self.level, bg).pack(side="left")

        tk.Label(self, text="先手", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(22),
                                       pady=(app.px(10), 2))
        fst = tk.Frame(self, bg=bg)
        fst.pack(fill="x", padx=app.px(18))
        ChipRow(fst, app, [(0, "白方先"), (1, "黑方先")], self.first,
                bg).pack(side="left")
        tk.Label(fst, text="人机对战时选「黑方先」就是电脑先走", bg=bg,
                 fg=app.col_dim, font=f(8)).pack(side="left",
                                                 padx=(app.px(10), 0))

        bar = tk.Frame(self, bg=bg)
        bar.pack(side="bottom", fill="x", padx=app.px(18), pady=app.px(16))
        app._button(bar, "开始对局", self.ok).pack(side="right",
                                                   padx=(app.px(8), 0))
        app._button(bar, "取消", self.destroy).pack(side="right")
        app._button(bar, "继续上次", self.resume).pack(side="left")

    def ok(self):
        names = [e.get().strip() or d for e, d in zip(self.names, ("白方", "黑方"))]
        exps = [k for k, v in self.exp.items() if v.get()]
        self.destroy()
        self.app.start_new(names, exps, self.mode.get(), self.level.get(), 1,
                           int(self.first.get()))

    def resume(self):
        self.destroy()
        p = store.autosave_path()
        if not os.path.exists(p):
            messagebox.showinfo("继续对局", "没有找到自动存档。")
            return
        self.app._load_path(p)


class NetDialog(_Dialog):
    """联机对战：开房（房主）或加入（客人）。同一 WiFi / 异地组网工具下直连。"""

    def __init__(self, app):
        super().__init__(app, "联机对战", 500, 560)
        f, bg = app.f, app.col_dark
        self.settings = app.settings
        tk.Label(self, text="联机对战", bg=bg, fg=app.col_text,
                 font=f(14, True)).pack(anchor="w", padx=app.px(22),
                                        pady=(app.px(16), 2))
        tk.Label(self, text="两个人各自开一个程序：房主点「开房」，把屏幕上的 "
                           "IP:端口 告诉对方；对方点「加入」填进来。",
                 bg=bg, fg=app.col_dim, font=f(9), justify="left",
                 wraplength=app.px(430)).pack(anchor="w", padx=app.px(22))

        tk.Label(self, text="身份", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(22),
                                       pady=(app.px(12), 2))
        idf = tk.Frame(self, bg=bg)
        idf.pack(fill="x", padx=app.px(18))
        self.mode = tk.StringVar(value="host")
        ChipRow(idf, app, [("host", "开房（我当房主）"),
                           ("join", "加入（连房主）")], self.mode, bg).pack(side="left")

        tk.Label(self, text="我的名字", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(22),
                                       pady=(app.px(10), 2))
        row = tk.Frame(self, bg=bg)
        row.pack(fill="x", padx=app.px(18))
        self.name = tk.Entry(row, bg=app.col_card, fg=app.col_text, bd=0,
                             insertbackground=app.col_text, font=f(10),
                             relief="flat", highlightthickness=1,
                             highlightbackground=app.col_line,
                             highlightcolor=app._hexc(app.theme.accent))
        self.name.insert(0, app.settings.get("net_name")
                         or app.game.names[0] or "玩家")
        self.name.pack(fill="x", ipady=app.px(3), padx=app.px(12))

        # --- 「加入」才要填的：房主 IP
        self.joinbox = tk.Frame(self, bg=bg)
        tk.Label(self.joinbox, text="房主的 IP", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(4),
                                       pady=(app.px(10), 2))
        self.ip = tk.Entry(self.joinbox, bg=app.col_card, fg=app.col_text,
                           bd=0, insertbackground=app.col_text, font=f(10),
                           relief="flat", highlightthickness=1,
                           highlightbackground=app.col_line,
                           highlightcolor=app._hexc(app.theme.accent))
        self.ip.insert(0, str(app.settings.get("net_ip") or ""))
        self.ip.pack(fill="x", ipady=app.px(3))

        # --- 端口（两边都要对得上）
        self.portbox = tk.Frame(self, bg=bg)
        tk.Label(self.portbox, text="端口", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(4),
                                       pady=(app.px(10), 2))
        self.port = tk.Entry(self.portbox, bg=app.col_card, fg=app.col_text,
                             bd=0, insertbackground=app.col_text, font=f(10),
                             relief="flat", highlightthickness=1,
                             highlightbackground=app.col_line,
                             highlightcolor=app._hexc(app.theme.accent))
        self.port.insert(0, str(int(app.settings.get("net_port", 8765))))
        self.port.pack(fill="x", ipady=app.px(3))

        # --- 「开房」才要用的：扩展 + 先手（客人以房主为准）
        self.hostbox = tk.Frame(self, bg=bg)
        tk.Label(self.hostbox, text="扩展棋子", bg=bg, fg=app.col_dim,
                 font=f(9, True)).pack(anchor="w", padx=app.px(4),
                                       pady=(app.px(10), 2))
        self.exp = {}
        for k in ("ladybug", "mosquito", "pillbug"):
            v = tk.BooleanVar(value=k in app.game.expansions)
            ToggleRow(self.hostbox, app, "%s · %s" % (KIND_NAMES[k], KIND_DESC[k]),
                      v).pack(anchor="w", pady=app.px(1))
            self.exp[k] = v
        tk.Label(self.hostbox, text="先手（房主执白，这里选白先还是黑先）",
                 bg=bg, fg=app.col_dim, font=f(9, True)).pack(
            anchor="w", padx=app.px(4), pady=(app.px(8), 2))
        self.first = tk.IntVar(value=int(app.settings.get("first", 0)) % 2)
        fst = tk.Frame(self.hostbox, bg=bg)
        fst.pack(anchor="w")
        ChipRow(fst, app, [(0, "白方先"), (1, "黑方先")], self.first,
                bg).pack(side="left")

        bar = tk.Frame(self, bg=bg)
        bar.pack(side="bottom", fill="x", padx=app.px(18), pady=app.px(16))
        app._button(bar, "开始", self.ok).pack(side="right",
                                              padx=(app.px(8), 0))
        app._button(bar, "取消", self.destroy).pack(side="right")

        self._sync()
        self.mode.trace_add("write", lambda *a: self._sync())

    def _sync(self):
        """按身份显示不同的输入框（顺便把窗口高度收紧，不留大白边）。"""
        host = self.mode.get() == "host"
        self.joinbox.pack_forget()
        self.hostbox.pack_forget()
        self.portbox.pack_forget()
        if host:
            self.portbox.pack(fill="x", padx=self.app.px(18))
            self.hostbox.pack(fill="x", padx=self.app.px(18))
        else:
            self.joinbox.pack(fill="x", padx=self.app.px(18))
            self.portbox.pack(fill="x", padx=self.app.px(18))
        try:
            self.geometry("%dx%d" % (self.app.px(500),
                                     self.app.px(500 if host else 420)))
        except tk.TclError:
            pass

    def ok(self):
        name = self.name.get().strip() or "玩家"
        try:
            port = int(self.port.get().strip())
        except ValueError:
            messagebox.showinfo("端口不对", "端口要填数字，比如 8765。")
            return
        if not (1 <= port <= 65535):
            messagebox.showinfo("端口不对", "端口要在 1~65535 之间，比如 8765。")
            return
        self.settings["net_name"] = name
        self.settings["net_port"] = port
        if self.mode.get() == "join":
            ip = self.ip.get().strip()
            if not ip:
                messagebox.showinfo("缺 IP", "要填房主屏幕上的那个 IP，比如 192.168.1.23。")
                return
            self.settings["net_ip"] = ip
            store.save_settings(self.settings)
            self.destroy()
            self.app.net_join(ip, port, name)
            return
        exps = [k for k, v in self.exp.items() if v.get()]
        first = int(self.first.get())
        self.settings["first"] = first
        store.save_settings(self.settings)
        self.destroy()
        self.app.net_host(name, exps, first, port)


class RulesDialog(_Dialog):
    def _insert_figures(self, txt):
        """把规则示意图插到说明文字后面。只留一巢那张图。"""
        try:
            from PIL import Image
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "assets")
            figs = [("rule_chain.png",
                     "图解　一条链被两端封住：中间的棋子抬起来就断巢（一巢规则），"
                     "整串全成了死子。这是最该避免的形状。")]
            txt.insert("end", "\n\n【图解】\n")
            self._figs = []
            for name, cap in figs:
                p = os.path.join(base, name)
                if not os.path.exists(p):
                    continue
                im = Image.open(p)
                im.thumbnail((int(600 * self.app.s), int(420 * self.app.s)))
                ph = ImageTk.PhotoImage(im)
                self._figs.append(ph)
                txt.insert("end", "\n")
                txt.image_create("end", image=ph, padx=self.app.px(8),
                                 pady=self.app.px(8))
                txt.insert("end", "\n" + cap + "\n")
        except Exception:
            pass

    TEXT = """【目标】
把对手的蜂后（Q）四周六个格子全部占满，即获胜。

【每回合二选一】
· 从手里落一枚新棋子；
· 或移动棋盘上的一枚棋子。

【落子规矩】
· 第一枚棋子下在中央，之后必须贴着已有的蜂巢。
· 双方都下过第一枚之后：新棋子必须贴着自己的棋子，
  且不能碰到对手的棋子（只看一堆棋子最上面那枚的颜色）。
· 蜂后必须在前 4 个回合内落下。
· 蜂后没落下之前，不能移动任何棋子。

【两条铁律】
· 一巢：任何时候所有棋子必须连成一体。抬起一枚棋子若会把
  蜂巢分成两半，这枚棋子就不能动。
· 自由移动：棋子只能「滑」，不能拿起来放。滑进相邻格时，要
  挤过两格共用的那条边；这条边的两个端点各还挨着第三个格子。
  ★ 只有「门的两侧」同时被棋子占住，才算「窄门」，挤不过去；
  只被一侧挡着时，棋子可以侧身让过去。

  这条对所有「滑行」的棋子都生效 —— 蜂后、兵蚁、蜘蛛、甲虫
  （在地面滑行时）、瓢虫（落地那一步）、鼠妇、以及复制它们
  走法的蚊子。

  ★ 只有蚱蜢例外：它是「跳」的，不受窄门限制。

  典型后果：一枚棋子的每个出口，两侧都被塞满时，它一步也动
  不了 —— 蜂后被「两枚棋子夹在角上」就是这么被钉死的。

【各种虫子的走法】
蜂后 Q   每次走一格。
甲虫 B   走一格，可以爬到别的棋子顶上，也可以从顶上下来。
         在顶上时可以盖住下面的棋子（被压住的棋子不能动）。
蜘蛛 S   沿蜂巢边缘滑行整三步，不能多也不能少。
蚱蜢 G   朝一个方向跳过一串连续的棋子，落在它们后面第一个空格。
兵蚁 A   沿蜂巢边缘滑行任意步。
瓢虫 L   先爬上蜂巢走两步，第三步落回地面的空格（扩展）。
蚊子 M   复制相邻棋子的走法（扩展）。
鼠妇 P   走一格；还能把贴着它的一枚棋子搬到自己另一侧的空格（扩展）。

【联机对战】
顶栏「联机」：两个人各自开一个程序，房主点「开房」，把屏幕上
的 IP:端口 告诉对方；对方点「加入」，把 IP 和端口填进来就行。
· 同一个 WiFi 直接能连；不在同一个网里，就用异地组网工具（或
  让懂网络的人做一次端口映射）把两台电脑放进同一个网络。
· 房主执白、客人执黑；谁先走由房主在「开房」时选。
· 联机时不能悔棋、重做、试下 —— 会把对方的棋盘搞乱。
· 每走一步两边都用校验码核对一次，对不上立刻停下，绝不把棋下岔。
· 谁中途断线，另一边的棋盘留在原处，可以存档或复盘。

【和棋】
同一局面出现三次判和。

【快捷键】
Ctrl+Z 悔棋   Ctrl+Y 重做   Ctrl+S 存档   Ctrl+O 读档
Ctrl+N 新局   Ctrl+H 提示   Esc 取消选择   F5 换配色
"""

    def __init__(self, app):
        super().__init__(app, "规则说明", 640, 640)
        self.resizable(True, True)
        tk.Label(self, text="规则说明", bg=app.col_dark, fg=app.col_text,
                 font=app.f(14, True)).pack(anchor="w", padx=app.px(20),
                                            pady=(app.px(16), app.px(6)))
        wrap = tk.Frame(self, bg=app.col_card)
        wrap.pack(fill="both", expand=True, padx=app.px(16),
                  pady=(0, app.px(16)))
        txt = tk.Text(wrap, bg=app.col_card, fg=app.col_text, bd=0,
                      highlightthickness=0, font=app.f(10), wrap="word",
                      padx=app.px(16), pady=app.px(12), spacing1=3, spacing3=3)
        sb = tk.Scrollbar(wrap, command=txt.yview, width=app.px(10))
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", self.TEXT)
        self._insert_figures(txt)
        txt.configure(state="disabled")


def main():
    enable_dpi()
    root = tk.Tk()
    app = HiveApp(root)

    def bye():
        try:
            app.settings["geometry"] = root.geometry()
            store.save_settings(app.settings)
        except Exception:
            pass
        app._autosave()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", bye)
    root.mainloop()










