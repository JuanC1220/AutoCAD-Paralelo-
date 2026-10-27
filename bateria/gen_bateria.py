"""Batería de dibujos variados para probar POVERKILL y PHATCH contra OVERKILL y HATCH de AutoCAD.

Tamaños (pequeño, mediano, grande y una serie para el punto de corte), dos densidades y todo tipo de
entidad: LINE, LWPOLYLINE recta y con arcos, ARC, CIRCLE, SPLINE, ELLIPSE, POINT y TEXT.
Cada familia de casos vive en su propia capa, así el verificador dice qué caso falla.

  overkill: o_<densidad>_<n>.dxf
    densa     entidades apretadas (se cruzan mucho) y ~60 % con copias, solapes o continuaciones
    pocodensa entidades dispersas en un área enorme y ~5 % con copias
  hatch: h_<densidad>_k<k>.dxf  (k x k áreas, un POINT interior por área, y <dxf>.puntos.txt para -HATCH)
    densa     rejilla deformada de celdas que comparten lados
    pocodensa celdas sueltas, giradas y separadas

Por cada DXF escribe <dxf>.json con lo que tiene cada capa (y en hatch, cada punto con su área esperada).
Lo que debe quedar tras OVERKILL lo calcula verificar_bateria.py con el motor v2 (overkill/v2), así que
aquí sólo se cuentan entradas. La misma semilla da los mismos archivos.

Uso:  python gen_bateria.py --out dibujos              (todo: ~40 archivos, ~150 MB)
      python gen_bateria.py --out dibujos --solo hatch --rapido
"""
import argparse
import json
import math
import os
import random
from collections import defaultdict

import ezdxf

# ------------------------------------------------------------------------------------------- OVERKILL
# familia -> (peso, clase, descripción). clase v2: el motor v2 sabe qué debe quedar (POVERKILL debe cuadrar exacto);
# fuera: POVERKILL no toca ese tipo (debe quedar igual) y se mira qué hace OVERKILL de AutoCAD.
FAMILIAS_OK = {
    "L_COPIAS": (0.25, "v2", "líneas con copias exactas, invertidas, contenidas, solapes, continuaciones, otro color, paralelas a 1e-3"),
    "L_AZAR": (0.10, "v2", "líneas sueltas que se cruzan, sin nada que borrar"),
    "P_RECTAS": (0.12, "v2", "polilíneas rectas abiertas y cerradas: copias exactas, invertidas, con otro inicio, otro color, un vértice movido"),
    "P_CURVAS": (0.08, "v2", "polilíneas con tramos de arco (bulge): mismas variantes"),
    "A_ARCOS": (0.12, "v2", "arcos sobre la misma circunferencia: copias, solapes, contenidos, continuaciones; vuelta completa"),
    "C_CIRCULOS": (0.08, "v2", "círculos: copias, concéntricos de otro radio, desplazados 1e-3, arcos sobre el círculo"),
    "S_SPLINES": (0.07, "fuera", "splines por puntos de control: copias exactas y de otro color"),
    "E_ELIPSES": (0.05, "fuera", "elipses y arcos de elipse: copias exactas y de otro color"),
    "X_LINEA_EN_POLI": (0.07, "fuera", "LINE encima de un tramo de polilínea (igual o parcial): tipos distintos"),
    "O_PUNTOS_TEXTOS": (0.06, "fuera", "POINT y TEXT repetidos"),
}

DENSIDAD = {  # separación media entre entidades (unidades) y probabilidad de que una base traiga casos repetidos
    "densa": (2.0, 0.6),
    "pocodensa": (150.0, 0.05),
}


class Gen:
    def __init__(self, seed):
        self.rnd = random.Random(seed)

    def u(self, a, b):
        return self.rnd.uniform(a, b)


def r6(v):
    return round(v, 6)


