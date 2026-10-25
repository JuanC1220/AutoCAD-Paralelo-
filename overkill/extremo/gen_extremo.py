"""Dibujo EXTREMO para poner a prueba OVERKILL / POVERKILL.

Millones de entidades repartidas en "familias" de casos difíciles. Cada familia vive en su
propia capa (o grupo de capas), así que tras correr OVERKILL basta contar entidades por capa
para saber exactamente qué caso falla. Los conteos esperados salen en <out>.json.

Clases de familia:
  seguro    comportamiento ya comprobado en AutoCAD 2027 (s5000/s400k): debe cuadrar exacto.
  nuevo     lo que dicen la geometría y la documentación, aún no medido en AutoCAD real.
  frontera  casos puestos a propósito en el límite (ángulo ~1e-10 rad, tolerancia ~1e-6,
            longitud cero...). No hay "respuesta correcta" única: sirven para comparar
            motores entre sí y con AutoCAD. El JSON da la lectura geométrica y, cuando se
            conoce, lo observado en AutoCAD.

Las líneas "seguras" usan coordenadas en una rejilla de 1e-3 y direcciones enteras, así la
colinealidad es exacta y el resultado se calcula con enteros (sin errores de redondeo).
Cada familia usa rectas portadoras propias y los grupos están separados >= 1 unidad, de modo
que no hay fusiones no planeadas. El orden de las entidades en el archivo es aleatorio.

El DXF (R2010) se escribe a mano por velocidad; ezdxf sólo crea cabecera y tablas.

Uso:  python gen_extremo.py --total 3000000 --out extremo_3M.dxf [--seed 7]
"""
import argparse
import json
import math
import random
import time
from collections import defaultdict

import ezdxf

GRID = 1e-3
TOL = 1e-6
UTM = (500_000_000, 4_500_000_000)       # (500 000 ; 4 500 000) en unidades de rejilla

# capa -> (color de capa, flags, tipo de línea).  flags: 1 congelada, 4 bloqueada
LAYERS = {}


def layer(name, color=7, flags=0, off=False):
    LAYERS.setdefault(name, (color, flags, off))
    return name


def fnum(v):
    r = repr(float(v))
    return r


class Out:
    """Acumula cuerpos de entidad (sin handle) y lleva los conteos por capa."""

    def __init__(self, rnd):
        self.rnd = rnd
        self.ents = []                                # (tipo, cuerpo)
        self.n_in = defaultdict(int)
        self.exp = defaultdict(lambda: [0, 0])          # capa -> [sin e2e, con e2e]
        self.by_type = defaultdict(lambda: defaultdict(int))

    def props(self, lay, color=None, lt=None, lw=None, transp=None, ltscale=None):
        s = f"100\nAcDbEntity\n8\n{lay}\n"
        if lt is not None:
            s += f"6\n{lt}\n"
        if color is not None:
            s += f"62\n{color}\n"
        if lw is not None:
            s += f"370\n{lw}\n"
        if ltscale is not None:
            s += f"48\n{ltscale}\n"
        if transp is not None:
            s += f"440\n{transp}\n"
        return s

    def line(self, lay, p0, p1, z0=0.0, z1=0.0, thick=None, **kw):
        s = self.props(lay, **kw) + "100\nAcDbLine\n"
        if thick is not None:
            s += f"39\n{thick}\n"
        s += (f"10\n{fnum(p0[0])}\n20\n{fnum(p0[1])}\n30\n{fnum(z0)}\n"
              f"11\n{fnum(p1[0])}\n21\n{fnum(p1[1])}\n31\n{fnum(z1)}\n")
        self._add("LINE", lay, s)

    def circle(self, lay, c, r, **kw):
        s = self.props(lay, **kw) + f"100\nAcDbCircle\n10\n{fnum(c[0])}\n20\n{fnum(c[1])}\n30\n0.0\n40\n{fnum(r)}\n"
        self._add("CIRCLE", lay, s)

    def arc(self, lay, c, r, a0, a1, **kw):
        s = (self.props(lay, **kw) + f"100\nAcDbCircle\n10\n{fnum(c[0])}\n20\n{fnum(c[1])}\n30\n0.0\n40\n{fnum(r)}\n"
             f"100\nAcDbArc\n50\n{fnum(a0)}\n51\n{fnum(a1)}\n")
        self._add("ARC", lay, s)

    def lwpoly(self, lay, pts, closed, **kw):
        s = self.props(lay, **kw) + f"100\nAcDbPolyline\n90\n{len(pts)}\n70\n{1 if closed else 0}\n43\n0.0\n"
        s += "".join(f"10\n{fnum(x)}\n20\n{fnum(y)}\n" for x, y in pts)
        self._add("LWPOLYLINE", lay, s)

    def _add(self, typ, lay, body):
        self.ents.append((typ, body))
        self.n_in[lay] += 1
        self.by_type[lay][typ] += 1

    def expect(self, lay, no_e2e, e2e=None):
        self.exp[lay][0] += no_e2e
        self.exp[lay][1] += no_e2e if e2e is None else e2e


