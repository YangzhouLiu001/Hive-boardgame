# -*- coding: utf-8 -*-
"""棋子美术：用 Pillow 以 3~4 倍超采样绘制，再缩小得到平滑边缘。

所有绘制都在“单位坐标”里进行：以棋子中心为原点，六边形外接圆半径 = 1，
y 轴向下，虫子的头朝上（负 y）。
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

SS = 4                      # 超采样倍数
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
SQ3 = math.sqrt(3.0)
HEX_H = SQ3 / 2.0           # 平顶六边形半高（相对于外接圆半径）


# ----------------------------------------------------------------- 颜色工具
def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def shade(c, f):
    """f<1 变暗，f>1 变亮。"""
    return tuple(max(0, min(255, int(round(v * f)))) for v in c)


class Theme:
    def __init__(self, key, name, bg, bg2, p1, p2, accent, chrome,
                 pattern=9, felt=0.0):
        self.key = key
        self.name = name
        self.bg = bg
        self.bg2 = bg2
        self.p1 = p1            # 白方配色
        self.p2 = p2            # 黑方配色
        self.accent = accent
        self.chrome = chrome     # 界面外壳配色
        self.pattern = pattern   # 桌面蜂窝纹的透明度
        self.felt = felt         # 桌面绒毛噪点强度


def _side(top, bot, rim, dark=False):
    """一枚砖的底色。昆虫自己另有配色，不随砖色变化。"""
    return {"top": _hex(top), "bot": _hex(bot), "rim": _hex(rim),
            "dark": bool(dark),
            "wing": lerp(_hex(top), (255, 255, 255), 0.75 if dark else 0.55)}


# 每种昆虫自己的颜色（原版 Hive 的做法：白砖 / 黑砖，虫子都上色）
KIND_BASE = {
    "queen": "#E5A82B",         # 蜂后：金黄
    "ant": "#B45A31",           # 兵蚁：赭红
    "spider": "#7A56A8",        # 蜘蛛：紫
    "beetle": "#2F6FB5",        # 甲虫：蓝
    "grasshopper": "#4C9B3F",   # 蚱蜢：绿
    "ladybug": "#CE3A2E",       # 瓢虫：红
    "mosquito": "#2B8F86",      # 蚊子：青
    "pillbug": "#9A7B4F",       # 鼠妇：褐
}


def bug_colors(kind, dark_tile):
    base = _hex(KIND_BASE.get(kind, "#444444"))
    body = lerp(base, (255, 255, 255), 0.22) if dark_tile else base
    return body, shade(body, 0.70)


def _chrome(bar, bar_ink, bar_hover, panel, panel_ink, panel_dim, card, line,
            w_ink, b_ink):
    return {"bar": bar, "bar_ink": bar_ink, "bar_hover": bar_hover,
            "panel": panel, "panel_ink": panel_ink, "panel_dim": panel_dim,
            "card": card, "line": line, "w_ink": w_ink, "b_ink": b_ink}


THEMES = [
    # 麻将：绿呢桌面 + 奶白砖 / 墨黑砖
    Theme("mahjong", "麻将",
          "#35714F", "#1C4530",
          _side("#FFFDF5", "#EFE6D0", "#C6B993"),
          _side("#3B3B40", "#141416", "#6E6E76", dark=True),
          _hex("#D8402F"),
          _chrome("#F6EEDC", "#2C2419", "#E6D9BC", "#F1E8D5", "#2C2419",
                  "#8D7C5C", "#FBF6EA", "#DDCDA9", "#1E5A44", "#8A5A2B"),
          pattern=10, felt=9.0),
    # 蜜蜡：暖木桌面
    Theme("amber", "蜜蜡",
          "#55432F", "#2A2018",
          _side("#FCF5E6", "#E4D2AC", "#B99B62"),
          _side("#40372F", "#1B1713", "#6E6053", dark=True),
          _hex("#E8B33A"),
          _chrome("#F0E4CB", "#33291B", "#E0D0B2", "#3B3128", "#F3E8D4",
                  "#A9977A", "#4A3E32", "#5B4C3D", "#F3E8D4", "#D9B870"),
          pattern=9, felt=0.0),
    # 青瓷：明亮清爽
    Theme("porcelain", "青瓷",
          "#CFE3D8", "#A8C6B7",
          _side("#FFFFFF", "#E8F1EC", "#A9C4B8"),
          _side("#3A4048", "#1B1F24", "#717A85", dark=True),
          _hex("#C0523C"),
          _chrome("#F7F4EC", "#2A3A33", "#E8E2D4", "#EFEDE4", "#2A3A33",
                  "#7E8C85", "#FFFFFF", "#D6D3C4", "#1F5545", "#333B44"),
          pattern=14, felt=0.0),
    # 墨玉：深色经典
    Theme("classic", "墨玉",
          "#2F2A25", "#151211",
          _side("#FFFFFF", "#DBDBDB", "#9A9A9A"),
          _side("#2A2A2A", "#0C0C0C", "#5C5C5C", dark=True),
          _hex("#7FA8D9"),
          _chrome("#1B1713", "#F0E6D6", "#3A3129", "#241E19", "#F0E6D6",
                  "#A2937F", "#2E2722", "#3B332B", "#F0E6D6", "#A9C0D8"),
          pattern=9, felt=0.0),
]

THEME_BY_KEY = {t.key: t for t in THEMES}


# ----------------------------------------------------------------- 画布
class Pen:
    """单位坐标 -> 像素坐标的画笔。"""

    def __init__(self, draw: ImageDraw.ImageDraw, cx, cy, r):
        self.d = draw
        self.cx = cx
        self.cy = cy
        self.r = r

    def P(self, x, y):
        return (self.cx + x * self.r, self.cy + y * self.r)

    def poly(self, pts, fill=None, outline=None, width=0):
        self.d.polygon([self.P(*p) for p in pts], fill=fill, outline=outline,
                       width=max(1, int(width * self.r)) if outline else 0)

    def line(self, pts, color, width, joint="curve", cap=True):
        w = max(1, int(round(width * self.r)))
        self.d.line([self.P(*p) for p in pts], fill=color, width=w, joint=joint)
        if cap and w > 2:
            rr = w / 2.0
            for p in (pts[0], pts[-1]):
                px, py = self.P(*p)
                self.d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=color)

    def ell(self, cx, cy, rx, ry, fill=None, outline=None, width=0, angle=0.0):
        pts = ell_poly(cx, cy, rx, ry, angle)
        self.poly(pts, fill=fill, outline=outline, width=width)

    def dot(self, cx, cy, r, fill):
        self.d.ellipse([self.P(cx - r, cy - r), self.P(cx + r, cy + r)], fill=fill)

    def band(self, cx, cy, rx, ry, y0, y1, fill):
        """椭圆内、y0..y1 之间的横向色带（用于蜂后/瓢虫的条纹）。"""
        pts = []
        n = 14
        y = y0
        for i in range(n + 1):
            yy = y0 + (y1 - y0) * i / n
            t = (yy - cy) / ry
            if abs(t) > 1:
                continue
            hw = rx * math.sqrt(1 - t * t)
            pts.append((cx + hw, yy))
        for i in range(n + 1):
            yy = y1 - (y1 - y0) * i / n
            t = (yy - cy) / ry
            if abs(t) > 1:
                continue
            hw = rx * math.sqrt(1 - t * t)
            pts.append((cx - hw, yy))
        if len(pts) >= 3:
            self.poly(pts, fill=fill)


def ell_poly(cx, cy, rx, ry, angle=0.0, n=44):
    ca, sa = math.cos(angle), math.sin(angle)
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x = rx * math.cos(a)
        y = ry * math.sin(a)
        out.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return out


def arc_pts(cx, cy, rx, ry, a0, a1, n=24):
    out = []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        out.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return out


# ----------------------------------------------------------------- 虫子图案
def draw_queen(pen, ink, ink2, wing):
    """蜂后：粗条纹腹部 + 双翅 + 触角。"""
    # 翅膀（先画，压在身体下面）：向后斜掠
    for sgn in (-1, 1):
        pts = ell_poly(sgn * 0.33, -0.06, 0.31, 0.125, sgn * 0.95)
        pen.poly(pts, fill=wing, outline=ink, width=0.028)
    # 腹部
    pen.ell(0, 0.26, 0.27, 0.31, fill=ink)
    for y0, y1 in ((0.14, 0.21), (0.26, 0.33), (0.38, 0.45)):
        pen.band(0, 0.26, 0.27, 0.31, y0, y1, ink2)
    # 尾针
    pen.line([(0, 0.53), (0, 0.66)], ink, 0.045)
    # 胸
    pen.ell(0, -0.14, 0.165, 0.15, fill=ink2)
    # 头
    pen.dot(0, -0.36, 0.125, ink)
    # 触角
    for sgn in (-1, 1):
        pen.line([(sgn * 0.06, -0.44), (sgn * 0.19, -0.55), (sgn * 0.25, -0.47)],
                 ink, 0.042)
    # 腿
    for sgn in (-1, 1):
        for dy, kx, ky in ((-0.22, 0.34, 0.02), (-0.13, 0.38, 0.14), (-0.04, 0.35, 0.26)):
            pen.line([(sgn * 0.13, dy), (sgn * kx, ky)], ink, 0.05)


def draw_ant(pen, ink, ink2, wing):
    """兵蚁：三节身体 + 六足 + 大颚。"""
    for sgn in (-1, 1):
        for dy, kx, ky, ex, ey in ((-0.04, 0.34, -0.22, 0.44, -0.30),
                                   (0.02, 0.40, 0.02, 0.50, 0.06),
                                   (0.08, 0.34, 0.24, 0.42, 0.40)):
            pen.line([(sgn * 0.10, dy), (sgn * kx, ky), (sgn * ex, ey)], ink, 0.05)
    # 腹部
    pen.ell(0, 0.34, 0.225, 0.245, fill=ink)
    # 腰
    pen.line([(0, 0.16), (0, 0.08)], ink, 0.06)
    # 胸
    pen.ell(0, -0.02, 0.125, 0.145, fill=ink2)
    # 头
    pen.dot(0, -0.26, 0.17, ink)
    # 大颚
    for sgn in (-1, 1):
        pen.poly([(sgn * 0.03, -0.38), (sgn * 0.16, -0.46), (sgn * 0.07, -0.33)],
                 fill=ink)
    # 触角
    for sgn in (-1, 1):
        pen.line([(sgn * 0.07, -0.37), (sgn * 0.22, -0.50), (sgn * 0.30, -0.42)],
                 ink, 0.038)


def draw_spider(pen, ink, ink2, wing):
    """蜘蛛：圆腹 + 八条折角长腿。"""
    legs = [((0.07, -0.18), (0.34, -0.52), (0.60, -0.44)),
            ((0.11, -0.10), (0.46, -0.26), (0.64, -0.06)),
            ((0.11, 0.02), (0.48, 0.06), (0.62, 0.26)),
            ((0.08, 0.12), (0.36, 0.30), (0.52, 0.54))]
    for sgn in (-1, 1):
        for a, b, c in legs:
            pen.line([(sgn * a[0], a[1]), (sgn * b[0], b[1]), (sgn * c[0], c[1])],
                     ink, 0.055)
            pen.dot(sgn * b[0], b[1], 0.045, ink)
    # 腹部
    pen.ell(0, 0.30, 0.27, 0.29, fill=ink)
    # 背纹
    pen.ell(0, 0.26, 0.13, 0.085, fill=ink2)
    # 头胸部
    pen.ell(0, -0.10, 0.20, 0.21, fill=ink)
    for sgn in (-1, 1):
        pen.dot(sgn * 0.08, -0.22, 0.038, ink2)
        pen.dot(sgn * 0.15, -0.14, 0.027, ink2)
    # 螯肢
    for sgn in (-1, 1):
        pen.line([(sgn * 0.05, -0.28), (sgn * 0.06, -0.40)], ink, 0.05)


def draw_beetle(pen, ink, ink2, wing):
    """甲虫：圆顶硬鞘 + 中缝 + 鹿角状大颚。"""
    for sgn in (-1, 1):
        for dy, kx, ky in ((-0.22, 0.42, -0.34), (-0.02, 0.50, 0.00), (0.16, 0.44, 0.32)):
            pen.line([(sgn * 0.20, dy), (sgn * kx, ky),
                      (sgn * (kx - 0.05), ky + 0.22)], ink, 0.062)
    # 鞘翅
    pen.ell(0, 0.14, 0.335, 0.40, fill=ink)
    # 中缝
    pen.line([(0, -0.20), (0, 0.54)], ink2, 0.045)
    # 前胸背板
    pen.ell(0, -0.24, 0.255, 0.155, fill=ink2)
    # 头
    pen.ell(0, -0.42, 0.125, 0.10, fill=ink)
    # 大颚
    for sgn in (-1, 1):
        pen.line([(sgn * 0.08, -0.46), (sgn * 0.18, -0.58), (sgn * 0.09, -0.62)],
                 ink, 0.055)
    for sgn in (-1, 1):
        pen.line([(sgn * 0.12, -0.40), (sgn * 0.28, -0.50)], ink2, 0.04)


def draw_grasshopper(pen, ink, ink2, wing):
    """蚱蜢：细长身体 + 折叠的粗壮后腿。"""
    # 后腿（大 Z 字折叠）
    for sgn in (-1, 1):
        pen.line([(sgn * 0.09, -0.04), (sgn * 0.52, -0.20),
                  (sgn * 0.30, 0.46)], ink, 0.09)
        pen.dot(sgn * 0.52, -0.20, 0.055, ink)
        pen.line([(sgn * 0.30, 0.46), (sgn * 0.40, 0.58)], ink2, 0.032)
    # 前中腿
    for sgn in (-1, 1):
        pen.line([(sgn * 0.08, -0.20), (sgn * 0.32, -0.32), (sgn * 0.38, -0.16)],
                 ink, 0.042)
        pen.line([(sgn * 0.08, -0.04), (sgn * 0.30, 0.02), (sgn * 0.36, 0.20)],
                 ink, 0.042)
    # 身体
    pen.ell(0, 0.10, 0.115, 0.40, fill=ink)
    pen.line([(0, -0.26), (0, 0.46)], ink2, 0.028)
    # 头
    pen.ell(0, -0.34, 0.15, 0.145, fill=ink)
    # 触角
    for sgn in (-1, 1):
        pen.line([(sgn * 0.08, -0.44), (sgn * 0.22, -0.60), (sgn * 0.36, -0.64)],
                 ink, 0.038)


def draw_ladybug(pen, ink, ink2, wing):
    """瓢虫：圆顶 + 中缝 + 七个圆点。"""
    for sgn in (-1, 1):
        for dy, kx, ky in ((-0.16, 0.38, -0.26), (0.00, 0.46, 0.02), (0.18, 0.38, 0.30)):
            pen.line([(sgn * 0.15, dy), (sgn * kx, ky),
                      (sgn * (kx - 0.03), ky + 0.20)], ink, 0.055)
    # 圆顶
    pen.ell(0, 0.08, 0.40, 0.42, fill=ink)
    # 中缝
    pen.line([(0, -0.30), (0, 0.49)], ink2, 0.04)
    # 前胸背板
    pen.ell(0, -0.26, 0.24, 0.14, fill=ink2)
    # 头
    pen.dot(0, -0.40, 0.095, ink)
    pen.line([(0, -0.44), (0, -0.50)], ink, 0.05)
    for sgn in (-1, 1):
        pen.line([(sgn * 0.05, -0.44), (sgn * 0.16, -0.54)], ink, 0.035)
    # 斑点
    for sx, sy, sr in ((-0.20, -0.02, 0.072), (0.20, -0.02, 0.072),
                       (-0.25, 0.24, 0.068), (0.25, 0.24, 0.068),
                       (-0.09, 0.42, 0.058), (0.09, 0.42, 0.058)):
        pen.dot(sx, sy, sr, ink2)


def draw_mosquito(pen, ink, ink2, wing):
    """蚊子：极细的针状身体 + 长腿 + 口器。"""
    for sgn in (-1, 1):
        for dy, kx, ky, ex, ey in ((-0.08, 0.30, -0.44, 0.46, -0.30),
                                   (0.00, 0.34, -0.14, 0.52, 0.06),
                                   (0.06, 0.30, 0.16, 0.44, 0.46)):
            pen.line([(sgn * 0.06, dy), (sgn * kx, ky), (sgn * ex, ey)], ink, 0.038)
    # 翅膀
    for sgn in (-1, 1):
        pts = ell_poly(sgn * 0.26, -0.06, 0.26, 0.085, sgn * 0.5)
        pen.poly(pts, fill=wing, outline=ink, width=0.025)
    # 腹部（细长）
    pen.poly([(-0.075, 0.10), (0.075, 0.10), (0.0, 0.60)], fill=ink)
    pen.ell(0, 0.03, 0.075, 0.085, fill=ink2)
    # 头
    pen.dot(0, -0.22, 0.105, ink)
    # 口器
    pen.line([(0, -0.30), (0, -0.62)], ink, 0.03)
    for sgn in (-1, 1):
        pen.line([(sgn * 0.06, -0.28), (sgn * 0.20, -0.44), (sgn * 0.28, -0.36)],
                 ink, 0.03)


def draw_pillbug(pen, ink, ink2, wing):
    """鼠妇：卵形身体 + 一层层甲片。"""
    for sgn in (-1, 1):
        for dy, ey in ((-0.12, 0.00), (0.02, 0.14), (0.16, 0.26)):
            pen.line([(sgn * 0.30, dy), (sgn * 0.45, ey)], ink, 0.045)
    # 身体
    pen.ell(0, 0.12, 0.35, 0.44, fill=ink)
    # 甲片弧线
    for y, bow in ((-0.18, 0.045), (-0.02, 0.055), (0.14, 0.065), (0.30, 0.065)):
        t = (y - 0.12) / 0.44
        if abs(t) >= 1:
            continue
        hw = 0.35 * math.sqrt(1 - t * t) * 0.95
        pts = []
        for i in range(13):
            x = -hw + 2 * hw * i / 12
            pts.append((x, y + bow * (1 - (x / hw) ** 2)))
        pen.line(pts, ink2, 0.028)
    # 头
    pen.ell(0, -0.34, 0.195, 0.125, fill=ink2)
    for sgn in (-1, 1):
        pen.line([(sgn * 0.13, -0.42), (sgn * 0.29, -0.54), (sgn * 0.37, -0.46)],
                 ink, 0.034)


DRAWERS = {
    "queen": draw_queen,
    "ant": draw_ant,
    "spider": draw_spider,
    "beetle": draw_beetle,
    "grasshopper": draw_grasshopper,
    "ladybug": draw_ladybug,
    "mosquito": draw_mosquito,
    "pillbug": draw_pillbug,
}


# ----------------------------------------------------------------- 六边形
def hex_points(cx, cy, r, flat_top=True):
    """平顶六边形：顶点在左右两侧。"""
    pts = []
    for i in range(6):
        a = math.pi / 3.0 * i
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def hex_mask(w, h, cx, cy, r, ss=1):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(hex_points(cx, cy, r), fill=255)
    return m


# ----------------------------------------------------------------- 棋子贴图
def render_piece(kind, owner, theme: Theme, r=52, ss=SS, shadow=True,
                 highlight=True):
    """渲染一枚棋子，返回 RGBA 图片以及“中心点”在图中的位置。"""
    side = theme.p1 if owner == 0 else theme.p2
    pad = r * (0.30 if shadow else 0.10)
    w = int(round((2 * r + 2 * pad) * ss))
    h = int(round((2 * HEX_H * r + 2 * pad) * ss))
    cx = w / 2.0
    cy = h / 2.0
    R = r * ss

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # --- 投影
    if shadow:
        sh = Image.new("L", (w, h), 0)
        off = r * 0.07 * ss
        ImageDraw.Draw(sh).polygon(
            hex_points(cx + off * 0.6, cy + off, R * 0.98), fill=150)
        sh = sh.filter(ImageFilter.GaussianBlur(r * 0.10 * ss))
        black = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        img.paste(black, (0, 0), sh)

    # --- 渐变色块
    mask = hex_mask(w, h, cx, cy, R)
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    y0 = cy - R * HEX_H
    y1 = cy + R * HEX_H
    span = max(1, int(y1 - y0))
    for i in range(span):
        t = i / span
        # 顶部稍亮，底部压暗
        col = lerp(side["top"], side["bot"], t ** 0.85)
        gd.line([(0, y0 + i), (w, y0 + i)], fill=col)
    body = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    body.paste(grad, (0, 0), mask)
    img.alpha_composite(body)

    # --- 顶部高光
    if highlight:
        hl = Image.new("L", (w, h), 0)
        ImageDraw.Draw(hl).ellipse(
            [cx - R * 0.78, cy - R * 0.92, cx + R * 0.78, cy + R * 0.10], fill=48)
        hl = hl.filter(ImageFilter.GaussianBlur(R * 0.16))
        white = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        img.paste(white, (0, 0), hl)

    # --- 描边（外圈深、内圈亮，做出倒角）
    d = ImageDraw.Draw(img)
    d.line(hex_points(cx, cy, R) + [hex_points(cx, cy, R)[0]],
           fill=side["rim"], width=max(1, int(R * 0.045)), joint="curve")
    inner = hex_points(cx, cy, R * 0.955)
    d.line(inner + [inner[0]], fill=lerp(side["rim"], (255, 255, 255), 0.45),
           width=max(1, int(R * 0.022)), joint="curve")

    # --- 虫子（颜色由昆虫种类决定，与砖色无关）
    body, detail = bug_colors(kind, side["dark"])
    pen = Pen(ImageDraw.Draw(img), cx, cy, R * 1.0)
    DRAWERS[kind](pen, body, detail, side["wing"])

    if ss != 1:
        img = img.resize((max(1, w // ss), max(1, h // ss)), LANCZOS)
        cx, cy = cx / ss, cy / ss
    return img, (cx, cy)


def render_background(w, h, theme: Theme, cell=None):
    """棋盘底：渐变 + 极淡的蜂窝纹 + 绒毛噪点 + 暗角。"""
    if cell is None:
        cell = max(34, int(min(w, h) / 20))
    img = Image.new("RGB", (w, h), _hex(theme.bg2))
    d = ImageDraw.Draw(img)

    # 垂直渐变
    c1, c2 = _hex(theme.bg), _hex(theme.bg2)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(c1, c2, y / max(1, h - 1)))

    # 绒毛噪点（麻将桌的绿呢）
    if getattr(theme, "felt", 0):
        try:
            n = Image.effect_noise((w, h), theme.felt).convert("L")
            noise = Image.merge("RGB", (n, n, n))
            img = Image.blend(img, noise, 0.045)
        except Exception:
            pass

    # 蜂窝纹
    if theme.pattern:
        pat = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pat)
        step = cell * 1.5
        row = 0
        y = -cell
        a = theme.pattern
        while y < h + cell:
            x = -cell + (step / 2 if row % 2 else 0)
            while x < w + cell:
                pd.polygon(hex_points(x, y, cell),
                           outline=(255, 255, 255, a), width=1)
                x += step
            y += cell * HEX_H
            row += 1
        img = Image.alpha_composite(img.convert("RGBA"), pat).convert("RGB")

    # 暗角
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.35],
                                fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(min(w, h) * 0.10))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, 0.30), vig)


def render_marker(color, r=8, ss=6, ring=False, width=2.2):
    """落点提示：实心圆点或圆环。"""
    size = int(round((r * 2 + 8) * ss))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2.0
    if ring:
        d.ellipse([c - r * ss, c - r * ss, c + r * ss, c + r * ss],
                  outline=color, width=max(1, int(width * ss)))
    else:
        d.ellipse([c - r * ss, c - r * ss, c + r * ss, c + r * ss], fill=color)
    return img.resize((size // ss, size // ss), LANCZOS)


def render_glow(color, r=52, ss=3):
    """选中棋子周围的光晕。"""
    size = int(round(r * 2.8 * ss))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2.0
    d = ImageDraw.Draw(img)
    d.ellipse([c - r * ss, c - r * ss, c + r * ss, c + r * ss],
              outline=color, width=int(r * 0.30 * ss))
    img = img.filter(ImageFilter.GaussianBlur(r * 0.16 * ss))
    return img.resize((size // ss, size // ss), LANCZOS)


def render_tile_badge(text, theme: Theme, r=52, ss=3):
    """棋子数量角标。"""
    size = int(round(r * 0.62 * 2 * ss))
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2.0
    d.ellipse([2, 2, size - 2, size - 2], fill=_hex("#1A1512"), outline=theme.accent,
              width=max(2, int(0.10 * r * ss)))
    return img.resize((size // ss, size // ss), LANCZOS)


def render_icon(size=256):
    """应用图标：一枚蜜蜡色蜂后棋子。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.05
    # 背板
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22),
                        fill=_hex("#241E19"))
    piece, (cx, cy) = render_piece("queen", 0, THEMES[0], r=int(size * 0.40),
                                  ss=4, shadow=False)
    img.alpha_composite(piece, (int(size / 2 - cx), int(size / 2 - cy)))
    return img


