"""
Flappy Ultra на Kivy (без pygame, собирается в APK через buildozer).
Меню, настройки, читы, темы дня, скины птицы, сохранение рекорда.
"""
import json
import math
import os
import random

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, Mesh, PopMatrix, PushMatrix, Rectangle, Rotate,
                           RoundedRectangle, Translate, Triangle)
from kivy.graphics.texture import Texture
from kivy.lang import Builder
from kivy.properties import ListProperty
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

DIFF_NAMES = ["Лёгкая", "Нормальная", "Сложная"]
DIFF_GAP = [1.16, 1.0, 0.86]
DIFF_SPEED = [0.87, 1.0, 1.13]
THEME_NAMES = ["День", "Закат", "Ночь", "Авто"]
SKIN_NAMES = ["Жёлтая", "Красная", "Синяя"]

CHEAT_LABELS = [
    ("god", "Бессмертие"),
    ("auto", "Автопилот"),
    ("slow", "Замедление"),
    ("lowg", "Низкая гравитация"),
    ("wide", "Широкий проход"),
]

PAL = [
    {"top": (80, 165, 235), "bot": (205, 238, 250), "far": (150, 205, 175), "near": (105, 188, 120),
     "cloud": (255, 255, 255), "night": 0.0},
    {"top": (60, 55, 125), "bot": (255, 160, 95), "far": (150, 100, 130), "near": (95, 95, 90),
     "cloud": (255, 205, 185), "night": 0.2},
    {"top": (6, 8, 32), "bot": (36, 52, 105), "far": (30, 48, 85), "near": (22, 58, 60),
     "cloud": (75, 85, 125), "night": 1.0},
]

SKINS = [
    {"body": (252, 214, 40), "belly": (255, 240, 170), "wing": (236, 186, 30), "out": (190, 125, 10)},
    {"body": (230, 70, 60), "belly": (255, 205, 195), "wing": (190, 45, 45), "out": (120, 25, 25)},
    {"body": (70, 140, 235), "belly": (205, 228, 255), "wing": (45, 100, 200), "out": (25, 60, 130)},
]

STYLES = {
    "primary": ((1.0, 0.59, 0.16, 1), (0.75, 0.39, 0.04, 1)),
    "normal": ((0.27, 0.51, 0.78, 1), (0.16, 0.33, 0.59, 1)),
    "danger": ((0.82, 0.27, 0.27, 1), (0.59, 0.16, 0.16, 1)),
    "on": ((0.27, 0.71, 0.31, 1), (0.16, 0.47, 0.20, 1)),
    "off": ((0.41, 0.41, 0.47, 1), (0.25, 0.25, 0.31, 1)),
}

KV = """
<GButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    bold: True
    color: 1, 1, 1, 1
    font_size: self.height * 0.36
    text_size: self.width * 0.92, self.height
    halign: 'center'
    valign: 'middle'
    shorten: True
    shorten_from: 'right'
    canvas.before:
        Color:
            rgba: self.edge
        RoundedRectangle:
            pos: self.x, self.y - self.height * 0.08
            size: self.size
            radius: [self.height * 0.22]
        Color:
            rgba: (self.face[0] * 0.8, self.face[1] * 0.8, self.face[2] * 0.8, 1) if self.state == 'down' else self.face
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [self.height * 0.22]
        Color:
            rgba: 1, 1, 1, 0.9
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, self.height * 0.22
            width: 1.5
"""
Builder.load_string(KV)


class GButton(Button):
    face = ListProperty([0.27, 0.51, 0.78, 1])
    edge = ListProperty([0.16, 0.33, 0.59, 1])

    def set_style(self, name):
        self.face, self.edge = [list(c) for c in STYLES[name]]


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp_c(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))


def rgb(c):
    return tuple(v / 255.0 for v in c)


def shade(c, f):
    return tuple(min(255, v * f) for v in c)


# ====================== текстуры ======================
def make_sky(top, bot):
    h = 64
    tex = Texture.create(size=(1, h), colorfmt="rgb")
    buf = bytearray()
    for y in range(h):  # y = 0 это низ (у земли)
        k = y / (h - 1)
        buf += bytes(int(bot[i] + (top[i] - bot[i]) * k) for i in range(3))
    tex.blit_buffer(bytes(buf), colorfmt="rgb", bufferfmt="ubyte")
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    return tex


def make_pipe_tex():
    w = 32
    tex = Texture.create(size=(w, 1), colorfmt="rgb")
    buf = bytearray()
    for x in range(w):
        k = x / (w - 1)
        f = 0.7 + 0.65 * math.exp(-((k - 0.28) / 0.17) ** 2) - 0.25 * max(0, (k - 0.6) / 0.4)
        buf += bytes(int(min(255, c * f)) for c in (84, 180, 53))
    tex.blit_buffer(bytes(buf), colorfmt="rgb", bufferfmt="ubyte")
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    return tex