# ------------------------------------------------------------------ rectas exactas
class Carriers:
    """Rectas portadoras únicas por capa: origen entero + dirección entera reducida."""

    def __init__(self, rnd):
        self.rnd = rnd
        self.used = set()

    def new(self, lay, mode, offset=(0, 0), span=10_000_000):
        rnd = self.rnd
        while True:
            if mode == "ejes" or (mode == "mixtas" and rnd.random() < 0.4):
                a, b = rnd.choice([(1, 0), (0, 1)])
            elif mode == "mixtas":
                a, b = rnd.randint(-50, 50), rnd.randint(1, 50)
            else:                                   # oblicuas: muchos ángulos distintos
                a, b = rnd.randint(-300, 300), rnd.randint(1, 300)
            g = math.gcd(a, b)
            a, b = a // g, b // g
            ox, oy = offset[0] + rnd.randrange(span), offset[1] + rnd.randrange(span)
            key = (lay, a, b, a * oy - b * ox)
            if key not in self.used:
                self.used.add(key)
                return ox, oy, a, b


def sweep_count(iv, e2e):
    iv = sorted(iv)
    n, end = 0, None
    for s0, s1 in iv:
        if end is None or s0 > end or (s0 == end and not e2e):
            n += 1
            end = s1
        else:
            end = max(end, s1)
    return n


def chain_family(o, car, lay, budget, kinds, mode="mixtas", offset=(0, 0), rev_p=0.5,
                 elev=0.0, props_random=True):
    """Rectas con grupos de piezas colineales. kinds: tipos de pieza que se plantan.
    Esperado = barrido entero exacto de los intervalos (con y sin extremo-a-extremo)."""
    rnd = o.rnd
    start = len(o.ents)
    while len(o.ents) - start < budget:
        ox, oy, a, b = car.new(lay, mode, offset)
        norm = math.hypot(a, b)
        kw = {}
        if props_random:
            kw = dict(color=rnd.choice([None, None, 1, 3, 5, 30]),
                      lt=rnd.choice([None, None, "DASHED", "CENTER"]),
                      lw=rnd.choice([None, None, 25, 50]))
        unit = lambda g: max(1, int(round(g / norm)))   # unidades de rejilla -> pasos s
        s = 0
        iv = []
        for _ in range(rnd.randint(1, 5)):              # grupos en esta recta
            s += unit(rnd.randint(1000, 20000)) + 1      # hueco >= 1 unidad
            s0 = s
            s1 = s0 + max(4, unit(rnd.randint(1000, 20000)))
            pieces = [(s0, s1)]
            end = s1
            for _ in range(rnd.randint(1, 6)):
                k = rnd.choice(kinds)
                if k == "dup":
                    pieces.append((s0, s1))
                elif k == "cont":
                    if s1 - s0 >= 4:
                        c0 = rnd.randint(s0 + 1, s1 - 2)
                        pieces.append((c0, rnd.randint(c0 + 1, s1 - 1)))
                elif k == "over":                  # empieza dentro, termina más allá
                    c0 = rnd.randint(max(s0, end - unit(5000)) + 1, end - 1) if end - s0 > 1 else s0
                    c1 = end + max(2, unit(rnd.randint(500, 8000)))
                    pieces.append((c0, c1)); end = c1
                elif k == "e2e":                   # empieza justo donde acaba
                    c1 = end + max(2, unit(rnd.randint(500, 8000)))
                    pieces.append((end, c1)); end = c1
            s = end
            iv += pieces
        rnd.shuffle(iv)
        for s0, s1 in iv:
            p0 = ((ox + a * s0) / 1000, (oy + b * s0) / 1000)
            p1 = ((ox + a * s1) / 1000, (oy + b * s1) / 1000)
            if rnd.random() < rev_p:
                p0, p1 = p1, p0
            o.line(lay, p0, p1, elev, elev, **kw)
        o.expect(lay, sweep_count(iv, False), sweep_count(iv, True))


