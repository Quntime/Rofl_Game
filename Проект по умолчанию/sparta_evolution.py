"""
СПАРТА: СЕЛЕКЦИЯ — 2D-симуляция на pygame.

Правила мира:
  * Спартанцы проверяют каждого ребёнка на «ЛЕГИТ».
  * Если у ребёнка есть хотя бы одна отрицательная модификация —
    его сбрасывают с обрыва (Тарпейская скала).
  * С шансом 1% сброшенный ребёнок выживает и вступает в ряды спартанцев.
  * Одобренные дети и выжившие спартанцы передают гены дальше:
    новые дети рождаются от лучших по приспособленности родителей
    (дарвиновский отбор), поэтому характеристики популяции растут.

Управление:
  SPACE — создать ребёнка вручную
  1..4  — скорость симуляции
  P     — пауза
  R     — сброс
  ESC   — выход

Запуск:  python sparta_evolution.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pygame

# ─────────────────────────── РАЗМЕРЫ И ГЕОМЕТРИЯ ───────────────────────────
WIDTH, HEIGHT = 1180, 660
FPS = 60

GROUND_Y = 500          # уровень земли
PLATEAU_Y = GROUND_Y - 46   # площадка, где стоят спасённые спартанцы
GORGE_X = 872           # начало обрыва
EDGE_X = 866            # край скалы, откуда сбрасывают
INSPECT_X = 696         # место, где ребёнок останавливается перед проверкой
INSPECTOR_X = 756       # где стоит спартанец-инспектор
FALL_LIMIT = 612        # глубина, после которой ребёнок «достиг дна»
SURVIVAL_CHANCE = 0.01  # 1% выживания при падении
EXECUTION_CHANCE = 0.05  # 5% — спартанец говорит «200», и ребёнок умирает на месте
MAX_STEP = 0.05          # максимальный шаг симуляции (для ускорения x100)

# армия: легитимные дети строятся внизу и уходят воевать по 100 человек
ARMY_TARGET = 100
ARMY_COLS = 34
ARMY_ROWS = 3
ARMY_X0, ARMY_DX = 18, 19
ARMY_Y0, ARMY_DY = 560, 36
ARMY_SCALE = 0.5
ARMY_SPEED = 170

# босс и битва
BOSS_MAX_HP = 1000
BOSS_X = 900
BOSS_FEET_Y = 628
BATTLE_DURATION = 11.0
BURGER_CHANCE = 0.06    # шанс, что босс перекусит бургером
LASER_CHANCE = 0.10     # шанс лазера из пупка
POUND_CHANCE = 0.19     # топот: ударные волны по земле
SPIT_CHANCE = 0.18      # плевок в бойцов
SPIN_CHANCE = 0.13      # вертушка руками
STRIKE_CHANCE = 0.34    # обычный удар лапой
BOSS_HEAL_SHARE = 0.08  # сколько здоровья восстанавливает бургер
BATTLE_RANGED_SHARE = 0.62
BATTLE_SCALE = 0.55

# ─────────────────────────── ЦВЕТА ───────────────────────────
SKY_TOP = (24, 28, 44)
SKY_BOTTOM = (126, 86, 64)
GOLD = (236, 198, 96)
WHITE = (238, 238, 232)
RED = (206, 74, 66)
GRAY = (168, 168, 172)
PANEL_BORDER = (86, 80, 74)

STAT_KEYS = ("power", "agility", "mind")
STAT_LABELS = {"power": "Сила", "agility": "Ловкость", "mind": "Ум"}
STAT_COLORS = {"power": (214, 96, 86), "agility": (126, 194, 112), "mind": (112, 162, 224)}


# ─────────────────────────── ГЕНЕТИКА ───────────────────────────
@dataclass(frozen=True)
class Mutation:
    """Модификация: меняет одну характеристику в плюс или в минус."""
    name: str
    stat: str
    delta: float
    positive: bool


POSITIVE_MUTATIONS = (
    Mutation("Геркулесова сила", "power", 0.22, True),
    Mutation("Широкие плечи", "power", 0.18, True),
    Mutation("Железная выдержка", "power", 0.14, True),
    Mutation("Быстрые ноги", "agility", 0.20, True),
    Mutation("Кошачья реакция", "agility", 0.16, True),
    Mutation("Лёгкие кости", "agility", 0.13, True),
    Mutation("Острый ум", "mind", 0.22, True),
    Mutation("Стратегический склад ума", "mind", 0.15, True),
    Mutation("КРАСТИН", "power", 0.20, True),
    Mutation("АЛЬТУХА С 3 РАЗМЕРОМ", "power", 0.24, True),
    Mutation("НЕ ИЗ СНК", "mind", 0.18, True),
    Mutation("НОСИТ КОСТЮМ «ПРИВЕДЕНИЯ»", "agility", 0.19, True),
)

NEGATIVE_MUTATIONS = (
    Mutation("Слабые мышцы", "power", -0.20, False),
    Mutation("Хрупкие кости", "power", -0.16, False),
    Mutation("Болезненность", "power", -0.13, False),
    Mutation("Хромота", "agility", -0.22, False),
    Mutation("Медлительность", "agility", -0.18, False),
    Mutation("Дрожащие руки", "agility", -0.15, False),
    Mutation("Тугоумие", "mind", -0.22, False),
    Mutation("Рассеянность", "mind", -0.14, False),
    Mutation("Васильев", "mind", -0.20, False),
    Mutation("Игрок на спектре", "agility", -0.17, False),
    Mutation("Не задонатил", "power", -0.15, False),
    Mutation("ДС-ССА", "mind", -0.19, False),
    Mutation("Из китай города", "agility", -0.14, False),
    Mutation("ИГОРЬ К.", "power", -0.18, False),
    Mutation("РАБ РЫГАЧЁВА", "power", -0.22, False),
)


# болезни: временно ухудшают характеристики, но проходят
@dataclass(frozen=True)
class Disease:
    name: str
    multipliers: dict
    duration: float
    weight: float
    color: tuple


DISEASES = (
    Disease("Простуда", {"power": 0.90, "agility": 0.82, "mind": 0.95},
            35.0, 0.34, (144, 206, 150)),
    Disease("Лихорадка", {"power": 0.75, "agility": 0.80, "mind": 0.70},
            26.0, 0.28, (226, 176, 92)),
    Disease("Дизентерия", {"power": 0.66, "agility": 0.72, "mind": 0.90},
            30.0, 0.24, (196, 132, 76)),
    Disease("Чума", {"power": 0.55, "agility": 0.55, "mind": 0.60},
            20.0, 0.14, (188, 92, 120)),
)


CHILD_PALETTES = (
    {"skin": (232, 196, 164), "cloth": (118, 146, 188), "hair": (86, 62, 44)},
    {"skin": (208, 166, 134), "cloth": (126, 168, 148), "hair": (52, 42, 36)},
    {"skin": (238, 208, 178), "cloth": (178, 146, 106), "hair": (128, 88, 52)},
)


@dataclass(frozen=True)
class Look:
    """Внешний вид ребёнка, собранный из его модификаций."""

    variant: int = 0
    body: str = "normal"      # normal | fat | skinny | muscular
    outfit: str = "cloth"     # cloth | rich | ghost | nude | alt
    hat: str = ""             # "" | dunce | straw
    glasses: bool = False
    cat_ears: bool = False
    headphones: bool = False
    hood: bool = False
    collar: bool = False
    crutch: bool = False
    cloud: bool = False
    fuse: bool = False
    cup: bool = False
    bandage: bool = False
    armor: bool = False
    scroll: bool = False
    snail: bool = False
    dots: bool = False
    trembling: bool = False
    fast: bool = False
    sick: bool = False


def look_for(mutations, variant: int) -> Look:
    names = {m.name for m in mutations}

    body = "normal"
    if "КРАСТИН" in names:
        body = "fat"
    elif "Геркулесова сила" in names or "Широкие плечи" in names:
        body = "muscular"
    elif "Слабые мышцы" in names:
        body = "skinny"

    outfit = "cloth"
    if "НОСИТ КОСТЮМ «ПРИВЕДЕНИЯ»" in names:
        outfit = "ghost"
    elif "РАБ РЫГАЧЁВА" in names:
        outfit = "nude"
    elif "АЛЬТУХА С 3 РАЗМЕРОМ" in names:
        outfit = "alt"
    elif "НЕ ИЗ СНК" in names:
        outfit = "rich"

    hat = ""
    if "Тугоумие" in names:
        hat = "dunce"
    elif "Из китай города" in names:
        hat = "straw"

    return Look(
        variant=variant,
        body=body,
        outfit=outfit,
        hat=hat,
        glasses="Острый ум" in names,
        cat_ears="Кошачья реакция" in names,
        headphones="Игрок на спектре" in names,
        hood="ДС-ССА" in names,
        collar="РАБ РЫГАЧЁВА" in names,
        crutch="Хромота" in names,
        cloud="Васильев" in names,
        fuse="ИГОРЬ К." in names,
        cup="Не задонатил" in names,
        bandage="Хрупкие кости" in names,
        armor="Железная выдержка" in names,
        scroll="Стратегический склад ума" in names,
        snail="Медлительность" in names,
        dots="Рассеянность" in names,
        trembling="Дрожащие руки" in names,
        fast="Быстрые ноги" in names or "Лёгкие кости" in names,
        sick="Болезненность" in names,
    )


def clamp(value: float, low: float = 0.05, high: float = 1.0) -> float:
    return max(low, min(high, value))


def percent(part: int, total: int) -> str:
    """Доля в процентах для интерфейса."""
    if total <= 0:
        return "0%"
    return f"{part / total * 100:.0f}%"


@dataclass
class Genome:
    """Наследуемый набор характеристик."""

    stats: dict
    generation: int
    disease: str = ""
    disease_left: float = 0.0
    disease_mult: dict = field(default_factory=dict)

    def is_sick(self) -> bool:
        return self.disease_left > 0 and self.disease

    def effective_stats(self) -> dict:
        """Характеристики с учётом текущей болезни."""
        if not self.is_sick():
            return dict(self.stats)
        return {
            key: max(0.05, min(1.0, self.stats[key] * self.disease_mult.get(key, 1.0)))
            for key in STAT_KEYS
        }

    def tick(self, dt: float):
        if self.disease_left > 0:
            self.disease_left -= dt
            if self.disease_left <= 0:
                self.disease_left = 0.0
                self.disease = ""
                self.disease_mult = {}

    def fitness(self) -> float:
        """Приспособленность — чем выше, тем больше шансов оставить потомство."""
        s = self.effective_stats()
        return 0.40 * s["power"] + 0.35 * s["agility"] + 0.25 * s["mind"]


# ─────────────────────────── ЧАСТИЦЫ И ТЕКСТ ───────────────────────────
class Particle:
    def __init__(self, x, y, vx, vy, life, color, radius):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.color = color
        self.radius = radius

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 260 * dt
        self.life -= dt


@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    color: tuple
    life: float = 1.1
    font_key: str = "bold"

    def update(self, dt):
        self.y -= 34 * dt
        self.life -= dt


class SpeechBubble:
    """Облачко с репликой спартанца."""

    def __init__(self, text: str, x: float, y: float, life: float = 1.8):
        self.text = text
        self.x, self.y = x, y
        self.life = self.max_life = life

    def update(self, dt):
        self.y -= 4 * dt
        self.life -= dt

    def draw(self, screen, fonts):
        image = fonts.title.render(self.text, True, (22, 20, 26))
        w, h = image.get_width(), image.get_height()
        rect = pygame.Rect(int(self.x - w / 2 - 14), int(self.y - h / 2 - 9), w + 28, h + 18)
        pygame.draw.rect(screen, (246, 244, 236), rect, border_radius=9)
        pygame.draw.polygon(screen, (246, 244, 236), [
            (rect.centerx - 9, rect.bottom - 2),
            (rect.centerx + 9, rect.bottom - 2),
            (rect.centerx, rect.bottom + 14),
        ])
        screen.blit(image, (rect.centerx - w // 2, rect.centery - h // 2))


class Meteor:
    """Метеорит, который падает на Васильева."""

    def __init__(self, target):
        self.target = target
        self.tx = target.x
        self.ty = GROUND_Y - 36
        self.x = self.tx + random.uniform(150, 240)
        self.y = -90.0
        dx, dy = self.tx - self.x, self.ty - self.y
        distance = max(1.0, math.hypot(dx, dy))
        self.speed = 560.0
        self.vx = dx / distance * self.speed
        self.vy = dy / distance * self.speed
        self.trail = []

    def update(self, dt):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 18:
            self.trail.pop(0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        return self.y < self.ty

    def draw(self, screen):
        for index, (x, y) in enumerate(self.trail):
            t = index / max(1, len(self.trail) - 1)
            radius = max(1, int(1 + 9 * t))
            color = (int(170 + 70 * t), int(58 + 116 * t), int(34 + 38 * t))
            pygame.draw.circle(screen, color, (int(x), int(y)), radius)
        glow = pygame.Surface((44, 44), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 132, 54, 90), (22, 22), 20)
        pygame.draw.circle(glow, (255, 176, 82, 130), (22, 22), 14)
        screen.blit(glow, (int(self.x) - 22, int(self.y) - 22))
        pygame.draw.circle(screen, (255, 168, 74), (int(self.x), int(self.y)), 12)
        pygame.draw.circle(screen, (255, 244, 190), (int(self.x), int(self.y)), 6)


class Explosion:
    """Расширяющиеся кольца взрыва."""

    def __init__(self, x, y, radius=95, color=(255, 170, 70), life=0.75):
        self.x, self.y = x, y
        self.radius = radius
        self.color = color
        self.life = self.max_life = life

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, screen):
        t = 1.0 - self.life / self.max_life
        size = max(24, int(self.radius * (0.9 + 0.6 * t) * 1.3))
        layer = pygame.Surface((size, size), pygame.SRCALPHA)
        center = size // 2
        fade = max(0.0, 1.0 - t)

        # мягкое свечение
        pygame.draw.circle(layer, (*self.color, int(60 * fade)), (center, center), int(size * 0.5))

        # огненный шар с белым ядром
        ball = max(2, int(size * 0.30 * (1.0 - 0.35 * t)))
        pygame.draw.circle(layer, (252, 132, 52, int(230 * fade)), (center, center), ball)
        pygame.draw.circle(layer, (255, 206, 108, int(240 * fade)), (center, center), max(1, int(ball * 0.72)))
        pygame.draw.circle(layer, (255, 248, 224, int(250 * fade)), (center, center), max(1, int(ball * 0.38)))

        # ударная волна
        wave = int(size * (0.25 + 0.30 * t))
        if wave > 1:
            pygame.draw.circle(layer, (255, 238, 196, int(190 * fade)),
                               (center, center), wave, width=max(2, int(4 * (1 - t) + 1)))
        screen.blit(layer, (int(self.x - size / 2), int(self.y - size / 2)))


# ─────────────────────────── РЕБЁНОК ───────────────────────────
class Child:
    """Ребёнок со своим геномом и модификациями."""

    def __init__(self, genome: Genome, mutations, origin: str):
        self.genome = genome
        self.mutations = mutations
        self.origin = origin
        self.negative = any(not m.positive for m in mutations)
        self.positive_count = sum(1 for m in mutations if m.positive)
        self.negative_count = sum(1 for m in mutations if not m.positive)

        self.x = -46.0
        self.y = float(GROUND_Y)
        self.state = "walk_in"
        self.timer = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.spin = 0.0
        self.phase = random.random() * math.tau
        self.variant = random.randrange(len(CHILD_PALETTES))
        self.look = look_for(self.mutations, self.variant)
        self.walk_speed = random.uniform(96, 116)

        self.condemned = False
        self.survived = False
        self.fate = None
        self.slot = None
        self.target_x = None
        self.target_y = None

    def has(self, name: str) -> bool:
        return any(m.name == name for m in self.mutations)

    # судьба решается у инспектора
    def decide_fate(self):
        if random.random() < EXECUTION_CHANCE:
            self.fate = "200"
        elif self.has("Васильев"):
            self.fate = "meteor"
        elif self.has("ИГОРЬ К."):
            self.fate = "boom"
        elif self.negative:
            self.fate = "cliff"
        else:
            self.fate = "legit"

    def start_death(self):
        if self.state in ("dying", "gone"):
            return
        self.state = "dying"
        self.timer = 0.9
        self.spin = random.choice((-1, 1)) * random.uniform(200, 320)

    # возвращает список событий для симуляции
    def update(self, dt: float):
        events = []

        if self.state == "walk_in":
            self.x += self.walk_speed * dt
            if self.x >= INSPECT_X:
                self.x = INSPECT_X
                self.decide_fate()
                self.condemned = self.fate in ("cliff", "meteor", "boom")
                self.state = "judge"
                self.timer = 0.9
                events.append(("judged", self))

        elif self.state == "judge":
            self.timer -= dt
            if self.timer <= 0:
                if self.fate == "legit":
                    self.state = "to_army"
                    events.append(("approved", self))
                elif self.fate == "cliff":
                    self.state = "to_edge"
                elif self.fate == "boom":
                    events.append(("boom", self))
                    self.start_death()
                elif self.fate == "meteor":
                    self.state = "await_meteor"
                    self.timer = 3.0
                elif self.fate == "200":
                    events.append(("execute", self))
                    self.start_death()

        elif self.state == "await_meteor":
            self.timer -= dt
            if self.timer <= 0:
                self.start_death()

        elif self.state == "dying":
            self.timer -= dt
            limit = 88.0 * (1 if self.spin > 0 else -1)
            if abs(self.angle) < 88.0:
                self.angle += self.spin * dt
                if abs(self.angle) > 88.0:
                    self.angle = limit
            self.y = min(self.y + 10 * dt, float(GROUND_Y))
            if self.timer <= 0:
                self.state = "gone"
                events.append(("killed", self))

        elif self.state == "to_army":
            if self.target_x is None:
                return events
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            if abs(dx) <= 1.0 and abs(dy) <= 1.0:
                self.x = self.target_x
                self.y = self.target_y
                self.state = "gone"
                events.append(("enlisted", self))
            else:
                step = 165 * dt
                distance = math.hypot(dx, dy)
                if distance <= step:
                    self.x, self.y = self.target_x, self.target_y
                else:
                    self.x += dx / distance * step
                    self.y += dy / distance * step

        elif self.state == "to_edge":
            self.x += 135 * dt
            if self.x >= EDGE_X:
                self.x = EDGE_X
                self.state = "teeter"
                self.timer = 0.45

        elif self.state == "teeter":
            self.timer -= dt
            if self.timer <= 0:
                self.survived = random.random() < SURVIVAL_CHANCE
                self.state = "fall"
                self.vy = 40.0
                self.vx = random.uniform(95, 150)
                self.spin = random.uniform(-280, -150)

        elif self.state == "fall":
            self.vy += 1200 * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.angle += self.spin * dt
            if self.y >= FALL_LIMIT:
                if self.survived:
                    self.state = "saved"
                    self.timer = 1.2
                    self.angle = 0.0
                    events.append(("miraculous", self))
                else:
                    self.state = "gone"
                    events.append(("dead", self))

        elif self.state == "saved":
            # чудо: ребёнок цепляется за скалу и поднимается обратно
            self.timer -= dt
            k = min(1.0, dt * 4.0)
            self.x += (EDGE_X - 26 - self.x) * k
            self.y += (GROUND_Y - self.y) * k
            if self.timer <= 0:
                self.x = EDGE_X - 26
                self.y = float(GROUND_Y)
                self.state = "gone"
                events.append(("joined", self))

        return events


class Spartan:
    def __init__(self, x: float):
        self.x = x
        self.phase = random.random() * math.tau


class Soldier:
    """Солдат армии: стоит в строю, потом уходит на войну."""

    def __init__(self, slot: int, look: Look, stats=None, genome=None):
        self.slot = slot
        self.look = look
        self.genome = genome
        self.stats = genome.effective_stats() if genome is not None else (
            dict(stats) if stats else {"power": 0.5, "agility": 0.5, "mind": 0.5})
        col = slot % ARMY_COLS
        row = (slot // ARMY_COLS) % ARMY_ROWS
        self.x = float(ARMY_X0 + col * ARMY_DX)
        self.y = float(ARMY_Y0 + row * ARMY_DY)
        self.phase = random.random() * math.tau

    def current_stats(self):
        if self.genome is not None:
            return self.genome.effective_stats()
        return self.stats


def win_chance(soldiers) -> float:
    """Шанс победы над боссом: зависит от силы, ловкости и ума бойцов."""
    if not soldiers:
        return 0.0
    total = 0.0
    for soldier in soldiers:
        stats = soldier.current_stats()
        total += (0.40 * stats.get("power", 0.5)
                  + 0.35 * stats.get("agility", 0.5)
                  + 0.25 * stats.get("mind", 0.5))
    average = total / len(soldiers)
    return max(0.03, min(0.80, (average - 0.42) * 1.7))


class BattleSoldier:
    """Боец в сражении с боссом."""

    def __init__(self, soldier, role: str, x: float, y: float):
        self.look = soldier.look
        self.stats = soldier.current_stats()
        self.genome = getattr(soldier, "genome", None)
        self.role = role
        self.x = x
        self.y = y
        self.phase = random.random() * math.tau
        self.alive = True
        self.dying = 0.0
        self.angle = 0.0
        self.lunge = 0.0
        self.cooldown = random.uniform(0.4, 2.4)
        self.corpse = random.choice((-1, 1))

    def update(self, dt, battle):
        if not self.alive:
            self.dying += dt
            self.angle = min(86.0, self.dying * 210)
            return
        self.cooldown -= dt
        if self.lunge > 0:
            self.lunge = max(0.0, self.lunge - dt * 3.2)
        if self.cooldown <= 0:
            if self.role == "ranged":
                battle.throw_spear(self)
                self.cooldown = random.uniform(1.3, 2.5)
            else:
                battle.melee_hit(self)
                self.lunge = 1.0
                self.cooldown = random.uniform(0.8, 1.6)

    def kill(self):
        if self.alive:
            self.alive = False
            self.dying = 0.0

    def draw(self, screen, sprites, battle):
        sprite = sprites.child(self.look, BATTLE_SCALE)
        if not self.alive:
            draw_figure(screen, sprite, self.x, self.y, angle=self.angle * self.corpse)
            return
        if self.role == "ranged":
            bob = math.sin(self.phase + battle.time * 5.0) * 1.2
            spear_x = self.x + 10
            pygame.draw.line(screen, (150, 112, 66), (spear_x, self.y - 30), (spear_x + 10, self.y - 52), 2)
            pygame.draw.polygon(screen, (214, 218, 224),
                                [(spear_x + 10, self.y - 56), (spear_x + 7, self.y - 50), (spear_x + 12, self.y - 49)])
        else:
            bob = math.sin(self.phase + battle.time * 7.0) * 1.4
            thrust = int(12 * self.lunge)
            pygame.draw.line(screen, (150, 112, 66),
                             (self.x + 8 + thrust, self.y - 34), (self.x + 30 + thrust, self.y - 46), 2)
            pygame.draw.polygon(screen, (214, 218, 224),
                                [(self.x + 32 + thrust, self.y - 48),
                                 (self.x + 27 + thrust, self.y - 44),
                                 (self.x + 31 + thrust, self.y - 41)])
        screen.blit(sprite, (int(self.x - sprite.get_width() / 2 + (6 * self.lunge if self.role == "melee" else 0)),
                             int(self.y - sprite.get_height() + bob)))
        if self.genome is not None and self.genome.is_sick():
            draw_sick_mark(screen, int(self.x), int(self.y - sprite.get_height() + bob - 7), 0.8)


class Spear:
    """Летящее копьё."""

    def __init__(self, x, y, tx, ty):
        self.x, self.y = x, y
        self.tx, self.ty = tx, ty
        dx, dy = tx - x, ty - y
        distance = max(1.0, math.hypot(dx, dy))
        self.speed = 860.0
        self.vx = dx / distance * self.speed
        self.vy = dy / distance * self.speed
        self.life = distance / self.speed
        self.angle = math.atan2(dy, dx)

    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        return self.life > 0

    def draw(self, screen):
        dx = math.cos(self.angle) * 15
        dy = math.sin(self.angle) * 15
        pygame.draw.line(screen, (160, 118, 68),
                         (int(self.x - dx), int(self.y - dy)), (int(self.x + dx), int(self.y + dy)), 3)
        pygame.draw.circle(screen, (226, 230, 236), (int(self.x + dx), int(self.y + dy)), 3)


class Spit:
    """Плевок босса: летит по дуге в бойца."""

    def __init__(self, x, y, tx, ty):
        self.x0, self.y0 = x, y
        self.tx, self.ty = tx, ty
        self.t = 0.0
        self.dur = max(0.35, math.hypot(tx - x, ty - y) / 780.0)
        self.x, self.y = x, y

    def update(self, dt):
        self.t += dt
        k = min(1.0, self.t / self.dur)
        self.x = self.x0 + (self.tx - self.x0) * k
        self.y = self.y0 + (self.ty - self.y0) * k - math.sin(k * math.pi) * 70
        return self.t < self.dur

    def draw(self, screen):
        pygame.draw.circle(screen, (154, 214, 110), (int(self.x), int(self.y)), 7)
        pygame.draw.circle(screen, (196, 236, 150), (int(self.x - 2), int(self.y - 2)), 3)
        pygame.draw.circle(screen, (110, 168, 78), (int(self.x + 6), int(self.y + 5)), 2)


class Shockwave:
    """Ударная волна от топота: расходится по земле."""

    def __init__(self, x, y, delay=0.0):
        self.x, self.y = x, y
        self.t = -delay
        self.dur = 0.75

    def update(self, dt):
        self.t += dt
        return self.t < self.dur

    def draw(self, screen):
        if self.t < 0:
            return
        k = min(1.0, self.t / self.dur)
        alpha = int(150 * (1.0 - k))
        radius = int(70 + 620 * k)
        height = int(radius * 0.62)
        layer = pygame.Surface((radius * 2, height * 2), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, radius * 2, height * 2)
        pygame.draw.ellipse(layer, (238, 196, 120, alpha), rect, 5)
        pygame.draw.ellipse(layer, (200, 150, 86, alpha // 2), rect.inflate(-18, -10), 3)
        screen.blit(layer, (int(self.x - radius), int(self.y - height)))


class Boss:
    """ОГРОМНЫЙ жирный парень в зелёной футболке."""

    def __init__(self):
        self.x = BOSS_X
        self.feet = BOSS_FEET_Y
        self.hp = self.max_hp = BOSS_MAX_HP
        self.t = 0.0
        self.state = "idle"
        self.timer = 0.0
        self.hit = 0.0
        self.death = 0.0
        self.dead = False
        self.burger = 0.0
        self.eat_progress = 0.0
        self.laser_glow = 0.0
        self.laser_to = None
        self.spit_to = None
        self.spit_progress = 0.0
        self.spin_angle = 0.0
        self.pound_phase = 0.0
        self.attack = 0.0
        self.arm_swing = 0.0

    def play_attack(self):
        self.state = "attack"
        self.timer = 0.42
        self.arm_swing = 1.0

    def start_eat(self):
        self.state = "eat"
        self.timer = 1.15
        self.burger = 1.0

    def start_laser(self, target):
        self.state = "laser"
        self.timer = 0.95
        self.laser_to = target
        self.laser_glow = 1.0

    def start_pound(self):
        """Топот: босс поднимает руки и бьёт по земле."""
        self.state = "pound"
        self.timer = 0.95
        self.pound_phase = 0.0
        self.arm_swing = 1.0

    def start_spit(self, target):
        """Плевок в бойцов."""
        self.state = "spit"
        self.timer = 0.85
        self.spit_to = target
        self.spit_progress = 0.0

    def start_spin(self):
        """Вертушка: босс раскручивается и разбрасывает бойцов."""
        self.state = "spin"
        self.timer = 1.1
        self.spin_angle = 0.0
        self.arm_swing = 1.0

    def start_death(self):
        self.state = "dying"
        self.death = 0.0

    def update(self, dt):
        self.t += dt
        self.hit = max(0.0, self.hit - dt * 4.0)
        self.laser_glow = max(0.0, self.laser_glow - dt * 1.2)
        if self.arm_swing > 0:
            self.arm_swing = max(0.0, self.arm_swing - dt * 3.0)
        if self.state == "dying":
            self.death += dt
            if self.death > 2.2:
                self.dead = True
            return
        if self.state != "idle":
            self.timer -= dt
            if self.timer <= 0:
                self.state = "idle"
                self.burger = 0.0
                self.eat_progress = 0.0
                self.laser_to = None
                self.spit_to = None
                self.spin_angle = 0.0
        if self.state == "eat":
            self.eat_progress = min(1.0, 1.0 - self.timer / 1.15)
        elif self.state == "pound":
            self.pound_phase = min(1.0, 1.0 - self.timer / 0.95)
        elif self.state == "spit":
            self.spit_progress = min(1.0, 1.0 - self.timer / 0.85)
        elif self.state == "spin":
            self.spin_angle += dt * 15.0

    # ----- отрисовка -----
    def _surface(self):
        surf = pygame.Surface((470, 500), pygame.SRCALPHA)
        cx, fy = 235, 486
        leg = (62, 72, 104)
        skin = (234, 194, 158)
        shirt = (56, 142, 82)
        shirt_dark = (42, 114, 66)
        hair = (158, 114, 62)

        # тень
        pygame.draw.ellipse(surf, (0, 0, 0, 90), (48, 466, 374, 30))

        # ноги в скинни-джинсах (почти скрыты животом)
        for lx in (205, 265):
            pygame.draw.line(surf, leg, (lx, 360), (lx, 466), 30)
            pygame.draw.circle(surf, leg, (lx, 360), 15)
        pygame.draw.ellipse(surf, (48, 38, 30), (180, 458, 52, 22))
        pygame.draw.ellipse(surf, (48, 38, 30), (238, 458, 52, 22))

        # длинные волосы принца (за спиной)
        pygame.draw.polygon(surf, hair, [
            (158, 130), (312, 130), (352, 330), (316, 322), (300, 230),
            (270, 300), (235, 240), (200, 300), (170, 230), (154, 322), (118, 330),
        ])
        pygame.draw.ellipse(surf, hair, (116, 74, 238, 196))
        pygame.draw.ellipse(surf, (176, 132, 76), (136, 88, 198, 150))

        # огромный живот в зелёной футболке
        pygame.draw.ellipse(surf, shirt_dark, (52, 158, 366, 282))
        pygame.draw.ellipse(surf, shirt, (62, 168, 346, 264))
        for i, yy in enumerate((238, 288, 338, 388)):
            pygame.draw.arc(surf, shirt_dark, (96 + i * 5, yy - 46, 278 - i * 10, 104), 3.3, 5.9, 3)

        # длинные пряди принца поверх футболки
        pygame.draw.polygon(surf, hair, [
            (150, 152), (190, 140), (182, 300), (168, 268), (156, 318), (140, 270), (132, 306),
        ])
        pygame.draw.polygon(surf, hair, [
            (280, 140), (320, 152), (338, 306), (330, 270), (314, 318), (302, 268), (288, 300),
        ])
        pygame.draw.line(surf, (188, 144, 86), (158, 170), (150, 300), 3)
        pygame.draw.line(surf, (188, 144, 86), (312, 170), (320, 300), 3)

        # шея и воротник
        pygame.draw.rect(surf, skin, (217, 186, 36, 40), border_radius=8)
        pygame.draw.ellipse(surf, shirt_dark, (196, 196, 78, 30))
        pygame.draw.ellipse(surf, (30, 92, 52), (202, 199, 66, 22))

        # руки: тёмный рукав + кожная кисть, чтобы читались на футболке
        swing = self.arm_swing
        if self.state == "eat":
            hand_l = (150, 360)
            hand_r = (300 - int(20 * self.eat_progress), 240 - int(70 * self.eat_progress))
        elif self.state == "attack":
            hand_l = (146, 368)
            hand_r = (356 - int(120 * swing), 330 + int(40 * swing))
        elif self.state == "pound":
            if self.pound_phase < 0.5:
                lift = self.pound_phase * 2.0
                hand_l = (148, int(340 - 190 * lift))
                hand_r = (322, int(340 - 190 * lift))
            else:
                drop = (self.pound_phase - 0.5) * 2.0
                hand_l = (148, int(150 + 230 * drop))
                hand_r = (322, int(150 + 230 * drop))
        elif self.state == "spin":
            hand_l = (60, 300 + int(math.sin(self.spin_angle) * 18))
            hand_r = (410, 300 - int(math.sin(self.spin_angle) * 18))
        elif self.state == "spit":
            hand_l = (140, 366)
            hand_r = (304, 208 - int(16 * self.spit_progress))
        else:
            hand_l = (140, 366)
            hand_r = (330, 366)
        for shoulder, hand in (((168, 226), hand_l), ((302, 226), hand_r)):
            elbow = (int((shoulder[0] + hand[0]) / 2) + (18 if shoulder[0] < 235 else -18), 292)
            pygame.draw.line(surf, shirt_dark, shoulder, elbow, 34)
            pygame.draw.line(surf, skin, elbow, hand, 24)
            pygame.draw.circle(surf, skin, elbow, 12)
            pygame.draw.circle(surf, skin, hand, 17)

        # пупок-лазер
        glow = int(60 + 120 * self.laser_glow)
        if self.laser_glow > 0:
            pygame.draw.circle(surf, (255, 120, 80), (cx, 398), int(34 * self.laser_glow) + 6)
        pygame.draw.circle(surf, (86, 46, 36), (cx, 398), 13)
        pygame.draw.circle(surf, (46, 26, 24), (cx, 398), 8)
        if self.laser_glow > 0:
            pygame.draw.circle(surf, (255, 220, 170), (cx, 398), 5)

        # голова
        pygame.draw.circle(surf, skin, (cx, 150), 54)
        # чёлка
        pygame.draw.polygon(surf, hair, [
            (182, 130), (196, 96), (235, 88), (274, 96), (288, 130),
            (268, 116), (252, 128), (235, 112), (214, 128),
        ])
        # глаза, брови, ухмылка, второй подбородок
        pygame.draw.circle(surf, (34, 28, 30), (214, 148), 4)
        pygame.draw.circle(surf, (34, 28, 30), (256, 148), 4)
        pygame.draw.arc(surf, (70, 48, 40), (200, 128, 28, 18), 3.4, 6.0, 3)
        pygame.draw.arc(surf, (70, 48, 40), (242, 128, 28, 18), 3.4, 6.0, 3)
        if self.state == "spit":
            pygame.draw.ellipse(surf, (86, 40, 42), (214, 160, 44, 30))
            pygame.draw.ellipse(surf, (196, 88, 82), (224, 172, 24, 14))
            drool = 4 + int(8 * self.spit_progress)
            pygame.draw.line(surf, (154, 206, 120), (240, 184), (240, 184 + drool), 3)
        else:
            pygame.draw.arc(surf, (120, 64, 56), (210, 164, 50, 26), 3.4, 5.9, 3)
        pygame.draw.arc(surf, (196, 146, 116), (196, 186, 78, 30), 3.3, 6.0, 2)
        pygame.draw.circle(surf, (214, 156, 126), (235, 160), 3)

        # испачканная футболка
        pygame.draw.ellipse(surf, (74, 118, 66), (196, 268, 60, 34))
        pygame.draw.ellipse(surf, (54, 96, 52), (210, 278, 34, 20))

        # бургер в руке
        if self.state == "eat" and self.eat_progress > 0.15:
            bx, by = hand_r
            by -= 14
            pygame.draw.ellipse(surf, (206, 158, 86), (bx - 20, by - 10, 40, 14))
            pygame.draw.rect(surf, (120, 74, 40), (bx - 18, by - 2, 36, 7), border_radius=3)
            pygame.draw.ellipse(surf, (96, 160, 72), (bx - 16, by - 5, 32, 6))
            pygame.draw.ellipse(surf, (216, 170, 96), (bx - 20, by + 2, 40, 12))

        if self.hit > 0:
            flash = pygame.Surface((470, 500), pygame.SRCALPHA)
            pygame.draw.ellipse(flash, (255, 255, 255, int(70 * self.hit)), (60, 160, 350, 300))
            surf.blit(flash, (0, 0))
        return surf

    def draw(self, screen):
        surf = self._surface()
        bob = math.sin(self.t * 1.7) * 3.0
        top = self.feet - 486 + bob
        if self.state == "dying":
            angle = min(82.0, self.death * 110)
            image = pygame.transform.rotozoom(surf, -angle, 1.0)
            screen.blit(image, (int(self.x - image.get_width() / 2),
                                int(self.feet - image.get_height() + bob + angle * 0.8)))
        elif self.state == "spin":
            sway = math.sin(self.spin_angle) * 9.0
            image = pygame.transform.rotozoom(surf, sway, 1.0)
            # следы вертушки
            trail = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            for k in range(3):
                radius = 150 + k * 34
                rect = pygame.Rect(0, 0, radius * 2, int(radius * 0.7))
                rect.center = (int(self.x), int(self.feet - 170))
                pygame.draw.arc(trail, (255, 220, 160, 70 - k * 18), rect,
                                self.spin_angle + k, self.spin_angle + k + 2.1, 4)
            screen.blit(trail, (0, 0))
            screen.blit(image, (int(self.x - image.get_width() / 2 + sway * 0.6),
                                int(self.feet - image.get_height() + bob)))
        elif self.state == "pound" and self.pound_phase > 0.55:
            # приседание от удара по земле
            squash = 0.92
            image = pygame.transform.smoothscale(
                surf, (int(surf.get_width() * 1.05), int(surf.get_height() * squash)))
            screen.blit(image, (int(self.x - image.get_width() / 2),
                                int(self.feet - image.get_height() + 6)))
        else:
            shake = math.sin(self.t * 40) * 3 if self.hit > 0.2 else 0
            screen.blit(surf, (int(self.x - 235 + shake), int(top)))


class Battle:
    """Сражение армии из 100 человек с боссом."""

    def __init__(self, soldiers):
        self.time = 0.0
        self.win_chance = win_chance(soldiers)
        self.victory = random.random() < self.win_chance
        self.boss = Boss()
        self.soldiers = []
        self.spears = []
        self.spits = []
        self.waves = []
        self.particles = []
        self.texts = []
        self.kill_acc = 0.0
        self.shake = 0.0
        self._shake_surface = None
        self.result = None
        self.result_timer = 0.0
        self.finished = False
        self.attack_timer = 0.75
        self.boss_hp_shown = 1.0
        self.navel_text_timer = 6.0
        self.arena = self._build_arena()
        self._place_soldiers(soldiers)

    # ----- подготовка -----
    def _build_arena(self):
        surf = pygame.Surface((WIDTH, HEIGHT)).convert()
        for y in range(HEIGHT):
            t = min(1.0, y / (HEIGHT - 1) * 1.35)
            surf.fill(lerp_color((16, 18, 30), (52, 34, 30), t), (0, y, WIDTH, 1))
        pygame.draw.circle(surf, (226, 214, 184), (742, 104), 46)
        pygame.draw.circle(surf, (242, 232, 204), (742, 104), 34)
        # далёкие горы
        pygame.draw.polygon(surf, (26, 26, 42), [(0, 470), (190, 300), (390, 470)])
        pygame.draw.polygon(surf, (22, 22, 36), [(260, 480), (520, 270), (790, 480)])
        pygame.draw.polygon(surf, (28, 26, 40), [(640, 480), (900, 320), (1180, 480)])
        # поле боя
        pygame.draw.rect(surf, (58, 46, 36), (0, 512, WIDTH, HEIGHT - 512))
        pygame.draw.rect(surf, (74, 58, 42), (0, 512, WIDTH, 8))
        rng = random.Random(4)
        for _ in range(220):
            x = rng.randrange(0, WIDTH)
            y = rng.randrange(524, HEIGHT - 6)
            surf.fill(rng.choice(((52, 42, 34), (64, 50, 40), (44, 36, 30))),
                      (x, y, rng.choice((2, 3)), rng.choice((1, 2))))
        return surf

    def _place_soldiers(self, soldiers):
        army = list(soldiers[:ARMY_TARGET])
        random.shuffle(army)
        ranged_count = int(len(army) * BATTLE_RANGED_SHARE)
        for index, soldier in enumerate(army):
            if index < ranged_count:
                col = index % 12
                row = index // 12
                x = 44 + col * 46 + random.uniform(-6, 6)
                y = 548 + row * 21
                self.soldiers.append(BattleSoldier(soldier, "ranged", x, y))
            else:
                k = index - ranged_count
                col = k % 8
                row = k // 8
                x = 598 + col * 20 + random.uniform(-4, 4)
                y = 552 + row * 20
                self.soldiers.append(BattleSoldier(soldier, "melee", x, y))

    # ----- бой -----
    def throw_spear(self, soldier):
        if self.result is not None and self.result != "victory":
            pass
        tx = self.boss.x - random.uniform(10, 150)
        ty = self.boss.feet - random.uniform(150, 330)
        self.spears.append(Spear(soldier.x + 12, soldier.y - 40, tx, ty))

    def melee_hit(self, soldier):
        self.boss.hit = max(self.boss.hit, 0.16)
        for _ in range(2):
            self.particles.append(Particle(
                self.boss.x - 160 + random.uniform(-16, 16),
                self.boss.feet - 190 + random.uniform(-40, 40),
                random.uniform(-40, 90), random.uniform(-140, 20),
                random.uniform(0.2, 0.5), (255, 226, 170), random.uniform(1.5, 3.0)))

    def _burst(self, x, y, color, count=8):
        for _ in range(count):
            self.particles.append(Particle(
                x + random.uniform(-8, 8), y + random.uniform(-8, 8),
                random.uniform(-120, 120), random.uniform(-170, 40),
                random.uniform(0.3, 0.8), color, random.uniform(1.4, 3.2)))

    def kill_one(self):
        alive = [s for s in self.soldiers if s.alive]
        if not alive:
            return
        victim = random.choice(alive)
        victim.kill()
        self._burst(victim.x, victim.y - 26, (150, 54, 48), 8)

    def kill_near(self, x, y):
        alive = [s for s in self.soldiers if s.alive]
        if not alive:
            return
        victim = min(alive, key=lambda s: (s.x - x) ** 2 + (s.y - y) ** 2)
        victim.kill()
        self._burst(victim.x, victim.y - 26, (150, 54, 48), 8)

    def _attack(self):
        """Босс выбирает атаку по весам — чем дальше бой, тем чаще бьёт."""
        roll = random.random()
        if roll < STRIKE_CHANCE:
            # обычный удар лапой
            self.boss.play_attack()
            for _ in range(random.randint(1, 2)):
                self.kill_one()
            self.shake = max(self.shake, 5.0)
            self._burst(self.boss.x - 170, self.boss.feet - 120, (120, 90, 60), 6)
        elif roll < STRIKE_CHANCE + POUND_CHANCE:
            # топот: две ударные волны по земле
            self.boss.start_pound()
            self.waves.append(Shockwave(self.boss.x, self.boss.feet - 8, 0.22))
            self.waves.append(Shockwave(self.boss.x, self.boss.feet - 8, 0.52))
            for _ in range(random.randint(3, 4)):
                self.kill_one()
            self.shake = max(self.shake, 15.0)
            for _ in range(26):
                self.particles.append(Particle(
                    self.boss.x - 300 + random.uniform(-200, 200), self.boss.feet - 10,
                    random.uniform(-160, 160), random.uniform(-220, -40),
                    random.uniform(0.4, 0.9), (176, 142, 96), random.uniform(1.6, 3.4)))
            self.texts.append(FloatingText("ТОПОТ!", self.boss.x, self.boss.feet - 430,
                                           (240, 196, 128), life=1.2, font_key="bold"))
        elif roll < STRIKE_CHANCE + POUND_CHANCE + SPIT_CHANCE:
            # плевок в трёх бойцов
            alive = [s for s in self.soldiers if s.alive]
            if not alive:
                return
            targets = random.sample(alive, min(3, len(alive)))
            target = random.choice(targets)
            self.boss.start_spit((target.x, target.y - 20))
            for soldier in targets:
                self.spits.append(Spit(self.boss.x - 26, self.boss.feet - 318,
                                       soldier.x, soldier.y - 26))
            self.shake = max(self.shake, 4.0)
            self.texts.append(FloatingText("ПЛЕВОК!", self.boss.x, self.boss.feet - 430,
                                           (176, 226, 130), life=1.2, font_key="bold"))
        elif roll < STRIKE_CHANCE + POUND_CHANCE + SPIT_CHANCE + SPIN_CHANCE:
            # вертушка: разбрасывает ближний бой
            self.boss.start_spin()
            for _ in range(random.randint(3, 5)):
                self.kill_one()
            self.shake = max(self.shake, 11.0)
            for _ in range(20):
                angle = random.uniform(0, math.tau)
                speed = random.uniform(140, 320)
                self.particles.append(Particle(
                    self.boss.x + math.cos(angle) * 120, self.boss.feet - 170 + math.sin(angle) * 80,
                    math.cos(angle) * speed, math.sin(angle) * speed - 40,
                    random.uniform(0.3, 0.7), (240, 208, 150), random.uniform(1.5, 3.0)))
            self.texts.append(FloatingText("ВЕРТУШКА!", self.boss.x, self.boss.feet - 430,
                                           (255, 210, 150), life=1.2, font_key="bold"))
        elif roll < STRIKE_CHANCE + POUND_CHANCE + SPIT_CHANCE + SPIN_CHANCE + LASER_CHANCE:
            # лазер из пупка
            alive = [s for s in self.soldiers if s.alive]
            if not alive:
                return
            target = random.choice(alive)
            self.boss.start_laser((target.x, target.y - 20))
            for _ in range(3):
                self.kill_one()
            self.shake = max(self.shake, 8.0)
            self.texts.append(FloatingText("ЛАЗЕР ИЗ ПУПКА!", self.boss.x, self.boss.feet - 430,
                                           (255, 140, 90), life=1.6, font_key="title"))
            self._burst(self.boss.x, self.boss.feet - 98, (255, 160, 90), 18)
        else:
            # бургер: лечится
            self.boss.start_eat()
            self.boss.hp = min(self.boss.max_hp, self.boss.hp + self.boss.max_hp * BOSS_HEAL_SHARE)
            self.texts.append(FloatingText(f"БУРГЕР! +{int(BOSS_HEAL_SHARE * 100)}%",
                                           self.boss.x, self.boss.feet - 430,
                                           (140, 226, 140), life=1.6, font_key="title"))
            self._burst(self.boss.x, self.boss.feet - 330, (130, 220, 130), 16)

    def update(self, dt):
        self.time += dt
        self.boss.update(dt)
        self.boss.hp = max(0, min(self.boss.max_hp, self.boss.hp))
        if self.shake > 0:
            self.shake = max(0.0, self.shake - dt * 22.0)
        for soldier in self.soldiers:
            soldier.update(dt, self)

        for spear in list(self.spears):
            if not spear.update(dt):
                self.spears.remove(spear)
                self.boss.hit = max(self.boss.hit, 0.22)
                self._burst(spear.tx, spear.ty, (255, 220, 150), 5)

        for spit in list(self.spits):
            if not spit.update(dt):
                self.spits.remove(spit)
                self._burst(spit.tx, spit.ty, (154, 214, 110), 9)
                self.kill_near(spit.tx, spit.ty)

        for wave in list(self.waves):
            if not wave.update(dt):
                self.waves.remove(wave)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]
        for text in self.texts:
            text.update(dt)
        self.texts = [t for t in self.texts if t.life > 0]

        if self.boss.state == "dying":
            if self.boss.dead and self.result_timer <= 0 and self.result == "victory":
                self.result_timer = 2.6
            if self.result_timer > 0:
                self.result_timer -= dt
                if self.result_timer <= 0:
                    self.finished = True
            return

        if self.result is not None:
            self.result_timer -= dt
            if self.result_timer <= 0:
                self.finished = True
            return

        progress = min(1.0, self.time / BATTLE_DURATION)
        # босс теряет здоровье; при поражении армии застревает на ~20%
        damage_share = 1.0 if self.victory else 0.8
        target_hp = self.boss.max_hp * (1.0 - damage_share * progress)
        if self.boss.state != "eat" and self.boss.hp > target_hp:
            self.boss.hp = max(target_hp, self.boss.hp - self.boss.max_hp * 0.9 * dt)
        elif self.boss.hp < target_hp - self.boss.max_hp * 0.02:
            self.boss.hp = min(target_hp, self.boss.hp + self.boss.max_hp * 0.25 * dt)

        self.attack_timer -= dt
        if self.attack_timer <= 0:
            # к концу боя босс звереет и бьёт чаще
            self.attack_timer = random.uniform(0.62, 1.12) * (1.0 - 0.18 * progress)
            self._attack()

        self.navel_text_timer -= dt
        if self.navel_text_timer <= 0:
            self.navel_text_timer = random.uniform(7.0, 10.5)
            self.texts.append(FloatingText("ГДЕ МОИ НОГИ?", self.boss.x, self.boss.feet - 430,
                                           (228, 216, 194), life=2.2, font_key="bold"))

        self.kill_acc += (2.8 if self.victory else 11.5) * dt
        while self.kill_acc >= 1:
            self.kill_acc -= 1
            if not any(s.alive for s in self.soldiers):
                break
            self.kill_one()

        army_wiped = not any(s.alive for s in self.soldiers)
        if progress >= 1.0 or (army_wiped and not self.victory):
            if self.victory and not army_wiped:
                self.boss.hp = 0
                self.boss.start_death()
                self.result = "victory"
                self._burst(self.boss.x, self.boss.feet - 200, (255, 190, 100), 40)
                self.texts.append(FloatingText("БОСС ПОВЕРЖЕН!", WIDTH // 2, 250,
                                               GOLD, life=3.0, font_key="title"))
            else:
                for soldier in self.soldiers:
                    soldier.kill()
                self.boss.hp = max(self.boss.hp, self.boss.max_hp * 0.18)
                self.result = "defeat"
                self.result_timer = 3.4
                self.texts.append(FloatingText("АРМИЯ ПАЛА", WIDTH // 2, 250,
                                               RED, life=3.0, font_key="title"))

    # ----- отрисовка -----
    def draw(self, screen, sprites, fonts, sim):
        world = screen
        ox = oy = 0
        if self.shake > 0.4:
            if self._shake_surface is None:
                self._shake_surface = pygame.Surface((WIDTH, HEIGHT)).convert()
            world = self._shake_surface
            ox = random.randint(-int(self.shake), int(self.shake))
            oy = random.randint(-int(self.shake * 0.6), int(self.shake * 0.6))

        world.blit(self.arena, (0, 0))

        # ударные волны от топота
        for wave in self.waves:
            wave.draw(world)

        # босс
        self.boss.draw(world)

        # лазер из пупка
        if self.boss.state == "laser" and self.boss.laser_to is not None:
            start = (self.boss.x, self.boss.feet - 88)
            end = self.boss.laser_to
            width = 10 + int(6 * self.boss.laser_glow)
            glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.line(glow, (255, 90, 60, 70), start, end, width + 14)
            pygame.draw.line(glow, (255, 150, 80, 160), start, end, width + 6)
            pygame.draw.line(glow, (255, 244, 210, 230), start, end, width)
            world.blit(glow, (0, 0))
            pygame.draw.circle(world, (255, 230, 190), (int(start[0]), int(start[1])), 16)

        # бойцы
        for soldier in sorted(self.soldiers, key=lambda s: s.y):
            soldier.draw(world, sprites, self)

        # копья и плевки
        for spear in self.spears:
            spear.draw(world)
        for spit in self.spits:
            spit.draw(world)

        # частицы
        for particle in self.particles:
            alpha = max(0.0, particle.life / particle.max_life)
            radius = max(1, int(particle.radius))
            dot = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*particle.color, int(220 * alpha)), (radius, radius), radius)
            world.blit(dot, (int(particle.x - radius), int(particle.y - radius)))

        if world is not screen:
            screen.fill((0, 0, 0))
            screen.blit(world, (ox, oy))

        # тексты
        for text in self.texts:
            alpha = int(255 * min(1.0, text.life * 2.0))
            font = getattr(fonts, text.font_key)
            image = font.render(text.text, True, text.color)
            outline = font.render(text.text, True, (10, 8, 12))
            image.set_alpha(alpha)
            outline.set_alpha(alpha)
            px = int(text.x - image.get_width() / 2)
            py = int(text.y)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                screen.blit(outline, (px + dx, py + dy))
            screen.blit(image, (px, py))

        # полоса здоровья босса
        bar = pygame.Rect(WIDTH // 2 - 240, 16, 480, 58)
        draw_panel(screen, bar, alpha=170)
        label = fonts.small.render("ОГРОМНЫЙ ПАРЕНЬ В ЗЕЛЁНОЙ ФУТБОЛКЕ", True, GOLD)
        screen.blit(label, (bar.x + 12, bar.y + 5))
        chance = fonts.small.render(f"шанс победы {self.win_chance * 100:.0f}%",
                                    True, (230, 220, 200))
        screen.blit(chance, (bar.right - 12 - chance.get_width(), bar.y + 5))
        hp_text = fonts.small.render(f"HP {self.boss.hp / self.boss.max_hp * 100:.0f}%",
                                     True, (245, 240, 230))
        screen.blit(hp_text, (bar.right - 12 - hp_text.get_width(), bar.y + 22))
        alive = sum(1 for s in self.soldiers if s.alive)
        losses = percent(ARMY_TARGET - alive, ARMY_TARGET)
        loss_text = fonts.small.render(f"потери {losses} · живых {alive}/{ARMY_TARGET}",
                                       True, (226, 176, 168))
        screen.blit(loss_text, (bar.x + 12, bar.y + 22))
        hp_w = int((bar.w - 24) * (self.boss.hp / self.boss.max_hp))
        pygame.draw.rect(screen, (48, 30, 32), (bar.x + 12, bar.y + 42, bar.w - 24, 8), border_radius=4)
        pygame.draw.rect(screen, (196, 66, 58), (bar.x + 12, bar.y + 42, hp_w, 8), border_radius=4)

        # итог
        if self.result is not None:
            banner = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            banner.fill((0, 0, 0, 90))
            screen.blit(banner, (0, 0))
            if self.result == "victory":
                title, color, sub = "ПОБЕДА", GOLD, "армия сражается и уходит с трофеями"
            else:
                title, color, sub = "ПОРАЖЕНИЕ", RED, "босс даже не вспотел"
            image = fonts.title.render(title, True, color)
            screen.blit(image, (WIDTH // 2 - image.get_width() // 2, 286))
            sub_image = fonts.bold.render(sub, True, (234, 230, 220))
            screen.blit(sub_image, (WIDTH // 2 - sub_image.get_width() // 2, 330))


# ─────────────────────────── СИМУЛЯЦИЯ ───────────────────────────
class Simulation:
    def __init__(self):
        self.spartan_genomes: list[Genome] = []
        self.fitness_history: list[float] = []
        self.reset()

    # ---------- жизненный цикл ----------
    def reset(self):
        self.time = 0.0
        self.children: list[Child] = []
        self.spartans: list[Spartan] = []
        self.army: list[Soldier] = []
        self.marchers: list[Soldier] = []
        self.pending_army: list[Soldier] | None = None
        self.battle: Battle | None = None
        self.battle_delay = 0.0
        self.victories = 0
        self.pool: list[Genome] = []
        self.particles: list[Particle] = []
        self.texts: list[FloatingText] = []
        self.fx: list = []
        self.bubble = None
        self.flash = 0.0
        self.fitness_history.clear()
        self.spartan_genomes.clear()

        self.born = 0
        self.approved = 0
        self.culled = 0
        self.executed = 0
        self.survivors = 0
        self.wars = 0
        self.generation = 1

        self.spawn_timer = 1.0
        self.spawn_interval = 2.0
        self.sneeze_timer = 2.5
        self.speed = 1.0
        self.paused = False

        # «начинается всё с одного» — первый ребёнок уже идёт на проверку
        self.children.append(self.make_child())

    # ---------- рождение ----------
    def make_child(self) -> Child:
        parents = self.pool + self.spartan_genomes
        father = mother = None
        if len(parents) >= 2 and random.random() < 0.85:
            weights = [max(0.05, g.fitness()) ** 2 for g in parents]
            father, mother = random.choices(parents, weights=weights, k=2)
            father_stats = father.effective_stats()
            mother_stats = mother.effective_stats()
            stats = {
                key: clamp((father_stats[key] + mother_stats[key]) * 0.5 + random.gauss(0, 0.03))
                for key in STAT_KEYS
            }
            generation = max(father.generation, mother.generation) + 1
            origin = "bred"
        else:
            stats = {key: clamp(random.uniform(0.30, 0.62)) for key in STAT_KEYS}
            generation = 1
            origin = "found"

        mutations = self.roll_mutations()
        for mutation in mutations:
            stats[mutation.stat] = clamp(stats[mutation.stat] + mutation.delta)

        genome = Genome(stats=stats, generation=generation)
        self.apply_disease(genome, father, mother)

        self.generation = max(self.generation, generation)
        self.born += 1
        return Child(genome, mutations, origin)

    @staticmethod
    def apply_disease(genome: Genome, father=None, mother=None):
        """Ребёнок может унаследовать болезнь родителей или подхватить новую."""
        sick_parent = next(
            (p for p in (father, mother) if p is not None and p.is_sick()), None
        )
        if sick_parent is not None and random.random() < 0.40:
            genome.disease = sick_parent.disease
            genome.disease_mult = dict(sick_parent.disease_mult)
            genome.disease_left = sick_parent.disease_left * random.uniform(0.7, 1.2)
            return
        if random.random() < 0.20:
            disease = random.choices(DISEASES, weights=[d.weight for d in DISEASES], k=1)[0]
            genome.disease = disease.name
            genome.disease_mult = dict(disease.multipliers)
            genome.disease_left = disease.duration

    @staticmethod
    def roll_mutations():
        if random.random() > 0.62:
            return []
        count = 1 if random.random() < 0.8 else 2
        mutations = []
        for _ in range(count):
            catalog = POSITIVE_MUTATIONS if random.random() < 0.45 else NEGATIVE_MUTATIONS
            mutations.append(random.choice(catalog))
        return mutations

    # ---------- события ----------
    def on_event(self, kind: str, child: Child):
        if kind == "judged":
            if child.fate == "200":
                # спартанец говорит «200» — приговора нет, ребёнок умирает на месте
                self.bubble = SpeechBubble("200", INSPECTOR_X, GROUND_Y - 232, 2.0)
            elif child.fate == "legit":
                gift = next((m.name for m in child.mutations if m.positive), None)
                label = f"ЛЕГИТ · {gift}" if gift else "ЛЕГИТ"
                self.texts.append(FloatingText(label, child.x, child.y - 140, GOLD, font_key="title"))
                self.burst(child.x, child.y - 46, GOLD, 8)
                if child.has("АЛЬТУХА С 3 РАЗМЕРОМ") or child.has("КРАСТИН"):
                    # превращение
                    self.burst(child.x, child.y - 46, (240, 120, 190), 18)
            else:
                flaw = next(m.name for m in child.mutations if not m.positive)
                self.texts.append(
                    FloatingText(f"НЕ ЛЕГИТ · {flaw}", child.x, child.y - 140, RED, font_key="title")
                )
                if child.fate == "meteor":
                    self.fx.append(Meteor(child))
                    self.texts.append(
                        FloatingText("МЕТЕОРИТ!", child.x, child.y - 186, (255, 172, 96), font_key="bold")
                    )
                self.burst(child.x, child.y - 46, (150, 60, 60), 8)

        elif kind == "approved":
            self.approved += 1
            self.pool.append(child.genome)
            self.fitness_history.append(child.genome.fitness())
            if len(self.fitness_history) > 600:
                del self.fitness_history[:100]
            # распределяем место в армии
            child.slot = self.free_slot()
            child.target_x = float(ARMY_X0 + (child.slot % ARMY_COLS) * ARMY_DX)
            child.target_y = float(ARMY_Y0 + ((child.slot // ARMY_COLS) % ARMY_ROWS) * ARMY_DY)
            self.burst(child.x, child.y - 46, GOLD, 12)
            # турнирный отбор: слабейшие гены выбывают из пула
            if len(self.pool) > 120:
                self.pool.sort(key=lambda g: g.fitness(), reverse=True)
                del self.pool[100:]

        elif kind == "enlisted":
            self.army.append(Soldier(child.slot, child.look, genome=child.genome))
            if len(self.army) >= ARMY_TARGET:
                self.start_march()

        elif kind == "dead":
            self.culled += 1
            self.burst(child.x, FALL_LIMIT, (140, 54, 48), 18)

        elif kind == "boom":
            self.fx.append(Explosion(child.x, child.y - 44, radius=130))
            self.flash = max(self.flash, 0.65)
            self.burst(child.x, child.y - 44, (255, 190, 90), 34)
            self.burst(child.x, child.y - 44, (120, 60, 40), 16)

        elif kind == "execute":
            self.texts.append(
                FloatingText("КАЗНЁН НА МЕСТЕ", child.x, child.y - 186, RED, font_key="title")
            )
            self.burst(child.x, child.y - 46, (120, 44, 44), 18)

        elif kind == "killed":
            self.executed += 1
            self.burst(child.x, child.y - 34, (92, 34, 34), 12)

        elif kind == "miraculous":
            self.survivors += 1
            self.texts.append(FloatingText("ВЫЖИЛ! 1%", child.x, FALL_LIMIT - 120, WHITE, font_key="title"))
            self.burst(child.x, child.y, (250, 240, 210), 22)

        elif kind == "joined":
            index = len(self.spartans)
            x = 352 + (index % 7) * 36
            self.spartans.append(Spartan(x))
            self.spartan_genomes.append(child.genome)
            if len(self.spartan_genomes) > 40:
                self.spartan_genomes.sort(key=lambda g: g.fitness(), reverse=True)
                del self.spartan_genomes[30:]
            self.texts.append(FloatingText("В РЯДЫ СПАРТАНЦЕВ", x, PLATEAU_Y - 112, GOLD))
            self.burst(x, PLATEAU_Y - 30, GOLD, 16)

    # ---------- армия ----------
    def free_slot(self) -> int:
        used = {soldier.slot for soldier in self.army}
        used |= {c.slot for c in self.children if c.slot is not None and c.state == "to_army"}
        for index in range(ARMY_TARGET):
            if index not in used:
                return index
        return 0

    def start_march(self):
        self.marchers.extend(self.army)
        self.pending_army = list(self.army)
        self.army.clear()
        self.battle_delay = 1.5
        self.wars += 1
        self.texts.append(
            FloatingText("ВОЙСКО УХОДИТ НА ВОЙНУ", WIDTH // 2, 418, GOLD, life=2.6, font_key="title")
        )

    # ---------- эффекты ----------
    def update_fx(self, dt):
        for effect in list(self.fx):
            if not effect.update(dt):
                self.fx.remove(effect)
                if isinstance(effect, Meteor):
                    self.on_meteor_impact(effect)

    def on_meteor_impact(self, meteor):
        x, y = meteor.x, meteor.y
        self.fx.append(Explosion(x, y, radius=130, color=(255, 150, 60), life=0.7))
        self.flash = max(self.flash, 0.6)
        self.burst(x, y, (255, 200, 120), 30)
        self.burst(x, y, (130, 70, 40), 18)
        self.texts.append(FloatingText("БУМ!", x, y - 96, (255, 190, 100), font_key="title"))
        meteor.target.start_death()

    # ---------- эффекты ----------
    def burst(self, x, y, color, count=10):
        for _ in range(count):
            self.particles.append(
                Particle(
                    x + random.uniform(-6, 6),
                    y + random.uniform(-6, 6),
                    random.uniform(-110, 110),
                    random.uniform(-150, 10),
                    random.uniform(0.35, 0.9),
                    color,
                    random.uniform(1.5, 3.4),
                )
            )

    # ---------- шаг симуляции ----------
    def update(self, dt: float):
        # большие dt (ускорение x100) режем на мелкие шаги, чтобы физика не ломалась
        if dt > MAX_STEP:
            steps = min(600, int(math.ceil(dt / MAX_STEP)))
            step = dt / steps
            for _ in range(steps):
                self._advance(step)
        else:
            self._advance(dt)

    def tick_diseases(self, dt: float):
        for genome in self.pool:
            genome.tick(dt)
        for genome in self.spartan_genomes:
            genome.tick(dt)
        for soldier in self.army:
            if soldier.genome is not None:
                soldier.genome.tick(dt)
        if self.pending_army:
            for soldier in self.pending_army:
                if soldier.genome is not None:
                    soldier.genome.tick(dt)

    def _advance(self, dt: float):
        self.time += dt
        self.tick_diseases(dt)

        if self.battle is not None:
            self.battle.update(dt)
            if self.battle.finished:
                if self.battle.result == "victory":
                    self.victories += 1
                self.battle = None
                self.marchers.clear()
                self.spawn_timer = 0.8
            return

        for child in list(self.children):
            for kind, subject in child.update(dt):
                self.on_event(kind, subject)

        self.children = [c for c in self.children if c.state != "gone"]

        for particle in self.particles:
            particle.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        for text in self.texts:
            text.update(dt)
        self.texts = [t for t in self.texts if t.life > 0]

        self.update_fx(dt)

        for soldier in self.marchers:
            soldier.x -= ARMY_SPEED * dt
        self.marchers = [s for s in self.marchers if s.x > -60]

        if self.bubble is not None:
            self.bubble.update(dt)
            if self.bubble.life <= 0:
                self.bubble = None

        self.flash = max(0.0, self.flash - dt * 2.4)

        self.sneeze_timer -= dt
        if self.sneeze_timer <= 0:
            self.sneeze_timer = random.uniform(2.0, 3.8)
            sick = [c for c in self.children if c.genome.is_sick()]
            if sick:
                victim = random.choice(sick)
                self.texts.append(FloatingText("апчхи!", victim.x, victim.y - 124,
                                               (150, 214, 150), life=1.0, font_key="tiny"))

        if self.pending_army is not None:
            self.battle_delay -= dt
            if self.battle_delay <= 0:
                self.battle = Battle(self.pending_army)
                self.pending_army = None
                self.marchers.clear()
                self.texts.clear()
            return

        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            if len(self.children) < 8:
                self.children.append(self.make_child())
            self.spawn_timer = self.spawn_interval

    # ---------- отрисовка ----------
    def draw_soldiers(self, screen, sprites, soldiers, marching=False):
        for soldier in sorted(soldiers, key=lambda s: s.y):
            sprite = sprites.child(soldier.look, ARMY_SCALE)
            bob = math.sin(self.time * (11.0 if marching else 6.0) + soldier.phase) * 1.6
            x, y = int(soldier.x), int(soldier.y + bob)
            pygame.draw.line(screen, (118, 86, 52), (x + 9, y - 46), (x + 12, y - 4), 2)
            pygame.draw.polygon(screen, (206, 210, 216),
                                [(x + 12, y - 51), (x + 9, y - 44), (x + 14, y - 44)])
            screen.blit(sprite, (x - sprite.get_width() // 2, y - sprite.get_height()))
            if soldier.genome is not None and soldier.genome.is_sick():
                draw_sick_mark(screen, x, y - sprite.get_height() - 7, 0.85)

    def draw(self, screen, sprites, fonts):
        if self.battle is not None:
            self.battle.draw(screen, sprites, fonts, self)
            self.draw_hud(screen, fonts)
            self.draw_hints(screen, fonts)
            if self.paused:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 110))
                screen.blit(overlay, (0, 0))
                pause = fonts.title.render("ПАУЗА", True, WHITE)
                screen.blit(pause, (WIDTH // 2 - pause.get_width() // 2,
                                    HEIGHT // 2 - pause.get_height() // 2))
            return

        # спасённые спартанцы на площадке
        for spartan in self.spartans[:7]:
            bob = math.sin(self.time * 2.0 + spartan.phase) * 1.2
            draw_figure(screen, sprites.spartan, spartan.x, PLATEAU_Y + bob)

        # инспектор
        bob = math.sin(self.time * 1.7) * 1.1
        draw_figure(screen, sprites.inspector, INSPECTOR_X, GROUND_Y + bob)

        # армия и уходящие на войну
        self.draw_soldiers(screen, sprites, self.army)
        self.draw_soldiers(screen, sprites, self.marchers, marching=True)

        # дети
        for child in self.children:
            sprite = sprites.child(child.look)
            if child.negative:
                glow = sprites.glow_red
            elif child.mutations:
                glow = sprites.glow_gold
            else:
                glow = None
            if glow is not None:
                screen.blit(glow, (int(child.x - glow.get_width() / 2),
                                   int(child.y - 56 - glow.get_height() / 2)))

            moving = child.state in ("walk_in", "to_edge", "to_army")
            walk_bob = math.sin(self.time * 9.0 + child.phase) * 2.0 if moving else 0.0
            if moving and child.look.fast:
                for k in range(2):
                    ly = int(child.y - 44 - k * 16)
                    pygame.draw.line(screen, (198, 198, 206),
                                     (int(child.x - 34 - k * 7), ly),
                                     (int(child.x - 20 - k * 7), ly), 2)
            jitter = math.sin(self.time * 42.0 + child.phase) * 1.4 if child.look.trembling else 0.0
            draw_figure(screen, sprite, child.x + jitter, child.y, bob=walk_bob, angle=child.angle)
            self.draw_badges(screen, child, fonts)

        # эффекты: метеорит, взрывы
        for effect in self.fx:
            effect.draw(screen)

        # частицы
        for particle in self.particles:
            alpha = max(0.0, particle.life / particle.max_life)
            radius = max(1, int(particle.radius))
            dot = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*particle.color, int(220 * alpha)), (radius, radius), radius)
            screen.blit(dot, (int(particle.x - radius), int(particle.y - radius)))

        # всплывающий текст (с тёмной обводкой, чтобы читался на любом фоне)
        for text in self.texts:
            alpha = int(255 * min(1.0, text.life * 2.0))
            font = getattr(fonts, text.font_key)
            image = font.render(text.text, True, text.color)
            outline = font.render(text.text, True, (12, 9, 14))
            image.set_alpha(alpha)
            outline.set_alpha(alpha)
            px = int(text.x - image.get_width() / 2)
            py = int(text.y)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                screen.blit(outline, (px + dx, py + dy))
            screen.blit(image, (px, py))

        # реплика спартанца
        if self.bubble is not None:
            self.bubble.draw(screen, fonts)

        # подпись скалы
        label = fonts.small.render("ТАРПЕЙСКАЯ СКАЛА", True, (170, 118, 112))
        screen.blit(label, (GORGE_X + 34, GROUND_Y - 30))

        self.draw_hud(screen, fonts)
        self.draw_chart(screen, fonts)
        self.draw_hints(screen, fonts)

        if self.flash > 0.01:
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 236, 200, int(78 * min(1.0, self.flash))))
            screen.blit(flash, (0, 0))

        if self.paused:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 110))
            screen.blit(overlay, (0, 0))
            pause = fonts.title.render("ПАУЗА", True, WHITE)
            screen.blit(pause, (WIDTH // 2 - pause.get_width() // 2, HEIGHT // 2 - pause.get_height() // 2))

    def draw_badges(self, screen, child: Child, fonts):
        if child.state in ("fall", "saved", "dying", "gone"):
            return
        x = child.x - 16
        if child.mutations:
            if child.positive_count:
                image = fonts.small.render(f"+{child.positive_count}", True, GOLD)
                screen.blit(image, (x, child.y - 106))
                x += image.get_width() + 6
            if child.negative_count:
                image = fonts.small.render(f"-{child.negative_count}", True, RED)
                screen.blit(image, (x, child.y - 106))
        if child.genome.is_sick():
            draw_sick_mark(screen, int(child.x), int(child.y - (124 if child.mutations else 108)))

    def draw_hud(self, screen, fonts):
        panel = pygame.Rect(16, 14, 318, 392)
        draw_panel(screen, panel)

        x = panel.x + 14
        y = panel.y + 10
        title = fonts.title.render("СПАРТА · СЕЛЕКЦИЯ", True, GOLD)
        screen.blit(title, (x, y))
        y += 36

        if self.battle is not None:
            army_now = sum(1 for s in self.battle.soldiers if s.alive)
            chance = f"{self.battle.win_chance * 100:.0f}%"
        elif self.pending_army is not None:
            army_now = len(self.pending_army)
            chance = f"{win_chance(self.pending_army) * 100:.0f}%"
        else:
            army_now = len(self.army)
            chance = "—"

        sick = sum(1 for g in self.pool if g.is_sick())
        sick += sum(1 for s in self.army if s.genome is not None and s.genome.is_sick())
        sick += sum(1 for c in self.children if c.genome.is_sick())
        pop = len(self.pool) + len(self.army) + len(self.children)
        if self.battle is not None:
            sick += sum(1 for s in self.battle.soldiers if s.genome is not None and s.genome.is_sick())
            pop += len(self.battle.soldiers)
        rows = (
            ("Поколение", str(self.generation)),
            ("Рождено детей", str(self.born)),
            ("Одобрено (ЛЕГИТ)", f"{self.approved} · {percent(self.approved, self.born)}"),
            ("Сброшено с обрыва", f"{self.culled} · {percent(self.culled, self.born)}"),
            ("Казнено на месте", f"{self.executed} · {percent(self.executed, self.born)}"),
            ("Выжило (1%)", f"{self.survivors} · {percent(self.survivors, self.culled)}"),
            ("Спартанцев", str(len(self.spartans) + 1)),
            ("Больны", f"{sick} · {percent(sick, pop)}"),
            ("Армия", f"{army_now}/{ARMY_TARGET} · {percent(army_now, ARMY_TARGET)}"),
            ("Войн", f"{self.wars} · побед {self.victories}"),
            ("Шанс победы", chance),
        )
        for label, value in rows:
            label_image = fonts.normal.render(label, True, (198, 196, 200))
            value_image = fonts.normal.render(value, True, WHITE)
            screen.blit(label_image, (x, y))
            screen.blit(value_image, (panel.right - 16 - value_image.get_width(), y))
            y += 22

        y += 2
        recent = self.pool[-25:]
        if recent:
            for key in STAT_KEYS:
                average = sum(g.stats[key] for g in recent) / len(recent)
                label_image = fonts.small.render(f"{STAT_LABELS[key]}  {average * 100:.0f}%", True, (196, 194, 198))
                screen.blit(label_image, (x, y))
                draw_bar(screen, x + 108, y + 3, 168, 9, average, STAT_COLORS[key])
                y += 18
        else:
            note = fonts.small.render("Пул генов пуст — ждём первого ЛЕГИТ", True, (170, 166, 160))
            screen.blit(note, (x, y))

        speed_text = fonts.small.render(
            f"скорость x{self.speed:g}" + ("  ·  ПАУЗА" if self.paused else ""), True, (176, 172, 166)
        )
        screen.blit(speed_text, (panel.right - 16 - speed_text.get_width(), panel.bottom - 24))

    def draw_chart(self, screen, fonts):
        rect = pygame.Rect(WIDTH - 312, 14, 296, 176)
        draw_panel(screen, rect)

        x = rect.x + 14
        y = rect.y + 10
        screen.blit(fonts.bold.render("ПРИСПОСОБЛЕННОСТЬ", True, GOLD), (x, y))
        y += 24

        values = self.fitness_history[-90:]
        if len(values) < 2:
            screen.blit(fonts.small.render("данных пока нет", True, GRAY), (x, rect.bottom - 26))
            return

        smooth = []
        acc = values[0]
        for value in values:
            acc = acc * 0.9 + value * 0.1
            smooth.append(acc)

        low, high = min(smooth), max(smooth)
        if high - low < 0.03:
            high = low + 0.03

        plot = pygame.Rect(x, y, rect.w - 28, rect.h - 66)
        pygame.draw.rect(screen, (26, 26, 32), plot, border_radius=4)

        points = []
        for index, value in enumerate(smooth):
            px = plot.left + index * plot.w / max(1, len(smooth) - 1)
            py = plot.bottom - 6 - (value - low) / (high - low) * (plot.h - 12)
            points.append((px, py))
        pygame.draw.lines(screen, GOLD, False, points, 2)

        mean = sum(values) / len(values)
        caption = fonts.small.render(f"средняя: {mean:.2f}   ·   поколение {self.generation}", True, (198, 194, 186))
        screen.blit(caption, (x, plot.bottom + 8))

    def draw_hints(self, screen, fonts):
        text = "ПРОБЕЛ — ребёнок   ·   P — пауза   ·   1–5 — скорость (5 = x100)   ·   R — сброс   ·   ESC — выход"
        image = fonts.tiny.render(text, True, (206, 202, 196))
        rect = pygame.Rect(WIDTH // 2 - image.get_width() // 2 - 12, HEIGHT - 25,
                           image.get_width() + 24, 20)
        draw_panel(screen, rect, alpha=110)
        screen.blit(image, (rect.x + 12, rect.y + 4))


# ─────────────────────────── СПРАЙТЫ ───────────────────────────
def make_person(scale=1.0, skin=(228, 192, 160), cloth=(120, 150, 190),
                cloak=False, helmet=False, spear=False, shield=False):
    """Рисует человечка в маленький Surface. Ноги — у нижнего края."""
    width, height = int(44 * scale), int(80 * scale)
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    cx = 22
    line = max(2, int(3 * scale))

    def point(x, y):
        return (int(x * scale), int(y * scale))

    if spear:
        pygame.draw.line(surface, (118, 84, 50), point(cx + 10, 6), point(cx + 13, 76), max(2, int(2 * scale)))
        pygame.draw.polygon(surface, (208, 212, 218),
                            [point(cx + 13, 2), point(cx + 8, 12), point(cx + 15, 10)])

    if cloak:
        pygame.draw.polygon(surface, (126, 30, 28),
                            [point(cx - 10, 21), point(cx + 10, 21), point(cx + 12, 64), point(cx - 12, 64)])

    pygame.draw.line(surface, cloth, point(cx - 2, 46), point(cx - 5, 76), line)
    pygame.draw.line(surface, cloth, point(cx + 2, 46), point(cx + 5, 76), line)

    pygame.draw.rect(surface, cloth, pygame.Rect(int((cx - 7) * scale), int(21 * scale),
                                                 int(14 * scale), int(27 * scale)),
                     border_radius=max(1, int(3 * scale)))

    pygame.draw.line(surface, cloth, point(cx - 6, 25), point(cx - 10, 45), line)
    pygame.draw.line(surface, cloth, point(cx + 6, 25), point(cx + 10, 45), line)

    pygame.draw.circle(surface, skin, point(cx, 14), int(7 * scale))

    if helmet:
        pygame.draw.circle(surface, (168, 134, 68), point(cx, 13), int(8.6 * scale))
        pygame.draw.circle(surface, (212, 178, 102), point(cx, 11), int(7.2 * scale))
        pygame.draw.polygon(surface, (188, 44, 40),
                            [point(cx, 0), point(cx + 8, 6), point(cx + 3, 9),
                             point(cx, 5), point(cx - 3, 9), point(cx - 8, 6)])

    if shield:
        pygame.draw.circle(surface, (150, 118, 68), point(cx - 11, 34), int(8.5 * scale))
        pygame.draw.circle(surface, (200, 168, 100), point(cx - 11, 34), int(5.5 * scale))

    return surface


def make_glow(size=52, color=(236, 198, 96), alpha=70):
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    steps = 6
    for step in range(steps, 0, -1):
        radius = int(size / 2 * step / steps)
        layer_alpha = int(alpha * (1 - step / (steps + 1)))
        pygame.draw.circle(surface, (*color, layer_alpha), (size // 2, size // 2), radius)
    return surface


def make_child_sprite(look: Look, scale: float = 1.0):
    """Собирает ребёнка с учётом модификаций. Холст 48x96, ноги — внизу."""
    surface = pygame.Surface((max(1, int(48 * scale)), max(1, int(96 * scale))), pygame.SRCALPHA)
    palette = CHILD_PALETTES[look.variant % len(CHILD_PALETTES)]
    skin = (198, 208, 168) if look.sick else palette["skin"]
    cloth = palette["cloth"]
    hair = (236, 116, 176) if look.outfit == "alt" else palette["hair"]

    def pt(x, y):
        return (int(x * scale), int(y * scale))

    def box(x, y, w, h, color, radius=0):
        pygame.draw.rect(
            surface, color,
            pygame.Rect(int(x * scale), int(y * scale), max(1, int(w * scale)), max(1, int(h * scale))),
            border_radius=max(0, int(radius * scale)),
        )

    def line(x1, y1, x2, y2, color, width=3):
        pygame.draw.line(surface, color, pt(x1, y1), pt(x2, y2), max(1, int(width * scale)))

    def dot(x, y, r, color):
        pygame.draw.circle(surface, color, pt(x, y), max(1, int(r * scale)))

    def poly(color, points):
        pygame.draw.polygon(surface, color, [pt(x, y) for x, y in points])

    body = look.body
    outfit = look.outfit
    torso_w = {"fat": 26, "muscular": 19, "skinny": 10}.get(body, 15)
    torso_x = 24 - torso_w / 2

    if outfit == "ghost":
        # простыня привидения
        poly((243, 243, 236),
             [(15, 13), (33, 13), (35, 88), (31, 83), (27, 89), (23, 83), (19, 89), (13, 85)])
        dot(20, 20, 2.7, (24, 22, 30))
        dot(28, 20, 2.7, (24, 22, 30))
    else:
        naked = outfit == "nude"
        alt = outfit == "alt"
        leg_color = skin if naked else (30, 30, 38) if alt else cloth
        leg_width = 6 if body == "fat" else 4
        line(21, 56, 19, 91, leg_color, leg_width)
        line(27, 56, 29, 91, leg_color, leg_width)
        if alt:
            for i in range(3):
                line(19 + i, 66 + i * 7, 28 + i, 62 + i * 7, (24, 22, 30), 1)
        line(16, 92, 21, 92, (54, 42, 36), 3)
        line(27, 92, 32, 92, (54, 42, 36), 3)

        top_color = {"nude": skin, "alt": (30, 30, 38), "rich": (226, 188, 92)}.get(outfit, cloth)
        box(torso_x, 24, torso_w, 32, top_color, radius=5)
        if body == "fat":
            # большой живот поверх рубашки
            dot(24, 44, 15, top_color)
            dot(24, 47, 9, tuple(int(c * 0.9) for c in top_color))
        if body == "skinny":
            shade = tuple(int(c * 0.8) for c in top_color)
            for ry in (34, 40, 46):
                line(21, ry, 27, ry, shade, 1)
        if body == "muscular":
            dot(24 - torso_w / 2 + 1, 27, 4.2, top_color)
            dot(24 + torso_w / 2 - 1, 27, 4.2, top_color)

        arm_width = {"muscular": 5, "skinny": 2}.get(body, 3)
        line(24 - torso_w / 2 + 1, 29, 24 - torso_w / 2 - 5, 50, leg_color, arm_width)
        line(24 + torso_w / 2 - 1, 29, 24 + torso_w / 2 + 5, 50, leg_color, arm_width)

        line(24, 25, 24, 28, skin, 4)
        dot(24, 17, 8, hair)
        dot(24, 19.5, 6.6, skin)
        if alt:
            line(15.5, 20, 15, 38, hair, 3)
            line(32.5, 20, 33, 38, hair, 3)
            line(20, 26, 28, 26, (24, 24, 28), 2)

        if outfit == "rich":
            pygame.draw.ellipse(surface, (244, 244, 240),
                                pygame.Rect(int(15 * scale), int(22 * scale),
                                            int(18 * scale), int(7 * scale)))
            line(18, 27, 30, 51, (150, 70, 150), 3)
            dot(24, 31, 1.6, (250, 226, 140))
            poly((236, 206, 110), [(19, 10), (21, 3), (23, 10)])
            poly((236, 206, 110), [(25, 10), (27, 3), (29, 10)])
        if outfit == "alt":
            poly((30, 30, 38), [(16, 53), (32, 53), (36, 64), (12, 64)])
        if naked:
            line(18, 24, 30, 24, (48, 42, 48), 3)

    # аксессуары модификаций
    if look.collar:
        box(16, 22.5, 16, 5, (46, 40, 48), radius=2)
        for i in range(3):
            dot(19.5 + i * 4.5, 25, 1.4, (214, 182, 96))
        line(24, 28, 24, 38, (196, 168, 92), 1)
        dot(24, 39, 2.0, (214, 182, 96))
    if look.fast:
        for i, yy in enumerate((63, 73, 83)):
            line(4 + i, yy, 12 + i * 1.5, yy, (226, 226, 234), 1)
    if look.armor:
        box(16, 28, 16, 19, (180, 148, 90), radius=3)
        dot(24, 37, 3, (226, 200, 132))
    if look.bandage:
        line(15, 36, 21, 39, (238, 238, 228), 2)
        line(16, 41, 22, 44, (238, 238, 228), 2)
        line(22, 60, 27, 63, (238, 238, 228), 2)
    if look.scroll:
        box(8, 45, 11, 5, (228, 212, 170), radius=2)
        dot(9.5, 47.5, 1.0, (150, 120, 80))
        dot(17.5, 47.5, 1.0, (150, 120, 80))
    if look.cup:
        box(36, 44, 6, 6, (150, 150, 156), radius=1)
        pygame.draw.circle(surface, (150, 150, 156), pt(42, 47),
                           max(1, int(2 * scale)), max(1, int(1 * scale)))
    if look.crutch:
        line(38, 40, 40, 92, (142, 102, 62), 2)
        line(35, 40, 41, 40, (120, 86, 52), 3)
    if look.snail:
        dot(41, 89, 3, (144, 110, 74))
        dot(41.5, 89, 1.4, (96, 70, 46))
        line(41, 92, 46, 92, (170, 170, 170), 1)
    if look.cat_ears:
        ear = (243, 243, 236) if outfit == "ghost" else cloth
        poly(ear, [(17, 11), (21, 10), (19, 3)])
        poly(ear, [(27, 10), (31, 11), (29, 3)])
    if look.glasses:
        pygame.draw.circle(surface, (30, 30, 36), pt(20.5, 19),
                           max(1, int(2.8 * scale)), max(1, int(1 * scale)))
        pygame.draw.circle(surface, (30, 30, 36), pt(27.5, 19),
                           max(1, int(2.8 * scale)), max(1, int(1 * scale)))
        line(23.3, 19, 24.7, 19, (30, 30, 36), 1)
    if look.headphones:
        pygame.draw.arc(surface, (36, 34, 40),
                        pygame.Rect(int(15 * scale), int(7 * scale),
                                    int(18 * scale), int(16 * scale)),
                        3.3, 6.1, max(1, int(2.5 * scale)))
        dot(14.5, 18, 2.6, (36, 34, 40))
        dot(33.5, 18, 2.6, (36, 34, 40))
    if look.hat == "dunce":
        poly((206, 84, 62), [(18, 12), (30, 12), (24, 0)])
        dot(24, 1, 1.8, (244, 240, 230))
    if look.hat == "straw":
        pygame.draw.ellipse(surface, (208, 178, 108),
                            pygame.Rect(int(9 * scale), int(11 * scale),
                                        int(30 * scale), int(7 * scale)))
        poly((226, 196, 126), [(13, 14), (35, 14), (24, 2)])
        line(13, 14, 35, 14, (160, 130, 80), 1)
    if look.hood:
        dot(24, 18, 10.5, (42, 38, 48))
        dot(24, 20, 5.6, skin)
    if look.cloud:
        dot(16, 7, 5, (86, 86, 96))
        dot(24, 4, 6, (96, 96, 108))
        dot(32, 7, 5, (86, 86, 96))
        poly((250, 214, 110),
             [(24, 10), (21, 16), (23.5, 16), (21, 21), (27, 14), (24, 14)])
    if look.fuse:
        line(24, 9, 27, 3, (120, 92, 60), 2)
        dot(27.5, 2, 2.4, (255, 204, 86))
        dot(27.5, 2, 1.2, (255, 244, 190))
    if look.dots:
        dot(32, 8, 1.6, (210, 206, 198))
        dot(36, 5, 1.3, (200, 196, 188))
        dot(39, 2.5, 1.0, (190, 186, 178))

    return surface


class Sprites:
    def __init__(self):
        self.spartan = make_person(1.16, skin=(214, 176, 146), cloth=(150, 40, 38),
                                   cloak=True, helmet=True, spear=True)
        self.inspector = make_person(1.26, skin=(206, 168, 138), cloth=(176, 46, 42),
                                     cloak=True, helmet=True, spear=True, shield=True)
        self.glow_gold = make_glow(56, (236, 198, 96), 62)
        self.glow_red = make_glow(56, (190, 60, 60), 58)
        self._cache = {}

    def child(self, look: Look, scale: float = 1.0):
        key = (look, scale)
        if key not in self._cache:
            self._cache[key] = make_child_sprite(look, scale)
        return self._cache[key]


def draw_sick_mark(screen, x, y, scale=1.0):
    """Зелёный крестик над больным ребёнком или бойцом."""
    size = max(3, int(7 * scale))
    thick = max(1, int(2 * scale))
    color = (150, 206, 128)
    pygame.draw.line(screen, color, (x - size, y), (x + size, y), thick)
    pygame.draw.line(screen, color, (x, y - size), (x, y + size), thick)


def draw_figure(screen, sprite, x, y, bob=0.0, angle=0.0):
    if abs(angle) < 0.5:
        shadow_width = int(sprite.get_width() * 0.8)
        shadow = pygame.Surface((shadow_width, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
        screen.blit(shadow, (int(x - shadow_width / 2), int(y - 5)))

    if abs(angle) > 0.5:
        image = pygame.transform.rotozoom(sprite, angle, 1.0)
        rect = image.get_rect(center=(int(x), int(y - sprite.get_height() / 2)))
        screen.blit(image, rect)
    else:
        screen.blit(sprite, (int(x - sprite.get_width() / 2), int(y - sprite.get_height() + bob)))


# ─────────────────────────── ФОН ───────────────────────────
def lerp_color(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def build_background():
    rng = random.Random(7)
    surface = pygame.Surface((WIDTH, HEIGHT)).convert()

    for y in range(HEIGHT):
        t = min(1.0, y / (HEIGHT - 1) * 1.3)
        surface.fill(lerp_color(SKY_TOP, SKY_BOTTOM, t), (0, y, WIDTH, 1))

    pygame.draw.circle(surface, (240, 188, 120), (632, 106), 44)
    pygame.draw.circle(surface, (252, 216, 158), (632, 106), 33)

    pygame.draw.polygon(surface, (52, 52, 74), [(0, 400), (170, 250), (330, 400)])
    pygame.draw.polygon(surface, (46, 46, 66), [(220, 410), (430, 220), (640, 410)])
    pygame.draw.polygon(surface, (42, 42, 60), [(520, 420), (760, 268), (980, 420)])
    pygame.draw.polygon(surface, (58, 52, 62), [(820, 420), (1040, 300), (1180, 420)])
    pygame.draw.polygon(surface, (222, 222, 232), [(430, 220), (470, 262), (430, 272), (392, 262)])
    pygame.draw.polygon(surface, (212, 212, 226), [(760, 268), (800, 306), (760, 316), (722, 306)])

    # земля
    pygame.draw.rect(surface, (188, 158, 112), (0, GROUND_Y, GORGE_X, HEIGHT - GROUND_Y))
    pygame.draw.rect(surface, (128, 142, 86), (0, GROUND_Y, GORGE_X, 12))
    for _ in range(180):
        x = rng.randrange(0, GORGE_X)
        y = rng.randrange(GROUND_Y + 16, HEIGHT - 4)
        pygame.draw.circle(surface, (170, 142, 100), (x, y), rng.choice((1, 1, 2)))

    # каменистый холм, на котором встают спасённые спартанцы
    pygame.draw.polygon(surface, (138, 110, 80),
                        [(300, GROUND_Y), (350, PLATEAU_Y), (606, PLATEAU_Y), (656, GROUND_Y)])
    pygame.draw.line(surface, (172, 140, 98), (350, PLATEAU_Y), (606, PLATEAU_Y), 3)
    for _ in range(10):
        bx = rng.randrange(356, 600)
        by = rng.randrange(PLATEAU_Y - 2, PLATEAU_Y + 12)
        pygame.draw.circle(surface, (108, 86, 66), (bx, by), rng.choice((2, 3)))
    for gx in range(362, 600, 28):
        pygame.draw.line(surface, (120, 140, 84), (gx, PLATEAU_Y + 7), (gx + 3, PLATEAU_Y - 5), 2)

    # палатки
    for tx, color in ((26, (96, 84, 70)), (84, (112, 94, 76))):
        pygame.draw.polygon(surface, color, [(tx, GROUND_Y), (tx + 34, GROUND_Y - 44), (tx + 68, GROUND_Y)])
        pygame.draw.polygon(surface, (70, 60, 52),
                            [(tx + 34, GROUND_Y - 44), (tx + 68, GROUND_Y), (tx + 40, GROUND_Y)])

    # обрыв
    pygame.draw.rect(surface, (18, 14, 20), (GORGE_X, GROUND_Y, WIDTH - GORGE_X, HEIGHT - GROUND_Y))
    pygame.draw.polygon(surface, (122, 98, 74),
                        [(GORGE_X, GROUND_Y), (GORGE_X, HEIGHT), (GORGE_X + 18, HEIGHT), (GORGE_X + 7, GROUND_Y)])
    pygame.draw.line(surface, (206, 176, 128), (GORGE_X - 2, GROUND_Y + 2), (GORGE_X + 5, GROUND_Y), 2)

    x = GORGE_X + 8
    while x < WIDTH:
        width = rng.randrange(18, 34)
        height = rng.randrange(34, 76)
        pygame.draw.polygon(surface, (46, 32, 40),
                            [(x, HEIGHT), (x + width // 2, HEIGHT - height), (x + width, HEIGHT)])
        pygame.draw.polygon(surface, (88, 68, 62),
                            [(x + width // 2, HEIGHT - height), (x + width // 2 + 4, HEIGHT - height + 12),
                             (x + width // 2 - 3, HEIGHT - height + 10)])
        x += width + 4

    return surface


# ─────────────────────────── ИНТЕРФЕЙС ───────────────────────────
class Fonts:
    def __init__(self):
        names = "segoeui,arial,dejavusans,freesans,liberationsans,sans"
        self.small = pygame.font.SysFont(names, 14)
        self.tiny = pygame.font.SysFont(names, 12)
        self.normal = pygame.font.SysFont(names, 17)
        self.bold = pygame.font.SysFont(names, 18, bold=True)
        self.title = pygame.font.SysFont(names, 24, bold=True)


def draw_panel(screen, rect, alpha=150, border=PANEL_BORDER):
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill((10, 10, 14, alpha))
    screen.blit(layer, rect.topleft)
    pygame.draw.rect(screen, border, rect, 1, border_radius=6)


def draw_bar(screen, x, y, width, height, value, color):
    pygame.draw.rect(screen, (38, 38, 46), (x, y, width, height), border_radius=3)
    filled = max(1, int(width * value))
    pygame.draw.rect(screen, color, (x, y, filled, height), border_radius=3)


# ─────────────────────────── ГЛАВНЫЙ ЦИКЛ ───────────────────────────
def run(max_frames: int | None = None):
    pygame.init()
    pygame.display.set_caption("Спарта: селекция")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    background = build_background()
    sprites = Sprites()
    fonts = Fonts()
    sim = Simulation()

    running = True
    frame = 0
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    if len(sim.children) < 40:
                        sim.children.append(sim.make_child())
                elif event.key == pygame.K_p:
                    sim.paused = not sim.paused
                elif event.key == pygame.K_r:
                    sim.reset()
                elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    sim.speed = {pygame.K_1: 1.0, pygame.K_2: 2.0, pygame.K_3: 3.0,
                                 pygame.K_4: 5.0, pygame.K_5: 100.0}[event.key]

        if not sim.paused:
            sim.update(dt * sim.speed)

        screen.blit(background, (0, 0))
        sim.draw(screen, sprites, fonts)
        pygame.display.flip()

        frame += 1
        if max_frames is not None and frame >= max_frames:
            running = False

    pygame.quit()


if __name__ == "__main__":
    run()
