"""Compara los resultados de correr_bateria.ps1 con lo esperado y escribe un informe.

OVERKILL (o_*.dxf): lo esperado lo calcula el motor de referencia overkill/v2 sobre el DXF original (LINE, ARC,
CIRCLE, LWPOLYLINE); los demás tipos deben quedar como en el volcado 'original'. Se compara la geometría, no sólo
los conteos: cada entidad se reduce a una clave (tipo, capa, color, números redondeados a 1e-5) y se cuentan las
que faltan y las que sobran por capa.
  - POVERKILL debe cuadrar exacto con v2 y dar lo mismo con 1 y con N hilos.
  - OVERKILL de AutoCAD se compara con v2 para ver dónde difieren (en el dibujo extremo AutoCAD dejaba de más).
HATCH (h_*.dxf): cada sombreado se reconstruye desde sus lazos (líneas, arcos, elipses, splines, polilíneas con
bulge), se calcula su área (lazos anidados alternan signo) y se asigna al punto interior que contiene. Se compara
con el área esperada en estilo Normal y Exterior (PHATCH usa Exterior).
Tiempos: <corrida>.ms (comando completo, medido en AutoCAD) y los internos de POVERKILL/PHATCH. Con la serie de
tamaños se busca el punto de corte: el tamaño desde el que POVERKILL/PHATCH ya es más rápido que el nativo.

Uso:  python verificar_bateria.py dibujos [--resultados dibujos/resultados] [--md informe.md]
"""
import argparse
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "overkill", "v2"))

Q = 1e5          # redondeo de claves: 1e-5
TOL_FINA = 2e-5  # segunda pasada: empareja lo que quedó suelto si todos sus números difieren <= esto


# ------------------------------------------------------------------------------------------- volcados
def leer_volcado(path):
    """Una entidad por línea: TIPO|código=valor|...  ->  [(tipo, [(código, texto)])]"""
    ents = []
    with open(path, encoding="latin-1", errors="replace") as f:
        for ln in f:
            ln = ln.rstrip("\r\n")
            if not ln:
                continue
            partes = ln.split("|")
            pares = []
            for p in partes[1:]:
                c, _, v = p.partition("=")
                try:
                    pares.append((int(c), v))
                except ValueError:
                    if pares:                      # un '|' dentro de un texto
                        pares[-1] = (pares[-1][0], pares[-1][1] + "|" + p)
            ents.append((partes[0], pares))
    return ents


def nums(v):
    return [float(x) for x in v.split(",")]


def q(x):
    return int(round(x * Q))


def q_ang(grados):
    return q(grados % 360.0) % int(360 * Q)


def canon_poli(cerrada, vs):
    """vs: [(x, y, bulge)] -> clave igual para la misma polilínea invertida o con otro inicio (si es cerrada)."""
    pts = [(q(x), q(y), int(round(b * 1e6))) for x, y, b in vs]
    n = len(pts)
    if not cerrada and n:
        pts[-1] = (pts[-1][0], pts[-1][1], 0)
    rev = [(x, y, -pts[(k - 1) % n][2] if cerrada else (-pts[k - 1][2] if k > 0 else 0))
           for k, (x, y, _) in reversed(list(enumerate(pts)))]
    cands = []
    for s in (pts, rev):
        if cerrada:
            cands += [tuple(s[k:] + s[:k]) for k in range(n)]
        else:
            cands.append(tuple(s))
    return (int(cerrada),) + min(cands)