def make_ground_tex():
    n, grass = 64, 16
    rnd = random.Random(7)
    buf = bytearray()
    for row in range(n):  # row 0 это низ текстуры
        from_top = n - 1 - row
        for x in range(n):
            if from_top < 2:
                col = (28, 66, 18)
            elif from_top < grass:
                col = (88, 175, 48) if ((x + from_top) % 32) < 16 else (110, 200, 60)
            elif from_top < grass + 2:
                col = (170, 130, 70)
            else:
                col = (196, 156, 88) if rnd.random() < 0.05 else (222, 184, 110)
            buf += bytes(col)
    tex = Texture.create(size=(n, n), colorfmt="rgb")
    tex.blit_buffer(bytes(buf), colorfmt="rgb", bufferfmt="ubyte")
    tex.wrap = "repeat"
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    return tex


# ====================== игра ======================
class FlappyRoot(FloatLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.cfg = {"best": 0, "diff": 1, "theme": 3, "skin": 0, "fps": False}
        self.load_cfg()
        self.cheats = {k: False for k, _ in CHEAT_LABELS}
        self.skies = [make_sky(p["top"], p["bot"]) for p in PAL]
        self.pipe_tex = make_pipe_tex()
        self.ground_tex = make_ground_tex()
        rnd = random.Random(3)
        self.stars = [(rnd.random(), rnd.random() * 0.6, rnd.uniform(0, 6.28), rnd.choice([1, 2])) for _ in range(70)]
        self.clouds = [[rnd.random(), rnd.uniform(0.05, 0.47), rnd.uniform(0.6, 1.4)] for _ in range(6)]
        self.particles = []
        self.ui_widgets = []
        self.over_card = False
        self.over_btns = False
        self.cheat_back = "menu"
        self.t = 0.0
        self.shake = 0.0
        self.state = "ready"
        self.ui = "menu"

        self.score_lbl = Label(text="0", halign="center", valign="middle", outline_width=3,
                               outline_color=(0, 0, 0, 1))
        self.hint_lbl = Label(text="Тапни, чтобы лететь", halign="center", valign="middle", outline_width=3,
                              outline_color=(0, 0, 0, 1))
        self.fps_lbl = Label(text="", halign="left", valign="middle", size_hint=(None, None))
        self.tag_lbl = Label(text="ЧИТЫ ВКЛ", halign="left", valign="middle", size_hint=(None, None),
                             color=(1, 0.67, 0.2, 1))
        for lbl in (self.score_lbl, self.hint_lbl):
            lbl.size_hint = (None, None)
        self.pause_btn = GButton(text="II", size_hint=(None, None))
        self.pause_btn.set_style("off")
        self.pause_btn.bind(on_release=lambda *_: self.show_ui("pause"))
        for w in (self.score_lbl, self.hint_lbl, self.fps_lbl, self.tag_lbl, self.pause_btn):
            self.add_widget(w)

        self.recalc()
        Window.bind(size=lambda *a: self.recalc(), on_keyboard=self.on_key)
        self.theme_cur = self.theme_prev = self.effective_theme()
        self.fade = 1.0
        Clock.schedule_interval(self.update, 1 / 60.0)

    # ---------- сохранение ----------
    def save_path(self):
        return os.path.join(App.get_running_app().user_data_dir, "flappy_save.json")

    def load_cfg(self):
        try:
            with open(self.save_path(), encoding="utf-8") as f:
                d = json.load(f)
            for k in self.cfg:
                if k in d:
                    self.cfg[k] = d[k]
        except Exception:
            pass

    def save_cfg(self):
        try:
            with open(self.save_path(), "w", encoding="utf-8") as f:
                json.dump(self.cfg, f)
        except Exception:
            pass

    # ---------- размеры ----------
    def recalc(self, *_):
        W, H = Window.size
        u = H / 800.0
        self.W, self.H, self.u = W, H, u
        self.GROUND_H = int(110 * u)
        self.FLOOR = H - self.GROUND_H  # координаты игры: y растёт вниз
        self.BIRD_X = W * 0.3
        self.R = int(24 * u)
        self.GRAVITY = 2300 * u
        self.JUMP = -700 * u
        self.MAX_FALL = 1100 * u
        self.BASE_SPEED = 300 * u
        self.PIPE_W = int(96 * u)
        self.CAP_H = int(38 * u)
        self.CAP_EXTRA = int(8 * u)
        self.BASE_GAP = int(250 * u)
        self.SPACING = int(400 * u)
        self.OL = max(2, int(3 * u))
        # HUD
        self.score_lbl.font_size = 110 * u
        self.score_lbl.size = (W, 140 * u)
        self.score_lbl.pos = (0, H - 30 * u - 140 * u)
        self.score_lbl.text_size = self.score_lbl.size
        self.hint_lbl.font_size = 50 * u
        self.hint_lbl.size = (W, 70 * u)
        self.hint_lbl.pos = (0, H * 0.38 - 35 * u)
        self.hint_lbl.text_size = self.hint_lbl.size
        self.fps_lbl.font_size = 30 * u
        self.fps_lbl.size = (220 * u, 40 * u)
        self.fps_lbl.pos = (16 * u, H - 16 * u - 40 * u)
        self.fps_lbl.text_size = self.fps_lbl.size
        self.tag_lbl.font_size = 30 * u
        self.tag_lbl.size = (260 * u, 40 * u)
        self.tag_lbl.pos = (16 * u, H - 56 * u - 40 * u)
        self.tag_lbl.text_size = self.tag_lbl.size
        self.pause_btn.size = (64 * u, 64 * u)
        self.pause_btn.pos = (W - 16 * u - 64 * u, H - 16 * u - 64 * u)
        if self.state == "ready":
            self.g = self.new_game()
        else:
            if not hasattr(self, "g"):
                self.g = self.new_game()
        if self.ui in ("menu", "settings", "cheats", "pause", "exit"):
            self.show_ui(self.ui)

    def cur_gap(self):
        return int(self.BASE_GAP * DIFF_GAP[self.cfg["diff"]] * (1.4 if self.cheats["wide"] else 1.0))

    def cur_speed(self):
        return self.BASE_SPEED * DIFF_SPEED[self.cfg["diff"]]

    def effective_theme(self):
        if self.cfg["theme"] == 3:
            return (self.g["score"] // 10) % 3 if hasattr(self, "g") else 0
        return self.cfg["theme"]

    # ---------- игровая логика ----------
    def new_game(self):
        return {"y": self.FLOOR * 0.5, "vy": 0.0, "pipes": [], "score": 0, "scroll": 0.0, "dead_t": 0.0,
                "last_cy": self.FLOOR * 0.5, "cheated": False, "new_best": False, "ang": 0.0}

    def add_pipe(self):
        u = self.u
        lo = 270 * u
        hi = self.FLOOR - 270 * u
        g = self.g
        cy = clamp(g["last_cy"] + random.randint(int(-150 * u), int(150 * u)), lo, hi)
        g["last_cy"] = cy
        g["pipes"].append({"x": self.W + 10, "cy": cy, "passed": False})

    def spawn(self, x, y, n, colors, speed, life, size):
        for _ in range(n):
            a = random.uniform(0, 6.283)
            s = random.uniform(0.3, 1.0) * speed
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s, life, life, random.choice(colors), size])

    def pipe_rects(self, p):
        gap = self.cur_gap()
        top = p["cy"] - gap / 2
        bot = p["cy"] + gap / 2
        x, pw, ch, ce = p["x"], self.PIPE_W, self.CAP_H, self.CAP_EXTRA
        return [(x, 0, pw, top - ch), (x - ce, top - ch, pw + 2 * ce, ch),
                (x - ce, bot, pw + 2 * ce, ch), (x, bot + ch, pw, self.FLOOR - bot - ch)]

    @staticmethod
    def circle_rect_hit(cx, cy, r, rect):
        nx = clamp(cx, rect[0], rect[0] + rect[2])
        ny = clamp(cy, rect[1], rect[1] + rect[3])
        return (cx - nx) ** 2 + (cy - ny) ** 2 < r * r

    def flap(self):
        g = self.g
        g["vy"] = self.JUMP
        self.spawn(self.BIRD_X - self.R, g["y"] + self.R * 0.5, 4, [(255, 255, 255), (230, 240, 250)],
                   140 * self.u, 0.4, 6 * self.u)

    def autopilot(self):
        g = self.g
        target = self.FLOOR * 0.45
        for p in g["pipes"]:
            if p["x"] + self.PIPE_W + self.CAP_EXTRA > self.BIRD_X - self.R:
                target = p["cy"] + self.cur_gap() * 0.22
                break
        if g["y"] > target and g["vy"] > 0:
            self.flap()

    def tap(self):
        if self.state == "ready":
            self.state = "play"
            self.flap()
        elif self.state == "play" and not self.cheats["auto"]:
            self.flap()

    def on_touch_down(self, touch):
        if super().on_touch_down(touch):
            return True
        if self.ui is None:
            self.tap()
        return True

    def on_key(self, window, key, *args):
        if key != 27:  # кнопка «назад»
            return False
        if self.ui is None:
            if self.state in ("ready", "play"):
                self.show_ui("pause")
        elif self.ui == "menu":
            self.show_ui("exit")
        elif self.ui in ("settings", "exit"):
            self.show_ui("menu")
        elif self.ui == "cheats":
            self.show_ui(self.cheat_back)
        elif self.ui == "pause":
            self.show_ui(None)
        elif self.ui == "over":
            self.action("home")
        return True

    def update(self, dt):
        raw = min(dt, 0.05)
        ts = 0.5 if self.cheats["slow"] else 1.0
        frozen = self.state == "play" and self.ui is not None
        d = 0.0 if frozen else raw * ts
        g = self.g
        W, H, u = self.W, self.H, self.u
        self.t += d

        target = self.effective_theme()
        if target != self.theme_cur:
            self.theme_prev, self.theme_cur, self.fade = self.theme_cur, target, 0.0
        self.fade = min(1.0, self.fade + raw / 1.6)

        if d > 0:
            for c in self.clouds:
                c[0] -= (30 * u * c[2] * d) / W
                if c[0] < -0.5:
                    c[0] = 1.1
                    c[1] = random.uniform(0.05, 0.47)

            if self.state == "ready":
                base = H * 0.28 if self.ui == "menu" else self.FLOOR * 0.5
                g["y"] = base + math.sin(self.t * 4) * 10 * u
                g["scroll"] += self.cur_speed() * 0.5 * d

            elif self.state == "play":
                if any(self.cheats.values()):
                    g["cheated"] = True
                grav = self.GRAVITY * (0.4 if self.cheats["lowg"] else 1.0)
                if self.cheats["auto"]:
                    self.autopilot()
                g["vy"] = min(g["vy"] + grav * d, self.MAX_FALL)
                g["y"] += g["vy"] * d
                spd = self.cur_speed()
                g["scroll"] += spd * d

                if not g["pipes"] or g["pipes"][-1]["x"] < W - self.SPACING:
                    self.add_pipe()
                for p in g["pipes"]:
                    p["x"] -= spd * d
                    if not p["passed"] and p["x"] + self.PIPE_W < self.BIRD_X - self.R:
                        p["passed"] = True
                        g["score"] += 1
                if not g["cheated"] and g["score"] > self.cfg["best"]:
                    self.cfg["best"] = g["score"]
                    g["new_best"] = True
                g["pipes"] = [p for p in g["pipes"] if p["x"] > -self.PIPE_W - 40 * u]

                if g["y"] - self.R < 0:
                    g["y"] = self.R
                    g["vy"] = max(g["vy"], 0)

                hit = False
                if g["y"] + self.R >= self.FLOOR:
                    g["y"] = self.FLOOR - self.R
                    if self.cheats["god"]:
                        g["vy"] = 0
                    else:
                        hit = True
                if not self.cheats["god"]:
                    for p in g["pipes"]:
                        for r in self.pipe_rects(p):
                            if r[2] > 0 and r[3] > 0 and self.circle_rect_hit(self.BIRD_X, g["y"], self.R * 0.85, r):
                                hit = True
                if hit:
                    self.state = "dead"
                    g["dead_t"] = 0.0
                    g["vy"] = -300 * u
                    self.shake = 0.4
                    self.spawn(self.BIRD_X, g["y"], 24, [(252, 214, 40), (255, 240, 170), (240, 110, 30)],
                               360 * u, 0.9, 8 * u)
                    self.save_cfg()
                    self.show_ui("over")

            elif self.state == "dead":
                g["dead_t"] += raw
                g["vy"] = min(g["vy"] + self.GRAVITY * d, self.MAX_FALL)
                g["y"] += g["vy"] * d
                if g["y"] + self.R > self.FLOOR:
                    g["y"] = self.FLOOR - self.R
                    g["vy"] = 0
                if self.ui == "over":
                    if not self.over_card and g["dead_t"] > 0.4:
                        self.build_over_card()
                    if not self.over_btns and g["dead_t"] > 0.6:
                        self.build_over_buttons()

            tgt = -90 if self.state == "dead" else clamp(-g["vy"] / u * 0.08, -80, 28)
            g["ang"] += (tgt - g["ang"]) * min(1.0, 12 * d)

            for p in self.particles:
                p[0] += p[2] * d
                p[1] += p[3] * d
                p[3] += self.GRAVITY * 0.3 * d
                p[4] -= d
            self.particles = [p for p in self.particles if p[4] > 0]

        self.shake = max(0.0, self.shake - raw)
        self.update_hud()
        self.draw()

    def update_hud(self):
        g = self.g
        self.score_lbl.text = str(g["score"])
        show_score = not (self.ui in ("menu", "settings", "cheats", "exit") and self.state == "ready")
        self.score_lbl.opacity = 1 if show_score else 0
        self.hint_lbl.opacity = 1 if (self.state == "ready" and self.ui is None) else 0
        self.fps_lbl.text = "FPS %d" % int(Clock.get_fps()) if self.cfg["fps"] else ""
        self.tag_lbl.opacity = 1 if (self.ui is None and any(self.cheats.values())) else 0
        pause_on = self.ui is None and self.state in ("ready", "play")
        self.pause_btn.opacity = 1 if pause_on else 0
        self.pause_btn.disabled = not pause_on

    # ---------- рисование ----------
    def draw_cloud(self, x, y, s, col):
        u, H = self.u, self.H
        r = 34 * u * s
        parts = ((0, 0, 1.0), (r * 0.9, -r * 0.3, 1.3), (r * 1.9, 0, 1.0), (r * 1.0, r * 0.2, 1.1))
        Color(*rgb(shade(col, 0.86)))
        for dx, dy, k in parts:
            rr = r * k
            Ellipse(pos=(x + dx - rr, H - (y + dy + r * 0.18) - rr), size=(2 * rr, 2 * rr))
        Color(*rgb(col))
        for dx, dy, k in parts:
            rr = r * k
            Ellipse(pos=(x + dx - rr, H - (y + dy) - rr), size=(2 * rr, 2 * rr))

    def draw_hills(self, scroll, base, a1, a2, factor, col):
        u, H = self.u, self.H
        verts = []
        for x in range(0, int(self.W) + 61, 30):
            y = self.FLOOR - base - a1 * math.sin((x + scroll * factor) / (130 * u)) \
                - a2 * math.sin((x + scroll * factor) / (47 * u))
            verts += [x, self.GROUND_H, 0, 0, x, H - y, 0, 0]
        Color(*rgb(col))
        Mesh(vertices=verts, indices=list(range(len(verts) // 4)), mode="triangle_strip")

    def draw_celestial(self, which):
        u, H, W = self.u, self.H, self.W

        def disc(cx, cy, r, col):
            Color(*rgb(col))
            Ellipse(pos=(cx - r, H - cy - r), size=(2 * r, 2 * r))

        if which == 0:
            cx, cy = W * 0.8, 150 * u
            disc(cx, cy, 95 * u, (250, 240, 175))
            disc(cx, cy, 70 * u, (255, 247, 200))
            disc(cx, cy, 48 * u, (255, 252, 225))
        elif which == 1:
            cx, cy = W * 0.7, self.FLOOR - 170 * u
            disc(cx, cy, 115 * u, (255, 190, 120))
            disc(cx, cy, 80 * u, (255, 150, 70))
        else:
            cx, cy = W * 0.78, 150 * u
            disc(cx, cy, 44 * u, (235, 238, 250))
            for dx, dy, r in ((-14, -8, 9), (10, 12, 12), (12, -16, 6)):
                disc(cx + dx * u, cy + dy * u, r * u, (208, 212, 232))

    def draw_bird(self, bx, by, ang, wing_phase):
        R, H, u = self.R, self.H, self.u
        sk = SKINS[self.cfg["skin"]]
        cx, cy = bx, H - by
        ol = max(2, int(3 * u))
        PushMatrix()
        Rotate(angle=ang, origin=(cx, cy))
        Color(*rgb(sk["wing"]))
        Triangle(points=[cx - R * 0.8, cy + R * 0.1, cx - R * 1.7, cy + R * 0.55, cx - R * 1.6, cy - R * 0.15])
        Color(*rgb(sk["out"]))
        Ellipse(pos=(cx - R - ol, cy - R - ol), size=(2 * (R + ol), 2 * (R + ol)))
        Color(*rgb(sk["body"]))
        Ellipse(pos=(cx - R, cy - R), size=(2 * R, 2 * R))
        Color(*rgb(sk["belly"]))
        Ellipse(pos=(cx - R * 0.6, cy - R * 0.85), size=(R * 1.3, R * 0.75))
        Color(*rgb(shade(sk["body"], 1.15)))
        Ellipse(pos=(cx - R * 0.55, cy + R * 0.45), size=(R * 0.8, R * 0.4))
        wo = math.sin(wing_phase) * R * 0.45
        Color(*rgb(sk["out"]))
        Ellipse(pos=(cx - R * 0.95 - 2, cy - wo - R * 0.42 - 2), size=(R * 1.05 + 4, R * 0.62 + 4))
        Color(*rgb(sk["wing"]))
        Ellipse(pos=(cx - R * 0.95, cy - wo - R * 0.42), size=(R * 1.05, R * 0.62))
        Color(1, 1, 1, 1)
        Ellipse(pos=(cx + R * 0.45 - R * 0.4, cy + R * 0.3 - R * 0.4), size=(R * 0.8, R * 0.8))
        Color(0.08, 0.08, 0.08, 1)
        Ellipse(pos=(cx + R * 0.58 - R * 0.19, cy + R * 0.3 - R * 0.19), size=(R * 0.38, R * 0.38))
        Color(0.94, 0.43, 0.12, 1)
        Triangle(points=[cx + R * 0.8, cy + R * 0.05, cx + R * 1.6, cy - R * 0.15, cx + R * 0.8, cy - R * 0.42])
        PopMatrix()

    def draw(self):
        W, H, u, g = self.W, self.H, self.u, self.g
        c = self.canvas.before
        c.clear()
        with c:
            PushMatrix()
            s = int(14 * u * self.shake / 0.4)
            Translate(random.randint(-s, s) if s > 0 else 0, random.randint(-s, s) if s > 0 else 0)

            sky_h = H - self.GROUND_H
            Color(1, 1, 1, 1)
            Rectangle(texture=self.skies[self.theme_prev if self.fade < 1 else self.theme_cur],
                      pos=(0, self.GROUND_H), size=(W, sky_h))
            if self.fade < 1:
                Color(1, 1, 1, self.fade)
                Rectangle(texture=self.skies[self.theme_cur], pos=(0, self.GROUND_H), size=(W, sky_h))

            night = PAL[self.theme_prev]["night"] + (PAL[self.theme_cur]["night"] - PAL[self.theme_prev]["night"]) * self.fade
            if night > 0.05:
                for sx, sy, ph, sz in self.stars:
                    b = min(1.0, night) * (0.6 + 0.4 * math.sin(self.t * 2 + ph))
                    Color(1, 1, 1, b)
                    r = max(1, sz * u)
                    Ellipse(pos=(sx * W - r, H - sy * self.FLOOR - r), size=(2 * r, 2 * r))

            self.draw_celestial(self.theme_cur if self.fade >= 0.5 else self.theme_prev)
            ccol = lerp_c(PAL[self.theme_prev]["cloud"], PAL[self.theme_cur]["cloud"], self.fade)
            for cl in self.clouds:
                self.draw_cloud(cl[0] * W, cl[1] * H, cl[2], ccol)
            self.draw_hills(g["scroll"], 120 * u, 40 * u, 15 * u, 0.08,
                            lerp_c(PAL[self.theme_prev]["far"], PAL[self.theme_cur]["far"], self.fade))
            self.draw_hills(g["scroll"], 60 * u, 35 * u, 18 * u, 0.2,
                            lerp_c(PAL[self.theme_prev]["near"], PAL[self.theme_cur]["near"], self.fade))

            for p in g["pipes"]:
                for (rx, ry, rw, rh) in self.pipe_rects(p):
                    if rw <= 0 or rh <= 0:
                        continue
                    Color(1, 1, 1, 1)
                    Rectangle(texture=self.pipe_tex, pos=(rx, H - ry - rh), size=(rw, rh))
                    Color(0.11, 0.26, 0.07, 1)
                    Line(rectangle=(rx, H - ry - rh, rw, rh), width=self.OL)

            u0 = (g["scroll"] / self.GROUND_H) % 1.0
            u1 = u0 + W / self.GROUND_H
            Color(1, 1, 1, 1)
            Rectangle(texture=self.ground_tex, pos=(0, 0), size=(W, self.GROUND_H),
                      tex_coords=(u0, 0, u1, 0, u1, 1, u0, 1))

            for p in self.particles:
                rad = max(1, p[7] * p[4] / p[5])
                Color(*rgb(p[6]))
                Ellipse(pos=(p[0] - rad, H - p[1] - rad), size=(2 * rad, 2 * rad))

            hide_bird = self.state == "ready" and self.ui in ("settings", "cheats", "exit")
            if not hide_bird:
                bx = W / 2 if (self.state == "ready" and self.ui == "menu") else self.BIRD_X
                wing = 0.0 if self.state == "dead" else self.t * 25
                self.draw_bird(bx, g["y"], g["ang"], wing)
            PopMatrix()

            if self.ui in ("settings", "cheats", "pause", "exit"):
                Color(0, 0, 0, 0.62)
                Rectangle(pos=(0, 0), size=(W, H))

            if self.ui == "over" and g["dead_t"] > 0.4:
                cw, ch = self.over_card_size()
                x, y = (W - cw) / 2, H - H * 0.2 - ch
                Color(1, 0.97, 0.88, 1)
                RoundedRectangle(pos=(x, y), size=(cw, ch), radius=[20 * u])
                Color(0.35, 0.24, 0.12, 1)
                Line(rounded_rectangle=(x, y, cw, ch, 20 * u), width=max(3, 4 * u))
                self.draw_medal(x + cw * 0.22, y + ch / 2 - 10 * u, g["score"])

    def over_card_size(self):
        return min(self.W * 0.88, 560 * self.u), self.H * 0.38

    def draw_medal(self, cx, cy, score):
        r = 40 * self.u
        if score >= 30:
            col = (255, 200, 40)
        elif score >= 20:
            col = (200, 200, 210)
        elif score >= 10:
            col = (205, 127, 50)
        else:
            Color(0.75, 0.69, 0.59, 1)
            Line(circle=(cx, cy, r), width=max(2, 3 * self.u))
            return
        Color(*rgb(shade(col, 0.6)))
        Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
        Color(*rgb(col))
        Ellipse(pos=(cx - r * 0.85, cy - r * 0.85), size=(1.7 * r, 1.7 * r))
        Color(*rgb(shade(col, 1.2)))
        Line(circle=(cx, cy, r * 0.5), width=max(2, 3 * self.u))

    # ---------- меню ----------
    def clear_ui(self):
        for w in self.ui_widgets:
            self.remove_widget(w)
        self.ui_widgets = []
        self.over_card = False
        self.over_btns = False

    def add_ui(self, w):
        self.ui_widgets.append(w)
        self.add_widget(w)

    def title(self, text, y, size=54, color=(1, 1, 1, 1)):
        u = self.u
        lbl = Label(text=text, font_size=size * u, size_hint=(None, None), size=(self.W, 80 * u),
                    pos=(0, y), halign="center", valign="middle", color=color,
                    outline_width=3, outline_color=(0, 0, 0, 1))
        lbl.text_size = lbl.size
        self.add_ui(lbl)
        return lbl

    def buttons(self, items, ytop, row=84, gap=16):
        u = self.u
        bw = min(self.W * 0.82, 560 * u)
        rh, gp = row * u, gap * u
        x = (self.W - bw) / 2
        for i, (bid, label, style) in enumerate(items):
            b = GButton(text=label, size_hint=(None, None), size=(bw, rh),
                        pos=(x, ytop - (i + 1) * rh - i * gp))
            b.set_style(style)
            b.bind(on_release=lambda inst, bid=bid: self.action(bid))
            self.add_ui(b)

    def show_ui(self, name):
        self.ui = name
        self.clear_ui()
        if name is None:
            return
        u, H = self.u, self.H
        if name == "menu":
            self.title("Flappy Bird", H * 0.94 - 80 * u, size=70)
            self.title("Рекорд: %d" % self.cfg["best"], H * 0.83 - 50 * u, size=34)
            self.buttons([("play", "Играть", "primary"), ("settings", "Настройки", "normal"),
                          ("cheats", "Читы", "normal"), ("exit", "Выйти", "danger")], ytop=H * 0.60)
        elif name == "settings":
            items = [("diff", "Сложность: " + DIFF_NAMES[self.cfg["diff"]], "normal"),
                     ("theme", "Время суток: " + THEME_NAMES[self.cfg["theme"]], "normal"),
                     ("skin", "Птица: " + SKIN_NAMES[self.cfg["skin"]], "normal"),
                     ("fps", "Показ FPS: " + ("ВКЛ" if self.cfg["fps"] else "ВЫКЛ"),
                      "on" if self.cfg["fps"] else "off"),
                     ("reset", "Сбросить рекорд", "danger"), ("back_menu", "Назад", "primary")]
            ytop = H / 2 + (6 * 78 + 5 * 14) * u / 2 - 20 * u
            self.title("Настройки", ytop + 10 * u)
            self.buttons(items, ytop, row=78, gap=14)
        elif name == "cheats":
            items = [(k, lb + ": " + ("ВКЛ" if self.cheats[k] else "ВЫКЛ"), "on" if self.cheats[k] else "off")
                     for k, lb in CHEAT_LABELS]
            items += [("score", "+10 очков", "normal"), ("back_cheats", "Назад", "primary")]
            ytop = H / 2 + (7 * 68 + 6 * 12) * u / 2 - 20 * u
            self.title("Читы", ytop + 10 * u)
            self.buttons(items, ytop, row=68, gap=12)
        elif name == "pause":
            ytop = H / 2 + (3 * 84 + 2 * 16) * u / 2
            self.title("Пауза", ytop + 10 * u)
            self.buttons([("resume", "Продолжить", "primary"), ("cheats", "Читы", "normal"),
                          ("home", "В меню", "danger")], ytop)
        elif name == "exit":
            ytop = H / 2 + 100 * u
            self.title("Выйти из игры?", ytop + 10 * u)
            self.buttons([("exit_yes", "Да, выйти", "danger"), ("exit_no", "Отмена", "primary")], ytop)
        elif name == "over":
            self.title("Game Over", H * 0.94 - 80 * u, size=70)

    def build_over_card(self):
        self.over_card = True
        u, H, W = self.u, self.H, self.W
        cw, ch = self.over_card_size()
        x, ytop = (W - cw) / 2, H - H * 0.2
        tx = x + cw * 0.65
        dark = (0.35, 0.24, 0.12, 1)
        g = self.g

        def lbl(text, off, size, color=dark, w=None):
            lab = Label(text=text, font_size=size * u, size_hint=(None, None), size=(w or cw * 0.4, 44 * u),
                        pos=(tx - (w or cw * 0.4) / 2, ytop - off - 44 * u), halign="center", valign="middle",
                        color=color)
            lab.text_size = lab.size
            self.add_ui(lab)

        lbl("СЧЁТ", 40, 28)
        lbl(str(g["score"]), 75, 48, (0.24, 0.16, 0.08, 1))
        lbl("РЕКОРД", 150, 28)
        lbl(str(self.cfg["best"]), 185, 48, (0.24, 0.16, 0.08, 1))
        if g["new_best"]:
            lab = Label(text="НОВЫЙ РЕКОРД!", font_size=30 * u, size_hint=(None, None), size=(cw * 0.8, 40 * u),
                        pos=(W / 2 - cw * 0.4, ytop - ch + 12 * u), halign="center", valign="middle",
                        color=(0.82, 0.2, 0.2, 1))
            lab.text_size = lab.size
            self.add_ui(lab)
        elif g["cheated"]:
            lab = Label(text="С читами рекорд не считается", font_size=26 * u, size_hint=(None, None),
                        size=(cw * 0.9, 40 * u), pos=(W / 2 - cw * 0.45, ytop - ch + 12 * u),
                        halign="center", valign="middle", color=(0.55, 0.4, 0.24, 1))
            lab.text_size = lab.size
            self.add_ui(lab)

    def build_over_buttons(self):
        self.over_btns = True
        self.buttons([("retry", "Заново", "primary"), ("home", "Меню", "normal")],
                     ytop=self.H * 0.36, row=80, gap=14)

    def action(self, bid):
        c = self.cfg
        if bid in ("play", "retry"):
            self.g = self.new_game()
            self.state = "ready"
            self.show_ui(None)
        elif bid == "settings":
            self.show_ui("settings")
        elif bid == "cheats":
            self.cheat_back = self.ui
            self.show_ui("cheats")
        elif bid == "exit":
            self.show_ui("exit")
        elif bid == "exit_yes":
            self.save_cfg()
            App.get_running_app().stop()
        elif bid in ("exit_no", "back_menu"):
            self.show_ui("menu")
        elif bid == "back_cheats":
            self.show_ui(self.cheat_back)
        elif bid == "diff":
            c["diff"] = (c["diff"] + 1) % 3
            self.save_cfg()
            self.show_ui("settings")
        elif bid == "theme":
            c["theme"] = (c["theme"] + 1) % 4
            self.save_cfg()
            self.show_ui("settings")
        elif bid == "skin":
            c["skin"] = (c["skin"] + 1) % 3
            self.save_cfg()
            self.show_ui("settings")
        elif bid == "fps":
            c["fps"] = not c["fps"]
            self.save_cfg()
            self.show_ui("settings")
        elif bid == "reset":
            c["best"] = 0
            self.save_cfg()
        elif bid in self.cheats:
            self.cheats[bid] = not self.cheats[bid]
            self.show_ui("cheats")
        elif bid == "score":
            self.g["score"] += 10
            self.g["cheated"] = True
        elif bid == "resume":
            self.show_ui(None)
        elif bid == "home":
            self.g = self.new_game()
            self.state = "ready"
            self.show_ui("menu")


class FlappyApp(App):
    title = "Flappy Ultra"

    def build(self):
        return FlappyRoot()

    def on_pause(self):
        return True


if __name__ == "__main__":
    FlappyApp().run()