def gen_overkill(path, n_total, densidad, seed):
    sep, rep = DENSIDAD[densidad]
    side = max(50.0, math.sqrt(n_total) * sep)
    g = Gen(seed)
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    info = {}
    for i, (fam, (w, clase, desc)) in enumerate(FAMILIAS_OK.items()):
        doc.layers.add(fam, color=(i % 7) + 1)
        info[fam] = {"clase": clase, "descripcion": desc, "entrada": 0, "por_tipo": defaultdict(int)}
    ents = []   # (familia, función que crea la entidad); se crean en orden aleatorio

    def add(fam, tipo, fn):
        ents.append(fn)
        info[fam]["entrada"] += 1
        info[fam]["por_tipo"][tipo] += 1

    def centro():
        return g.u(0, side), g.u(0, side)

    def dir_():
        if g.rnd.random() < 0.3:
            a = g.rnd.choice([0, 90, 180, 270]) * math.pi / 180
        else:
            a = g.u(0, 2 * math.pi)
        return math.cos(a), math.sin(a)

    # ---- líneas con casos
    def L(fam, p0, p1, **at):
        a = dict(layer=fam, **at)
        add(fam, "LINE", lambda: msp.add_line(p0, p1, dxfattribs=a))

    def fam_l_copias(quota):
        c = 0
        while c < quota:
            cx, cy = centro(); dx, dy = dir_(); ln = g.u(2, 20)
            p0 = (cx, cy); p1 = (cx + dx * ln, cy + dy * ln)
            P = lambda t: (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
            L("L_COPIAS", p0, p1); c += 1
            if g.rnd.random() >= rep:
                continue
            for _ in range(g.rnd.randint(1, 3)):
                k = g.rnd.choice(["exacta", "invertida", "contenida", "solape", "continuacion", "otro_color", "paralela"])
                if k == "exacta": L("L_COPIAS", p0, p1)
                elif k == "invertida": L("L_COPIAS", p1, p0)
                elif k == "contenida":
                    a = g.u(0.1, 0.5); L("L_COPIAS", P(a), P(a + g.u(0.1, 0.4)))
                elif k == "solape": L("L_COPIAS", P(g.u(0.3, 0.8)), P(g.u(1.1, 1.6)))
                elif k == "continuacion": L("L_COPIAS", p1, P(g.u(1.2, 2.0)))
                elif k == "otro_color": L("L_COPIAS", p0, p1, color=1)
                else:
                    nx, ny = -(p1[1] - p0[1]) / ln * 1e-3, (p1[0] - p0[0]) / ln * 1e-3
                    L("L_COPIAS", (p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny))
                c += 1

    def fam_l_azar(quota):
        for _ in range(quota):
            cx, cy = centro(); dx, dy = dir_(); ln = g.u(2, 30)
            L("L_AZAR", (cx, cy), (cx + dx * ln, cy + dy * ln))

    # ---- polilíneas
    def poli(curvas):
        cx, cy = centro()
        n = g.rnd.randint(3, 8)
        pts, a = [], g.u(0, 2 * math.pi)
        x, y = cx, cy
        for _ in range(n):
            pts.append((x, y))
            a += g.u(-1.2, 1.2); s = g.u(1, 6)
            x += math.cos(a) * s; y += math.sin(a) * s
        b = [(g.u(-1, 1) if curvas and g.rnd.random() < 0.5 else 0.0) for _ in range(n)]
        return pts, b, g.rnd.random() < 0.5

    def invertir(pts, b, cerr):
        n = len(pts)
        rp = list(reversed(pts))
        rb = [-b[(n - 2 - i) % n] for i in range(n)]
        if not cerr:
            rb[-1] = 0.0
        return rp, rb

    def PL(fam, pts, b, cerr, **at):
        a = dict(layer=fam, **at)
        if not cerr:
            b = b[:-1] + [0.0]
        v = [(x, y, bb) for (x, y), bb in zip(pts, b)]
        add(fam, "LWPOLYLINE", lambda: msp.add_lwpolyline(v, format="xyb", close=cerr, dxfattribs=a))

    def fam_poli(fam, curvas, quota):
        c = 0
        while c < quota:
            pts, b, cerr = poli(curvas)
            PL(fam, pts, b, cerr); c += 1
            if g.rnd.random() >= rep:
                continue
            for _ in range(g.rnd.randint(1, 3)):
                k = g.rnd.choice(["exacta", "invertida", "otro_inicio", "otro_color", "vertice_movido"])
                if k == "exacta": PL(fam, pts, b, cerr)
                elif k == "invertida": PL(fam, *invertir(pts, b, cerr), cerr)
                elif k == "otro_inicio" and cerr:
                    s = g.rnd.randint(1, len(pts) - 1); PL(fam, pts[s:] + pts[:s], b[s:] + b[:s], cerr)
                elif k == "otro_color": PL(fam, pts, b, cerr, color=3)
                else:
                    q = list(pts); j = g.rnd.randrange(len(q)); q[j] = (q[j][0] + 1e-3, q[j][1]); PL(fam, q, b, cerr)
                c += 1

    # ---- arcos y círculos
    def ARC(fam, c, r, a0, a1, **at):
        a = dict(layer=fam, **at)
        add(fam, "ARC", lambda: msp.add_arc(c, r, a0 % 360, a1 % 360, dxfattribs=a))

    def CIR(fam, c, r, **at):
        a = dict(layer=fam, **at)
        add(fam, "CIRCLE", lambda: msp.add_circle(c, r, dxfattribs=a))

    def fam_arcos(quota):
        c = 0
        while c < quota:
            cen = centro(); r = g.u(1, 10); a0 = g.u(0, 360); sw = g.u(20, 200)
            ARC("A_ARCOS", cen, r, a0, a0 + sw); c += 1
            if g.rnd.random() >= rep:
                continue
            for _ in range(g.rnd.randint(1, 3)):
                k = g.rnd.choice(["exacta", "solape", "contenido", "continuacion", "vuelta", "otro_radio", "otro_color"])
                if k == "exacta": ARC("A_ARCOS", cen, r, a0, a0 + sw)
                elif k == "solape": ARC("A_ARCOS", cen, r, a0 + sw * 0.5, a0 + sw * 1.5)
                elif k == "contenido": ARC("A_ARCOS", cen, r, a0 + sw * 0.2, a0 + sw * 0.6)
                elif k == "continuacion": ARC("A_ARCOS", cen, r, a0 + sw, a0 + sw + g.u(10, 90))
                elif k == "vuelta": ARC("A_ARCOS", cen, r, a0 + sw * 0.9, a0 + 360 + sw * 0.1)
                elif k == "otro_radio": ARC("A_ARCOS", cen, r + 0.01, a0, a0 + sw)
                else: ARC("A_ARCOS", cen, r, a0, a0 + sw, color=5)
                c += 1

    def fam_circulos(quota):
        c = 0
        while c < quota:
            cen = centro(); r = g.u(0.5, 8)
            CIR("C_CIRCULOS", cen, r); c += 1
            if g.rnd.random() >= rep:
                continue
            for _ in range(g.rnd.randint(1, 3)):
                k = g.rnd.choice(["exacta", "concentrico", "desplazado", "arco_encima", "otro_color"])
                if k == "exacta": CIR("C_CIRCULOS", cen, r)
                elif k == "concentrico": CIR("C_CIRCULOS", cen, r * 0.7)
                elif k == "desplazado": CIR("C_CIRCULOS", (cen[0] + 1e-3, cen[1]), r)
                elif k == "arco_encima":
                    a0 = g.u(0, 360); ARC("C_CIRCULOS", cen, r, a0, a0 + g.u(30, 300))
                else: CIR("C_CIRCULOS", cen, r, color=6)
                c += 1

    # ---- splines, elipses, mezcla de tipos, puntos y textos (POVERKILL no los toca)
    def SPL(fam, cps, **at):
        a = dict(layer=fam, **at)
        add(fam, "SPLINE", lambda: msp.add_open_spline(cps, degree=3, dxfattribs=a))

    def fam_splines(quota):
        c = 0
        while c < quota:
            cx, cy = centro()
            cps = [(cx + i * g.u(1, 3), cy + g.u(-3, 3)) for i in range(g.rnd.randint(4, 8))]
            SPL("S_SPLINES", cps); c += 1
            if g.rnd.random() < rep:
                SPL("S_SPLINES", cps, **({"color": 2} if g.rnd.random() < 0.3 else {})); c += 1

    def ELL(fam, cen, maj, ratio, s, e, **at):
        a = dict(layer=fam, **at)
        add(fam, "ELLIPSE", lambda: msp.add_ellipse(cen, maj, ratio, s, e, dxfattribs=a))

    def fam_elipses(quota):
        c = 0
        while c < quota:
            cen = centro(); a = g.u(0, math.pi); m = g.u(1, 8)
            maj = (math.cos(a) * m, math.sin(a) * m); ratio = g.u(0.2, 0.9)
            s, e = (0, 2 * math.pi) if g.rnd.random() < 0.5 else (g.u(0, 3), g.u(3.5, 6))
            ELL("E_ELIPSES", cen, maj, ratio, s, e); c += 1
            if g.rnd.random() < rep:
                ELL("E_ELIPSES", cen, maj, ratio, s, e, **({"color": 4} if g.rnd.random() < 0.3 else {})); c += 1

    def fam_linea_en_poli(quota):
        c = 0
        while c < quota:
            pts, b, cerr = poli(False)
            PL("X_LINEA_EN_POLI", pts, b, cerr); c += 1
            j = g.rnd.randrange(len(pts) - 1)
            p0, p1 = pts[j], pts[j + 1]
            if g.rnd.random() < 0.5:
                L("X_LINEA_EN_POLI", p0, p1)
            else:
                t0, t1 = g.u(0.1, 0.4), g.u(0.6, 0.9)
                L("X_LINEA_EN_POLI", (p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0),
                  (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1))
            c += 1

    def fam_otros(quota):
        c = 0
        while c < quota:
            p = centro()
            if g.rnd.random() < 0.5:
                fn = lambda p=p: msp.add_point(p, dxfattribs={"layer": "O_PUNTOS_TEXTOS"}); tipo = "POINT"
            else:
                t = f"T{g.rnd.randint(1, 999)}"
                fn = lambda p=p, t=t: msp.add_text(t, height=1.0, dxfattribs={"layer": "O_PUNTOS_TEXTOS", "insert": p}); tipo = "TEXT"
            add("O_PUNTOS_TEXTOS", tipo, fn); c += 1
            if g.rnd.random() < rep:
                add("O_PUNTOS_TEXTOS", tipo, fn); c += 1

    hacer = {
        "L_COPIAS": fam_l_copias, "L_AZAR": fam_l_azar,
        "P_RECTAS": lambda q: fam_poli("P_RECTAS", False, q), "P_CURVAS": lambda q: fam_poli("P_CURVAS", True, q),
        "A_ARCOS": fam_arcos, "C_CIRCULOS": fam_circulos, "S_SPLINES": fam_splines, "E_ELIPSES": fam_elipses,
        "X_LINEA_EN_POLI": fam_linea_en_poli, "O_PUNTOS_TEXTOS": fam_otros,
    }
    for fam, (w, _, _) in FAMILIAS_OK.items():
        hacer[fam](max(2, round(n_total * w)))
    g.rnd.shuffle(ents)     # orden de archivo aleatorio: el superviviente no siempre es la base
    for fn in ents:
        fn()
    doc.saveas(path)
    for v in info.values():
        v["por_tipo"] = dict(v["por_tipo"])
    man = {"archivo": os.path.basename(path), "comando": "overkill", "densidad": densidad, "n": len(ents),
           "lado": side, "semilla": seed, "tolerancia": 1e-6, "extremo_con_extremo": True, "capas": info}
    with open(path + ".json", "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return len(ents)


# ------------------------------------------------------------------------------------------- HATCH
# familia -> (peso, phatch_soporta, descripción)
FAMILIAS_H = {
    "H_LINEAS": (0.20, True, "celda cerrada por LINE"),
    "H_POLIS": (0.12, True, "celda que es una LWPOLYLINE cerrada (sus lados también cierran a las vecinas)"),
    "H_DIAGONAL": (0.08, True, "celda partida por una diagonal; el punto está en un triángulo"),
    "H_ISLA": (0.10, True, "isla cuadrada de LINE dentro de la celda"),
    "H_ISLA_POLI": (0.08, True, "isla que es una LWPOLYLINE cerrada"),
    "H_RUIDO": (0.10, True, "segmentos sueltos dentro (salen de un lado o flotan): no cambian el área"),
    "H_ANIDADA": (0.07, False, "isla con otra isla dentro (Normal y Exterior dan áreas distintas)"),
    "H_CIRCULO": (0.07, False, "isla circular"),
    "H_ARCOS": (0.06, False, "isla de polilínea con tramos de arco (forma de estadio)"),
    "H_ELIPSE": (0.06, False, "isla elíptica"),
    "H_SPLINE": (0.06, False, "isla de spline cerrada"),
}


def bspline_area(cps, knots, p=3, n=4000):
    """Área de una B-spline no racional cerrada (de Boor sobre el dominio válido), con signo."""
    lo, hi = knots[p], knots[len(knots) - p - 1]
    pts = []
    for s in range(n):
        t = lo + (hi - lo) * s / n
        k = p
        while k < len(knots) - p - 2 and knots[k + 1] <= t:
            k += 1
        d = [list(cps[j + k - p]) for j in range(p + 1)]
        for r in range(1, p + 1):
            for j in range(p, r - 1, -1):
                i = j + k - p
                a = (t - knots[i]) / (knots[i + p - r + 1] - knots[i])
                d[j] = [(1 - a) * d[j - 1][0] + a * d[j][0], (1 - a) * d[j - 1][1] + a * d[j][1]]
        pts.append(d[p])
    return poly_area(pts)


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2


def gen_hatch(path, k, densidad, seed):
    rnd = random.Random(seed)
    s = 10.0
    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    for i, f in enumerate(list(FAMILIAS_H) + ["PUNTOS"]):
        doc.layers.add(f, color=(i % 7) + 1)
    fams = list(FAMILIAS_H)
    pesos = [FAMILIAS_H[f][0] for f in fams]
    fam_de = [[rnd.choices(fams, pesos)[0] for _ in range(k)] for _ in range(k)]
    # asegurar que con k pequeño salga cada familia al menos una vez
    celdas = [(i, j) for j in range(k) for i in range(k)]
    rnd.shuffle(celdas)
    for f, (i, j) in zip(fams, celdas):
        fam_de[j][i] = f
    puntos = []
    stats = defaultdict(int)

    def line(a, b, lay):
        msp.add_line(a, b, dxfattribs={"layer": lay}); stats["LINE"] += 1

    def lw(v, lay, fmt="xy"):
        msp.add_lwpolyline(v, format=fmt, close=True, dxfattribs={"layer": lay}); stats["LWPOLYLINE"] += 1

    if densidad == "densa":
        jit = 0.2 * s
        V = [[(i * s + (rnd.uniform(-jit, jit) if 0 < i < k else 0), j * s + (rnd.uniform(-jit, jit) if 0 < j < k else 0))
              for i in range(k + 1)] for j in range(k + 1)]
        def quad(i, j): return [V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]]
        def es_poli(i, j): return 0 <= i < k and 0 <= j < k and fam_de[j][i] == "H_POLIS"
        for j in range(k + 1):              # lados compartidos: una LINE salvo si una celda vecina es polilínea
            for i in range(k):
                if not (es_poli(i, j) or es_poli(i, j - 1)):
                    line(V[j][i], V[j][i + 1], "H_LINEAS")
        for i in range(k + 1):
            for j in range(k):
                if not (es_poli(i, j) or es_poli(i - 1, j)):
                    line(V[j][i], V[j + 1][i], "H_LINEAS")
        celdas_q = [(i, j, quad(i, j)) for j in range(k) for i in range(k)]
    else:
        celdas_q = []
        for j in range(k):
            for i in range(k):
                cx, cy, a = (i + 0.5) * 3 * s, (j + 0.5) * 3 * s, rnd.uniform(0, math.pi / 2)
                h = s / 2
                q = [(cx + math.cos(a) * x - math.sin(a) * y, cy + math.sin(a) * x + math.cos(a) * y)
                     for x, y in ((-h, -h), (h, -h), (h, h), (-h, h))]
                if fam_de[j][i] != "H_POLIS":
                    for m in range(4):
                        line(q[m], q[(m + 1) % 4], "H_LINEAS")
                celdas_q.append((i, j, q))

    for i, j, q in celdas_q:
        f = fam_de[j][i]
        cx = sum(p[0] for p in q) / 4; cy = sum(p[1] for p in q) / 4
        area_celda = abs(poly_area(q))
        pt = ((cx + q[0][0]) / 2, (cy + q[0][1]) / 2)    # a medio camino del centro a la primera esquina
        isla = 0.0; anid = 0.0
        if f == "H_POLIS":
            lw(q, f)
        elif f == "H_DIAGONAL":
            line(q[0], q[2], f)
            tri = [q[0], q[1], q[2]]
            pt = (sum(p[0] for p in tri) / 3, sum(p[1] for p in tri) / 3)
            area_celda = abs(poly_area(tri))
        elif f in ("H_ISLA", "H_ISLA_POLI", "H_ANIDADA"):
            r = s / 8
            sq = [(cx - r, cy - r), (cx + r, cy - r), (cx + r, cy + r), (cx - r, cy + r)]
            if f == "H_ISLA_POLI":
                lw(sq, f)
            else:
                for m in range(4):
                    line(sq[m], sq[(m + 1) % 4], f)
            isla = (2 * r) ** 2
            if f == "H_ANIDADA":
                r2 = s / 20
                lw([(cx - r2, cy - r2), (cx + r2, cy - r2), (cx + r2, cy + r2), (cx - r2, cy + r2)], f)
                anid = (2 * r2) ** 2
        elif f == "H_RUIDO":
            m0 = ((q[1][0] + q[2][0]) / 2, (q[1][1] + q[2][1]) / 2)       # del medio del lado derecho hacia el centro
            line(m0, ((m0[0] + cx) / 2 + 0.01, (m0[1] + cy) / 2), f)
            line((cx - s * 0.05, cy + s * 0.1), (cx + s * 0.1, cy + s * 0.15), f)   # flotante
        elif f == "H_CIRCULO":
            r = s / 7
            msp.add_circle((cx, cy), r, dxfattribs={"layer": f}); stats["CIRCLE"] += 1
            isla = math.pi * r * r
        elif f == "H_ARCOS":
            w, r = s / 8, s / 12      # estadio: rectángulo 2w x 2r con semicírculos en los lados cortos
            lw([(cx - w, cy - r, 0), (cx + w, cy - r, 1), (cx + w, cy + r, 0), (cx - w, cy + r, 1)], f, "xyb")
            isla = 2 * w * 2 * r + math.pi * r * r
        elif f == "H_ELIPSE":
            a, ratio = s / 6, 0.5
            msp.add_ellipse((cx, cy), (a, 0), ratio, dxfattribs={"layer": f}); stats["ELLIPSE"] += 1
            isla = math.pi * a * a * ratio
        elif f == "H_SPLINE":
            n, r = 8, s / 7
            base = [(cx + r * math.cos(2 * math.pi * m / n) * (1 + 0.25 * (m % 2)), cy + r * math.sin(2 * math.pi * m / n) * (1 + 0.25 * (m % 2)))
                    for m in range(n)]
            cps = base + base[:1]                     # spline sujeta (clamped) que vuelve al primer punto: cerrada
            sp = msp.add_open_spline(cps, degree=3, dxfattribs={"layer": f})
            knots = list(sp.knots)
            stats["SPLINE"] += 1
            isla = abs(bspline_area(cps, knots))
        msp.add_point(pt, dxfattribs={"layer": "PUNTOS"}); stats["POINT"] += 1
        puntos.append({"x": pt[0], "y": pt[1], "familia": f, "phatch_soporta": FAMILIAS_H[f][1],
                       "area_exterior": area_celda - isla, "area_normal": area_celda - isla + anid})
    doc.saveas(path)
    with open(os.path.splitext(path)[0] + ".puntos.txt", "w", newline="\r\n") as fh:
        fh.write("".join(f"{p['x']!r},{p['y']!r}\n" for p in puntos))
    man = {"archivo": os.path.basename(path), "comando": "hatch", "densidad": densidad, "k": k, "semilla": seed,
           "por_tipo": dict(stats),
           "familias": {f: {"phatch_soporta": v[1], "descripcion": v[2], "puntos": sum(1 for p in puntos if p["familia"] == f)}
                        for f, v in FAMILIAS_H.items()},
           "puntos": puntos}
    with open(path + ".json", "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False)
    return len(puntos)


# ------------------------------------------------------------------------------------------- batería
BATERIA_OK = [("densa", n) for n in (300, 1000, 3000, 10000, 50000, 150000, 400000)] + \
             [("pocodensa", n) for n in (1000, 50000, 400000)]
BATERIA_H = [("densa", k) for k in (2, 4, 8, 16, 25, 32, 50)] + [("pocodensa", k) for k in (8, 25, 50)]
RAPIDO_OK = [("densa", 300), ("densa", 3000), ("pocodensa", 1000)]
RAPIDO_H = [("densa", 4), ("densa", 8), ("pocodensa", 8)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dibujos")
    ap.add_argument("--solo", choices=["overkill", "hatch"])
    ap.add_argument("--rapido", action="store_true", help="sólo 3 dibujos pequeños de cada comando")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.solo != "hatch":
        for d, n in (RAPIDO_OK if a.rapido else BATERIA_OK):
            p = os.path.join(a.out, f"o_{d}_{n}.dxf")
            print(f"{p}: {gen_overkill(p, n, d, a.seed + n):,} entidades", flush=True)
    if a.solo != "overkill":
        for d, k in (RAPIDO_H if a.rapido else BATERIA_H):
            p = os.path.join(a.out, f"h_{d}_k{k}.dxf")
            print(f"{p}: {gen_hatch(p, k, d, a.seed + k):,} puntos", flush=True)


if __name__ == "__main__":
    main()