def grid_base(o, car, lay, mode="mixtas"):
    """Un segmento base sobre recta exacta; devuelve extremos en unidades de dibujo."""
    ox, oy, a, b = car.new(lay, mode)
    norm = math.hypot(a, b)
    s1 = max(4, int(round(o.rnd.randint(2000, 20000) / norm)))
    return ((ox) / 1000, (oy) / 1000), ((ox + a * s1) / 1000, (oy + b * s1) / 1000)


def perp(p0, p1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    return -dy / L, dx / L


# ------------------------------------------------------------------ familias
FAMILIAS = {}   # capa -> (clase, descripción, notas extra)


def fam(lay, clase, desc, **extra):
    FAMILIAS[lay] = dict(clase=clase, desc=desc, **extra)
    return lay


def generate(total, seed):
    rnd = random.Random(seed)
    o = Out(rnd)
    car = Carriers(rnd)
    W = lambda f: int(total * f)

    # --- seguras (lo ya comprobado en AutoCAD) --------------------------------
    chain_family(o, car, fam(layer("F01_DUPLICADOS"), "seguro", "copias exactas (2-7 por segmento), mitad invertidas"),
                 W(.08), ["dup"], rev_p=0.0)
    chain_family(o, car, fam(layer("F02_INVERTIDAS"), "seguro", "copias con inicio y fin intercambiados"),
                 W(.05), ["dup"], rev_p=0.5)
    chain_family(o, car, fam(layer("F03_CONTENIDAS"), "seguro", "sub-segmentos dentro del segmento base"),
                 W(.08), ["cont", "dup"])
    chain_family(o, car, fam(layer("F04_SOLAPES"), "seguro", "cadenas de hasta 7 segmentos colineales que se solapan parcialmente"),
                 W(.12), ["over"])
    chain_family(o, car, fam(layer("F05_EXTREMO"), "seguro", "cadenas de segmentos que se tocan extremo con extremo (sólo se unen con 'combinar extremo a extremo')"),
                 W(.10), ["e2e"])
    chain_family(o, car, fam(layer("F06_MEZCLA_EJES"), "seguro", "mezcla de todo (copia, invertida, contenida, solape, extremo) en rectas horizontales/verticales"),
                 W(.12), ["dup", "cont", "over", "e2e"], mode="ejes")
    chain_family(o, car, fam(layer("F07_MEZCLA_OBLICUA"), "seguro",
                             "mezcla de todo en rectas oblicuas (~110 000 ángulos distintos)",
                             nota="AutoCAD dejó ~1 % de solapes oblicuos sin fusionar en s5000/s400k sin causa geométrica"),
                 W(.12), ["dup", "cont", "over", "e2e"], mode="oblicuas")

    # --- nuevas (geometría clara, aún sin medir en AutoCAD) ---------------------
    chain_family(o, car, fam(layer("F08_COORD_UTM"), "nuevo", "mezcla de todo con coordenadas tipo UTM (x~500 000, y~4 500 000)"),
                 W(.07), ["dup", "cont", "over", "e2e"], offset=UTM)
    chain_family(o, car, fam(layer("F09_ELEVACION_100"), "nuevo", "mezcla de todo a Z=100 (todas iguales: deben fusionarse igual)"),
                 W(.03), ["dup", "cont", "over", "e2e"], elev=100.0)

    # propiedades: la misma línea con UNA propiedad distinta -> no se borra
    lay, layb = layer("F10_PROPIEDADES"), layer("F10_PROPIEDADES_OTRA_CAPA")
    fam(lay, "nuevo", "por grupo: base + copia exacta (se borra) + 6 copias que difieren sólo en color, tipo de línea, "
                      "grosor de línea, altura (thickness), transparencia o escala de tipo de línea (se quedan)")
    fam(layb, "nuevo", "copia exacta de F10 en otra capa (se queda salvo 'ignorar capa')")
    start = len(o.ents)
    while len(o.ents) - start < W(.05):
        p0, p1 = grid_base(o, car, lay)
        if rnd.random() < .5:
            p0, p1 = p1, p0
        o.line(lay, p0, p1); o.line(lay, p1, p0)
        o.line(lay, p0, p1, color=1)
        o.line(lay, p0, p1, lt="DASHED")
        o.line(lay, p0, p1, lw=50)
        o.line(lay, p0, p1, thick=2.0)
        o.line(lay, p0, p1, transp=33554559)
        o.line(lay, p0, p1, ltscale=2.0)
        o.line(layb, p0, p1)
        o.expect(lay, 7); o.expect(layb, 1)

    # paralelas cercanas: 10x, 100x y 1000x la tolerancia -> se quedan todas
    lay = fam(layer("F11_PARALELAS_CERCA"), "nuevo", "base + paralelas a 1e-3, 1e-4 y 1e-5 (10-1000 x tolerancia): no se borra ninguna")
    start = len(o.ents)
    while len(o.ents) - start < W(.04):
        p0, p1 = grid_base(o, car, lay)
        nx, ny = perp(p0, p1)
        o.line(lay, p0, p1)
        for d in (1e-3, 1e-4, 1e-5):
            o.line(lay, (p0[0] + nx * d, p0[1] + ny * d), (p1[0] + nx * d, p1[1] + ny * d))
        o.expect(lay, 4)

    # casi-duplicados por traslación (paralelos exactos, a < tol/3)
    lay = fam(layer("F12_CASI_DUPLICADOS"), "nuevo", "copias trasladadas en bloque < 0,3e-6 (siguen exactamente paralelas): se borran")
    start = len(o.ents)
    while len(o.ents) - start < W(.04):
        p0, p1 = grid_base(o, car, lay)
        o.line(lay, p0, p1)
        for _ in range(rnd.randint(1, 4)):
            ang = rnd.uniform(0, 2 * math.pi); r = rnd.uniform(0.05, 0.3) * TOL
            dx, dy = r * math.cos(ang), r * math.sin(ang)
            q0, q1 = (p0[0] + dx, p0[1] + dy), (p1[0] + dx, p1[1] + dy)
            o.line(lay, *((q1, q0) if rnd.random() < .5 else (q0, q1)))
        o.expect(lay, 1)

    # Z / 3D
    lay = fam(layer("F13_ELEVACION_3D"), "nuevo",
              "misma XY a distinta Z: base Z=0 + copias a Z=1, Z=0,001, inclinada 3D (0->5) (se quedan) + copia a Z=1e-9 (se borra)",
              nota="POVERKILL/overkill_core ignoran Z: aquí deberían fallar")
    start = len(o.ents)
    while len(o.ents) - start < W(.03):
        p0, p1 = grid_base(o, car, lay)
        o.line(lay, p0, p1)
        o.line(lay, p0, p1, 1.0, 1.0)
        o.line(lay, p0, p1, 1e-3, 1e-3)
        o.line(lay, p0, p1, 0.0, 5.0)
        o.line(lay, p1, p0, 1e-9, 1e-9)
        o.expect(lay, 4)

    # capas bloqueada / congelada / apagada
    for name, flags, off, clase, desc, keep in (
            ("F14_BLOQUEADA", 4, False, "nuevo", "duplicados y solapes en capa BLOQUEADA: OVERKILL no debe tocarlos", True),
            ("F15_CONGELADA", 1, False, "nuevo", "duplicados y solapes en capa CONGELADA: 'Todo' no los selecciona", True),
            ("F16_APAGADA", 0, True, "frontera", "duplicados y solapes en capa APAGADA: 'Todo' sí suele seleccionarlos", False)):
        lay = fam(layer(name, flags=flags, off=off), clase, desc)
        before_n = o.n_in[lay]
        chain_family(o, car, lay, W(.01), ["dup", "over", "e2e"], mode="ejes")
        if keep:
            o.exp[lay] = [o.n_in[lay], o.n_in[lay]]
        else:
            FAMILIAS[lay]["si_no_se_procesa"] = o.n_in[lay] - before_n

    # arcos y círculos
    lay = fam(layer("F17_ARCOS_CIRCULOS"), "nuevo",
              "círculos duplicados, arcos duplicados, arcos que se solapan, arcos extremo con extremo y arcos dentro de un círculo",
              nota="POVERKILL/overkill_core sólo tratan LINE")
    start = len(o.ents)
    while len(o.ents) - start < W(.03):
        c = (rnd.randrange(10_000_000) / 1000, rnd.randrange(10_000_000) / 1000)
        r = rnd.randint(500, 50_000) / 1000
        k = rnd.randrange(5)
        if k == 0:                                     # círculos duplicados
            for _ in range(rnd.randint(2, 5)):
                o.circle(lay, c, r)
            o.expect(lay, 1)
        elif k == 1:                                   # arcos duplicados
            a0 = rnd.randint(0, 200); a1 = a0 + rnd.randint(10, 150)
            for _ in range(rnd.randint(2, 5)):
                o.arc(lay, c, r, a0, a1)
            o.expect(lay, 1)
        elif k == 2:                                   # arcos solapados en cadena
            a0 = rnd.randint(0, 60); a1 = a0 + rnd.randint(20, 60)
            o.arc(lay, c, r, a0, a1)
            for _ in range(rnd.randint(1, 3)):
                b0 = rnd.randint(a0 + 1, a1 - 1); b1 = a1 + rnd.randint(10, 40)
                o.arc(lay, c, r, b0, b1); a0, a1 = b0, b1
            o.expect(lay, 1)
        elif k == 3:                                   # arcos extremo con extremo
            a = rnd.randint(0, 60); n = rnd.randint(2, 4)
            for _ in range(n):
                b = a + rnd.randint(20, 60)
                o.arc(lay, c, r, a, b); a = b
            o.expect(lay, n, 1)
        else:                                          # arcos dentro de un círculo
            o.circle(lay, c, r)
            for _ in range(rnd.randint(1, 3)):
                a0 = rnd.randint(0, 300)
                o.arc(lay, c, r, a0, a0 + rnd.randint(5, 59))
            o.expect(lay, 1)

    # --- frontera ---------------------------------------------------------------
    # giro alrededor del punto medio: barrido del corte angular de AutoCAD (~1e-10 rad)
    for th in (1e-13, 1e-12, 1e-11, 3e-11, 1e-10, 3e-10, 1e-9, 1e-8, 1e-7, 1e-6):
        lay = layer(f"F18_GIRO_{th:.0e}".replace("-", "m").replace("+", ""))
        geo = 1 if 5 * th < TOL else 2              # L = 10: desplazamiento máx = 5*th
        acad = "1" if th <= 1e-11 else ("transición" if th < 1e-10 else "2")
        fam(lay, "frontera", f"base de 10 u + copia girada {th:g} rad en su punto medio (desplaza {5 * th:.1e})",
            esperado_geometrico_por_grupo=geo, acad_estimado_por_grupo=acad)
        start = len(o.ents)
        while len(o.ents) - start < W(.0015):
            c = (rnd.uniform(0, 1000), rnd.uniform(0, 1000)); phi = rnd.uniform(0, math.pi)
            for t in (phi, phi + th):
                dx, dy = 5 * math.cos(t), 5 * math.sin(t)
                o.line(lay, (c[0] - dx, c[1] - dy), (c[0] + dx, c[1] + dy))
            o.expect(lay, geo)

    # barrido de distancia paralela alrededor de la tolerancia
    for d in (0.5e-6, 0.9e-6, 1.1e-6, 2e-6):
        lay = layer(f"F19_DIST_{d:.1e}".replace("-", "m").replace("+", ""))
        geo = 1 if d < TOL else 2
        fam(lay, "frontera", f"base + paralela exacta a {d:g} (tolerancia 1e-6)", esperado_geometrico_por_grupo=geo)
        start = len(o.ents)
        while len(o.ents) - start < W(.002):
            p0, p1 = grid_base(o, car, lay, mode="ejes")
            nx, ny = perp(p0, p1)
            o.line(lay, p0, p1)
            o.line(lay, (p0[0] + nx * d, p0[1] + ny * d), (p1[0] + nx * d, p1[1] + ny * d))
            o.expect(lay, geo)

    lay = fam(layer("F20_JITTER_INDEPENDIENTE"), "frontera",
              "copia con cada extremo movido al azar +-0,3e-6 (cambia el ángulo ~1e-8 rad)",
              esperado_geometrico_por_grupo=1, acad_observado_por_grupo=2)
    start = len(o.ents)
    while len(o.ents) - start < W(.01):
        p0, p1 = grid_base(o, car, lay)
        j = lambda v: v + rnd.uniform(-0.3, 0.3) * TOL
        o.line(lay, p0, p1); o.line(lay, (j(p0[0]), j(p0[1])), (j(p1[0]), j(p1[1])))
        o.expect(lay, 1)

    lay = fam(layer("F21_LONGITUD_CERO"), "frontera", "líneas de longitud cero repetidas en el mismo punto (geométricamente 1 por punto; AutoCAD podría dejar 0 o todas)")
    start = len(o.ents)
    while len(o.ents) - start < W(.003):
        p = (rnd.randrange(10_000_000) / 1000, rnd.randrange(10_000_000) / 1000)
        for _ in range(rnd.randint(2, 4)):
            o.line(lay, p, p)
        o.expect(lay, 1)

    lay = fam(layer("F22_PORCAPA_VS_EXPLICITO", color=7), "frontera",
              "base PorCapa (capa blanca, Continuous) + copia con color 7 explícito + copia con tipo CONTINUOUS explícito "
              "(mismas propiedades efectivas, distinto valor guardado)", esperado_geometrico_por_grupo="1 (efectivo) o 3 (literal)")
    start = len(o.ents)
    while len(o.ents) - start < W(.006):
        p0, p1 = grid_base(o, car, lay)
        o.line(lay, p0, p1); o.line(lay, p0, p1, color=7); o.line(lay, p0, p1, lt="Continuous")
        o.expect(lay, 3)

    lay = fam(layer("F23_POLILINEAS"), "frontera", "polilíneas (rectángulos cerrados y zigzags) duplicadas 2-4 veces",
              nota="con 'optimizar polilíneas' AutoCAD puede reescribirlas")
    start = len(o.ents)
    while len(o.ents) - start < W(.01):
        x, y = rnd.randrange(10_000_000), rnd.randrange(10_000_000)
        if rnd.random() < .5:
            w, h = rnd.randint(500, 9000), rnd.randint(500, 9000)
            pts, closed = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True
        else:
            pts, closed = [(x, y)], False
            for i in range(rnd.randint(2, 6)):
                x += rnd.randint(500, 4000); y += rnd.randint(500, 4000) * (1 if i % 2 else -1)
                pts.append((x, y))
        pts = [(px / 1000, py / 1000) for px, py in pts]
        for _ in range(rnd.randint(2, 4)):
            o.lwpoly(lay, pts, closed)
        o.expect(lay, 1)

    rnd.shuffle(o.ents)
    return o


def write(path, o):
    doc = ezdxf.new("R2010", setup=True)
    for name, (color, flags, off) in LAYERS.items():
        ly = doc.layers.add(name, color=color)
        ly.dxf.flags = flags
        if off:
            ly.off()
    owner = doc.modelspace().block_record_handle
    tmp = path + ".plantilla.dxf"
    doc.saveas(tmp)
    with open(tmp, encoding="utf-8") as f:
        tpl = f.read()
    import os
    os.remove(tmp)
    i = tpl.index("ENTITIES\n")
    i = tpl.index("\n", i) + 1
    head, tail = tpl[:i], tpl[i:]
    h0 = 0x100000
    seed = h0 + len(o.ents) + 1
    k = head.index("$HANDSEED\n")
    k = head.index("\n", head.index("\n", k) + 1) + 1          # tras el código 5
    e = head.index("\n", k)
    head = head[:k] + f"{seed:X}" + head[e:]
    with open(path, "w", encoding="utf-8", newline="\n", buffering=1 << 22) as f:
        f.write(head)
        buf = []
        for n, (typ, body) in enumerate(o.ents):
            buf.append(f"0\n{typ}\n5\n{h0 + n:X}\n330\n{owner}\n{body}")
            if len(buf) >= 50_000:
                f.write("".join(buf)); buf = []
        f.write("".join(buf))
        f.write(tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=3_000_000, help="entidades aproximadas")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t = time.time()
    o = generate(a.total, a.seed)
    t1 = time.time()
    write(a.out, o)
    capas = {}
    for lay in LAYERS:
        if o.n_in[lay] == 0:
            continue
        info = dict(FAMILIAS.get(lay, {}))
        info.update(entrada=o.n_in[lay], por_tipo=dict(o.by_type[lay]),
                    esperado_sin_e2e=o.exp[lay][0], esperado_con_e2e=o.exp[lay][1])
        capas[lay] = info
    res = dict(archivo=a.out, semilla=a.seed, tolerancia=TOL, entidades=len(o.ents),
               por_tipo={t: sum(v[t] for v in o.by_type.values() if t in v) for t in ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")},
               esperado_total_sin_e2e=sum(c["esperado_sin_e2e"] for c in capas.values()),
               esperado_total_con_e2e=sum(c["esperado_con_e2e"] for c in capas.values()),
               capas=capas)
    with open(a.out + ".json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(f"{len(o.ents):,} entidades  generar {t1 - t:.1f} s  escribir {time.time() - t1:.1f} s")
    print(f"esperado (todas las capas): sin e2e {res['esperado_total_sin_e2e']:,}  con e2e {res['esperado_total_con_e2e']:,}")


if __name__ == "__main__":
    main()