def clave_volcado(tipo, pares):
    """Clave canónica de una entidad del volcado de AutoCAD (ángulos de entget en radianes)."""
    d = defaultdict(list)
    for c, v in pares:
        d[c].append(v)
    capa = d[8][0] if d[8] else "0"
    color = d[62][0] if d[62] else "256"
    if tipo == "LINE":
        a, b = tuple(q(x) for x in nums(d[10][0])), tuple(q(x) for x in nums(d[11][0]))
        geo = tuple(sorted((a, b)))
    elif tipo == "CIRCLE":
        geo = tuple(q(x) for x in nums(d[10][0])) + (q(float(d[40][0])),)
    elif tipo == "ARC":
        geo = tuple(q(x) for x in nums(d[10][0])) + (q(float(d[40][0])), q_ang(math.degrees(float(d[50][0]))),
                                                     q_ang(math.degrees(float(d[51][0]))))
    elif tipo == "LWPOLYLINE":
        vs = []
        for c, v in pares:
            if c == 10:
                x, y = nums(v)[:2]; vs.append([x, y, 0.0])
            elif c == 42 and vs:
                vs[-1][2] = float(v)
        geo = canon_poli(int(d[70][0]) & 1 if d[70] else 0, vs)
    elif tipo == "SPLINE":
        geo = (int(d[71][0]) if d[71] else 3, tuple(q(float(k)) for k in d[40]),
               tuple(tuple(q(x) for x in nums(p)) for p in d[10]), tuple(q(float(w)) for w in d[41]))
    elif tipo == "ELLIPSE":
        geo = tuple(q(x) for x in nums(d[10][0]) + nums(d[11][0])) + tuple(q(float(d[k][0])) for k in (40, 41, 42))
    elif tipo == "POINT":
        geo = tuple(q(x) for x in nums(d[10][0]))
    elif tipo == "TEXT":
        geo = tuple(q(x) for x in nums(d[10][0])) + (d[1][0] if d[1] else "", q(float(d[40][0])))
    else:
        geo = tuple(sorted((c, v) for c, v in pares if c not in (8, 62)))
    return (tipo, capa, color, geo)


def clave_v2(D, i, nuevo):
    """Clave de la entidad i del motor v2 (DXF: ángulos en grados), con su geometría nueva si la tiene."""
    t = D.tipo[i]; g = D.geo[i]
    capa = D.prop[i][0]; color = D.prop[i][1] or "256"
    if t == "LINE":
        if nuevo is not None:
            a, b = nuevo
            g = tuple(a) + tuple(b)
        geo = tuple(sorted((tuple(q(x) for x in g[:3]), tuple(q(x) for x in g[3:]))))
    elif t in ("ARC", "CIRCLE"):
        if nuevo == "circulo" or t == "CIRCLE":
            t = "CIRCLE"; geo = tuple(q(x) for x in g[:4])
        else:
            a0, a1 = nuevo if nuevo is not None else (g[4], g[5])
            geo = tuple(q(x) for x in g[:4]) + (q_ang(a0), q_ang(a1))
    else:
        geo = canon_poli(g[0], g[2])
    return (t, capa, color, geo)


def comparar(esperado, obtenido):
    """Multiconjuntos de claves -> (faltan, sobran) como Counter, con una segunda pasada por tolerancia."""
    e, o = Counter(esperado), Counter(obtenido)
    falta, sobra = e - o, o - e
    if falta and sobra and len(falta) * len(sobra) <= 4_000_000:
        def planos(k):
            out = []
            def rec(x):
                if isinstance(x, tuple):
                    for y in x: rec(y)
                elif isinstance(x, int):
                    out.append(x)
            rec(k[3]); return out
        grupos = defaultdict(list)
        for k in list(sobra):
            grupos[k[:3]].append(k)
        for kf in list(falta):
            pf = planos(kf)
            for ks in grupos.get(kf[:3], ()):
                if sobra[ks] <= 0:
                    continue
                ps = planos(ks)
                if len(ps) == len(pf) and all(abs(a - b) <= TOL_FINA * Q for a, b in zip(pf, ps)):
                    m = min(falta[kf], sobra[ks])
                    falta[kf] -= m; sobra[ks] -= m
                    if falta[kf] <= 0:
                        break
        falta, sobra = +falta, +sobra
    return falta, sobra


def tiempo_ms(path):
    try:
        return int(open(path).read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def tiempos_internos(path):
    try:
        t = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    m = re.findall(r"Tiempos: (.*?total [\d.,]+ s)", t)
    return m[-1] if m else None


# ------------------------------------------------------------------------------------------- OVERKILL
def verificar_overkill(dxf, man, res):
    import overkill_v2 as v2
    D = v2.leer(dxf)
    nuevos, borr = v2.overkill(D, tol=man.get("tolerancia", 1e-6), e2e=man.get("extremo_con_extremo", True))
    orig_path = os.path.join(res, "original.txt")
    if not os.path.exists(orig_path):
        return None
    orig = [clave_volcado(t, p) for t, p in leer_volcado(orig_path)]
    soportados = ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")
    esp = [k for k in orig if k[0] not in soportados] + \
          [clave_v2(D, i, nuevos.get(i)) for i in range(D.n) if i not in borr]
    # control de lectura: lo que v2 lee del DXF debe ser lo que AutoCAD abrió
    f0, s0 = comparar([clave_v2(D, i, None) for i in range(D.n)], [k for k in orig if k[0] in soportados])
    corridas = {}
    for txt in sorted(glob.glob(os.path.join(res, "*.txt"))):
        nom = os.path.basename(txt)[:-4]
        if nom == "original" or nom.endswith(".acadparalelo"):
            continue
        obt = [clave_volcado(t, p) for t, p in leer_volcado(txt)]
        falta, sobra = comparar(esp, obt)
        corridas[nom] = {"claves": obt, "falta": falta, "sobra": sobra,
                         "ms": tiempo_ms(os.path.join(res, nom + ".ms")),
                         "internos": tiempos_internos(os.path.join(res, nom + ".acadparalelo.txt"))}
    return {"esp": esp, "orig": orig, "lectura": (sum(f0.values()), sum(s0.values())), "corridas": corridas,
            "ms_abrir": tiempo_ms(os.path.join(res, "original.ms"))}


def informe_overkill(nombre, man, r, out):
    out.append(f"\n### {nombre} ({man['densidad']}, {man['n']:,} entidades)\n")
    if r is None:
        out.append("Sin resultados (falta original.txt).\n"); return
    fl, sl = r["lectura"]
    if fl or sl:
        out.append(f"**Aviso:** lo que lee v2 del DXF no coincide con lo que abrió AutoCAD ({fl} faltan, {sl} sobran).\n")
    cor = r["corridas"]
    noms = sorted(cor, key=lambda n: (not n.startswith("overkill"), int(re.sub(r"\D", "", n) or 0)))
    cab = "| capa | clase | entrada | esperado (v2) | " + " | ".join(noms) + " |"
    out.append(cab); out.append("|" + "---|" * (4 + len(noms)))
    ent_capa = Counter(k[1] for k in r["orig"]); esp_capa = Counter(k[1] for k in r["esp"])
    for capa, info in man["capas"].items():
        celdas = []
        for n in noms:
            c = cor[n]
            got = sum(1 for k in c["claves"] if k[1] == capa)
            fa = sum(v for k, v in c["falta"].items() if k[1] == capa)
            so = sum(v for k, v in c["sobra"].items() if k[1] == capa)
            celdas.append(f"{got:,}" + (" ✓" if fa == so == 0 else f" (−{fa:,} +{so:,})"))
        out.append(f"| {capa} | {info['clase']} | {ent_capa[capa]:,} | {esp_capa[capa]:,} | " + " | ".join(celdas) + " |")
    tot = []
    for n in noms:
        c = cor[n]
        fa, so = sum(c["falta"].values()), sum(c["sobra"].values())
        tot.append(f"{len(c['claves']):,}" + (" ✓" if fa == so == 0 else f" (−{fa:,} +{so:,})"))
    out.append(f"| **total** | | {len(r['orig']):,} | {len(r['esp']):,} | " + " | ".join(tot) + " |")
    out.append("\n(−faltan +sobran respecto de v2, comparando geometría.)\n")
    pov = [n for n in noms if n.startswith("poverkill")]
    if len(pov) > 1:
        a = Counter(cor[pov[0]]["claves"])
        iguales = all(Counter(cor[n]["claves"]) == a for n in pov[1:])
        out.append(f"POVERKILL con {', '.join(pov)}: {'mismo dibujo' if iguales else '**DISTINTO**'}.\n")
    for n in noms:
        c = cor[n]
        out.append(f"- {n}: comando {c['ms'] / 1000:.2f} s" if c["ms"] is not None else f"- {n}: sin tiempo")
        if c["internos"]:
            out[-1] += f" ({c['internos']})"


# ------------------------------------------------------------------------------------------- HATCH
def de_boor(cps, knots, p, n):
    lo, hi = knots[p], knots[len(knots) - p - 1]
    pts = []
    for s in range(n + 1):
        t = lo + (hi - lo) * s / n
        k = p
        while k < len(knots) - p - 2 and knots[k + 1] <= t:
            k += 1
        d = [list(cps[j + k - p]) for j in range(p + 1)]
        for r in range(1, p + 1):
            for j in range(p, r - 1, -1):
                i = j + k - p
                den = knots[i + p - r + 1] - knots[i]
                a = 0.0 if den == 0 else (t - knots[i]) / den
                d[j] = [(1 - a) * d[j - 1][0] + a * d[j][0], (1 - a) * d[j - 1][1] + a * d[j][1]]
        pts.append(tuple(d[p]))
    return pts


def ang_a_rad(a0, a1):
    """Los ángulos de los lazos pueden venir en grados o radianes según la fuente."""
    if max(abs(a0), abs(a1)) > 2 * math.pi + 1e-6:
        return math.radians(a0), math.radians(a1)
    return a0, a1


def arco_pts(c, r, a0, a1, ccw, n=720):
    if not ccw:
        a0, a1 = -a0, -a1
    sw = (a1 - a0) if ccw else (a0 - a1)
    sw = sw % (2 * math.pi) or 2 * math.pi
    sg = 1 if ccw else -1
    m = max(4, int(n * sw / (2 * math.pi)))
    return [(c[0] + r * math.cos(a0 + sg * sw * k / m), c[1] + r * math.sin(a0 + sg * sw * k / m)) for k in range(m + 1)]


def bulge_pts(p0, p1, b, n=720):
    """Puntos del tramo p0 -> p1 (sin p1). bulge = tan(ángulo/4), positivo = antihorario."""
    if abs(b) < 1e-12:
        return [p0]
    th = 4 * math.atan(b)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ch = math.hypot(dx, dy)
    d = ch / (2 * math.tan(th / 2))                    # distancia con signo del centro a la cuerda (a la izquierda)
    cx, cy = (p0[0] + p1[0]) / 2 - dy / ch * d, (p0[1] + p1[1]) / 2 + dx / ch * d
    r = math.hypot(p0[0] - cx, p0[1] - cy)
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    m = max(4, int(n * abs(th) / (2 * math.pi)))
    return [(cx + r * math.cos(a0 + th * k / m), cy + r * math.sin(a0 + th * k / m)) for k in range(m)]


def area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2


def dentro(pt, poly):
    x, y = pt; c = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def lazos_hatch(pares):
    """Reconstruye los lazos de un HATCH volcado -> [(polígono, curvo)]."""
    i = next((k for k, (c, _) in enumerate(pares) if c == 91), None)
    if i is None:
        return []
    it = iter(pares[i + 1:])
    cola = list(it)
    pos = [0]

    def sig(esp=None):
        while pos[0] < len(cola):
            c, v = cola[pos[0]]; pos[0] += 1
            if esp is None or c == esp:
                return c, v
        raise ValueError("lazo incompleto")
    n_lazos = int(pares[i][1])
    lazos = []
    for _ in range(n_lazos):
        _, fl = sig(92); fl = int(fl)
        pts, curvo = [], False
        if fl & 2:
            _, hb = sig(72); sig(73); _, nv = sig(93)
            vs = []
            for _ in range(int(nv)):
                _, p = sig(10); x, y = nums(p)[:2]; b = 0.0
                if int(hb):
                    _, bb = sig(42); b = float(bb)
                vs.append((x, y, b))
            for k in range(len(vs)):
                p0, p1 = vs[k][:2], vs[(k + 1) % len(vs)][:2]
                if vs[k][2]:
                    curvo = True
                pts += bulge_pts(p0, p1, vs[k][2])
        else:
            _, ne = sig(93)
            for _ in range(int(ne)):
                _, t = sig(72); t = int(t)
                if t == 1:
                    _, a = sig(10); _, b = sig(11); pts.append(tuple(nums(a)[:2]))
                elif t == 2:
                    _, c = sig(10); _, r = sig(40); _, a0 = sig(50); _, a1 = sig(51); _, ccw = sig(73)
                    a0, a1 = ang_a_rad(float(a0), float(a1))
                    pts += arco_pts(nums(c)[:2], float(r), a0, a1, int(ccw))[:-1]; curvo = True
                elif t == 3:
                    _, c = sig(10); _, mj = sig(11); _, ra = sig(40); _, a0 = sig(50); _, a1 = sig(51); _, ccw = sig(73)
                    c = nums(c)[:2]; mj = nums(mj)[:2]; ra = float(ra)
                    a0, a1 = ang_a_rad(float(a0), float(a1))
                    for x, y in arco_pts((0, 0), 1.0, a0, a1, int(ccw))[:-1]:
                        pts.append((c[0] + mj[0] * x - mj[1] * ra * y, c[1] + mj[1] * x + mj[0] * ra * y))
                    curvo = True
                elif t == 4:
                    _, deg = sig(94); _, rac = sig(73); sig(74); _, nk = sig(95); _, nc = sig(96)
                    kn = [float(sig(40)[1]) for _ in range(int(nk))]
                    cp = [tuple(nums(sig(10)[1])[:2]) for _ in range(int(nc))]
                    if int(rac):
                        for _ in range(int(nc)):
                            sig(42)
                    pts += de_boor(cp, kn, int(deg), 2000)[:-1]; curvo = True
                    # datos de ajuste opcionales (97 n, 11 puntos, 12 y 13 tangentes): se saltan en el lazo siguiente
        lazos.append((pts, curvo))
    return lazos


def area_hatch(lazos):
    polys = [p for p, _ in lazos if len(p) >= 3]
    if not polys:
        return 0.0, None
    tot = 0.0
    for i, p in enumerate(polys):
        prof = sum(1 for j, o in enumerate(polys) if j != i and abs(area(o)) > abs(area(p)) and dentro(p[0], o))
        tot += (-1) ** prof * abs(area(p))
    ext = max(polys, key=lambda p: abs(area(p)))
    return tot, ext


def verificar_hatch(man, res):
    pts = man["puntos"]
    celda = 10.0
    rej = defaultdict(list)
    for k, p in enumerate(pts):
        rej[(math.floor(p["x"] / celda), math.floor(p["y"] / celda))].append(k)
    corridas = {}
    for txt in sorted(glob.glob(os.path.join(res, "*.txt"))):
        nom = os.path.basename(txt)[:-4]
        if nom.endswith(".acadparalelo"):
            continue
        hs = [p for t, p in leer_volcado(txt) if t == "HATCH"]
        por_punto = defaultdict(list)
        sin_punto = varios = 0
        for pares in hs:
            try:
                lz = lazos_hatch(pares)
            except (ValueError, StopIteration, IndexError):
                sin_punto += 1; continue
            a, ext = area_hatch(lz)
            if ext is None:
                sin_punto += 1; continue
            curvo = any(c for _, c in lz)
            xs = [x for x, _ in ext]; ys = [y for _, y in ext]
            cand = [k for i in range(math.floor(min(xs) / celda), math.floor(max(xs) / celda) + 1)
                    for j in range(math.floor(min(ys) / celda), math.floor(max(ys) / celda) + 1) for k in rej.get((i, j), ())]
            dentro_k = [k for k in cand if dentro((pts[k]["x"], pts[k]["y"]), ext)]
            if not dentro_k:
                sin_punto += 1
            if len(dentro_k) > 1:
                varios += 1
            for k in dentro_k:
                por_punto[k].append((a, curvo))
        fam = defaultdict(Counter)
        for k, p in enumerate(pts):
            h = por_punto.get(k, [])
            f = p["familia"]
            if not h:
                fam[f]["sin sombreado"] += 1; continue
            if len(h) > 1:
                fam[f]["varios sombreados"] += 1; continue
            a, curvo = h[0]
            tol = 2e-3 if curvo or f in ("H_CIRCULO", "H_ARCOS", "H_ELIPSE", "H_SPLINE") else 1e-6
            def igual(x): return abs(a - x) <= tol * max(1.0, abs(x))
            if igual(p["area_exterior"]) and igual(p["area_normal"]):
                fam[f]["ok"] += 1
            elif igual(p["area_exterior"]):
                fam[f]["ok (Exterior)"] += 1
            elif igual(p["area_normal"]):
                fam[f]["ok (Normal)"] += 1
            else:
                fam[f]["área distinta"] += 1
        corridas[nom] = {"n": len(hs), "fam": fam, "sin_punto": sin_punto, "varios": varios,
                         "ms": tiempo_ms(os.path.join(res, nom + ".ms")),
                         "internos": tiempos_internos(os.path.join(res, nom + ".acadparalelo.txt"))}
    return corridas


def informe_hatch(nombre, man, cor, out):
    out.append(f"\n### {nombre} ({man['densidad']}, {len(man['puntos']):,} áreas)\n")
    if not cor:
        out.append("Sin resultados.\n"); return
    noms = sorted(cor, key=lambda n: (not n.startswith("hatch"), int(re.sub(r"\D", "", n) or 0)))
    out.append("| familia | PHATCH la soporta | puntos | " + " | ".join(noms) + " |")
    out.append("|" + "---|" * (3 + len(noms)))
    for f, info in man["familias"].items():
        if not info["puntos"]:
            continue
        celdas = []
        for n in noms:
            c = cor[n]["fam"][f]
            celdas.append(", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: kv[0] != "ok")))
        out.append(f"| {f} | {'sí' if info['phatch_soporta'] else 'no'} | {info['puntos']} | " + " | ".join(celdas) + " |")
    out.append("")
    for n in noms:
        c = cor[n]
        extra = (f", {c['sin_punto']} sin punto dentro" if c["sin_punto"] else "") + \
                (f", {c['varios']} cubren varios puntos (se salen de su área)" if c["varios"] else "")
        out.append(f"- {n}: {c['n']:,} sombreados{extra}; " +
                   (f"comando {c['ms'] / 1000:.2f} s" if c["ms"] is not None else "sin tiempo") +
                   (f" ({c['internos']})" if c["internos"] else ""))


# ------------------------------------------------------------------------------------------- corte
def punto_de_corte(filas, out, nativo, nuevo, unidad):
    """filas: [(tamaño, {corrida: ms})] de una misma densidad, ordenadas por tamaño."""
    rap = [n for n in sorted({k for _, t in filas for k in t if k.startswith(nuevo)}, key=lambda n: int(re.sub(r"\D", "", n)))]
    if not rap or not any(nativo in t for _, t in filas):
        return
    out.append(f"| {unidad} | {nativo} | " + " | ".join(rap) + " | más rápido que el nativo |")
    out.append("|" + "---|" * (3 + len(rap)))
    corte = None
    for tam, t in filas:
        nat = t.get(nativo)
        celdas = []
        for r in rap:
            v = t.get(r)
            celdas.append("—" if v is None else f"{v / 1000:.2f} s" + (f" ({nat / v:.1f}x)" if nat and v else ""))
        mejor = min((t[r] for r in rap if t.get(r)), default=None)
        gana = nat is not None and mejor is not None and mejor < nat
        corte = corte if (gana and corte is not None) else (tam if gana else None)
        out.append(f"| {tam:,} | " + (f"{nat / 1000:.2f} s" if nat is not None else "—") + " | " + " | ".join(celdas) +
                   f" | {'sí' if gana else 'no'} |")
    out.append("\n" + (f"**Punto de corte: desde {corte:,} {unidad}** (de ahí en adelante siempre gana).\n" if corte is not None
                       else "No hay tamaño desde el que gane siempre.\n"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dibujos")
    ap.add_argument("--resultados")
    ap.add_argument("--md", help="archivo del informe (por defecto <resultados>/informe.md)")
    a = ap.parse_args()
    res_dir = a.resultados or os.path.join(a.dibujos, "resultados")
    out = ["# Batería POVERKILL y PHATCH\n"]
    serie_ok, serie_h = defaultdict(list), defaultdict(list)
    secc_ok, secc_h = [], []
    for js in sorted(glob.glob(os.path.join(a.dibujos, "*.dxf.json")), key=lambda p: (os.path.basename(p)[0], os.path.getsize(p))):
        man = json.load(open(js, encoding="utf-8"))
        base = man["archivo"][:-4]
        res = os.path.join(res_dir, base)
        if not os.path.isdir(res):
            continue
        print(f"verificando {base} ...", flush=True)
        if man["comando"] == "overkill":
            r = verificar_overkill(js[:-5], man, res)
            informe_overkill(base, man, r, secc_ok)
            if r:
                serie_ok[man["densidad"]].append((man["n"], {n: c["ms"] for n, c in r["corridas"].items() if c["ms"]}))
        else:
            cor = verificar_hatch(man, res)
            informe_hatch(base, man, cor, secc_h)
            serie_h[man["densidad"]].append((len(man["puntos"]), {n: c["ms"] for n, c in cor.items() if c["ms"]}))
    if serie_ok:
        out.append("## OVERKILL: tiempo del comando y punto de corte\n")
        for d, filas in serie_ok.items():
            out.append(f"\n**{d}**\n")
            punto_de_corte(sorted(filas), out, "overkill_nativo", "poverkill", "entidades")
    if serie_h:
        out.append("## HATCH: tiempo del comando y punto de corte\n")
        for d, filas in serie_h.items():
            out.append(f"\n**{d}**\n")
            punto_de_corte(sorted(filas), out, "hatch_nativo", "phatch", "áreas")
    if secc_ok:
        out.append("\n## OVERKILL: resultado por dibujo y capa\n"); out += secc_ok
    if secc_h:
        out.append("\n## HATCH: resultado por dibujo y familia\n"); out += secc_h
    texto = "\n".join(out) + "\n"
    md = a.md or os.path.join(res_dir, "informe.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)
    print(f"informe: {md}")


if __name__ == "__main__":
    main()
