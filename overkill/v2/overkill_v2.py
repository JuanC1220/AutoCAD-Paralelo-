"""OVERKILL v2: motor de referencia geométrico y robusto (LINE, ARC, CIRCLE, LWPOLYLINE).

Qué cambia respecto a overkill_core (v1) y al OVERKILL de AutoCAD:
  * La tolerancia es una distancia real: dos líneas se tratan si los extremos de la más corta
    quedan a <= tol de la recta de la más larga (en 3D). No se redondea a una rejilla (v1) ni
    se exige que el ángulo coincida a 1e-10 rad (AutoCAD), así que no hay fallos por
    coordenadas grandes (UTM), giros diminutos o extremos movidos dentro de la tolerancia.
  * Se comparan todas las propiedades que OVERKILL ofrece ignorar: capa, color (índice y
    color verdadero), tipo de línea, escala de tipo, grosor de línea, altura (thickness),
    transparencia, estilo de trazado, material y vector de extrusión. Z cuenta.
  * Capas bloqueadas y congeladas no se tocan (igual que AutoCAD con "Todo").
  * Arcos y círculos: mismo centro, radio y normal (a tol) -> se fusionan arcos solapados
    o extremo con extremo; un arco dentro de un círculo se borra.
  * Polilíneas idénticas (también invertidas o con otro vértice inicial si son cerradas) -> una.

Cómo encuentra candidatos sin pares O(n^2) y sin "bordes" entre trabajadores:
  1. Cada línea tiene ángulo th en [0, pi) y una incertidumbre angular D = 2*tol/L (cuánto
     puede diferir el ángulo de otra línea colineal a tol). Se registra en todas las cubetas
     angulares de ancho W que toca [th - D, th + D] (casi siempre 1).
  2. En cada cubeta se usa UNA normal fija n_b, así que rho = n_b . punto_medio no arrastra el
     error angular multiplicado por la distancia al origen (lo que rompe UTM).
  3. Se agrupan por rho (enlace simple con margen tol + (W + D) * Lmax) y dentro de cada grupo
     se barre por t (proyección) comparando sólo piezas cuyos intervalos se tocan.
  4. Cada par candidato se verifica con la geometría exacta. Los pares aceptados se unen
     (union-find). Cada componente se reemplaza por su superviviente (la primera del archivo)
     estirado a los extremos reales más lejanos.
Las cubetas son independientes: se reparten entre trabajadores y el resultado (conjunto de
pares) no depende del reparto ni del orden del archivo.
"""
import math
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict

import numpy as np

PI = math.pi
NB = 31416              # cubetas angulares en [0, pi): ancho exacto pi/NB (~1e-4 rad)
W_ANG = PI / NB


# ======================================================================= lectura
PROP_CODES = {8: "capa", 62: "color", 420: "rgb", 6: "tipo", 48: "esc_tipo", 370: "grosor",
              39: "altura", 440: "transp", 390: "estilo", 347: "material"}


class Dib:
    """Copia plana del dibujo: columnas por tipo de entidad."""

    def __init__(self):
        self.n = 0                     # entidades leídas (todas las de tipos soportados)
        self.tipo, self.capa, self.prop, self.handle = [], [], [], []
        self.geo = []                  # por entidad: tupla con la geometría
        self.capas_bloq = set()


def leer(path):
    """Lector de DXF ASCII. Devuelve Dib con LINE, ARC, CIRCLE, LWPOLYLINE de ENTITIES."""
    D = Dib()
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = f.read().split("\n")
    n = len(rows) - 1
    i = 0
    sec = None
    cur = None
    in_layer = None
    TIPOS = ("LINE", "ARC", "CIRCLE", "LWPOLYLINE")

    def flush(c):
        t = c["t"]
        props = tuple(c.get(k, "") for k in (62, 420, 6, 48, 370, 39, 440, 390, 347)) + \
            ((c.get(210, "0"), c.get(220, "0"), c.get(230, "1")),)
        cap = c.get(8, "0")
        g = c["g"]
        if t == "LINE":
            geo = (float(g[10]), float(g[20]), float(g.get(30, 0)), float(g[11]), float(g[21]), float(g.get(31, 0)))
        elif t == "CIRCLE":
            geo = (float(g[10]), float(g[20]), float(g.get(30, 0)), float(g[40]))
        elif t == "ARC":
            geo = (float(g[10]), float(g[20]), float(g.get(30, 0)), float(g[40]), float(g[50]), float(g[51]))
        else:
            geo = (int(c.get(70, "0")) & 1, float(c.get(38, 0)), tuple(c["v"]))
        D.tipo.append(t); D.capa.append(cap); D.prop.append((cap,) + props)
        D.handle.append(c.get(5, "")); D.geo.append(geo)

    while i < n:
        code = int(rows[i]); val = rows[i + 1].strip(); i += 2
        if code == 0:
            if cur is not None:
                flush(cur); cur = None
            in_layer = None
            if val == "SECTION":
                sec = rows[i + 1].strip(); i += 2
            elif val == "ENDSEC":
                sec = None
            elif sec == "ENTITIES" and val in TIPOS:
                cur = {"t": val, "g": {}, "v": []}
            elif sec == "TABLES" and val == "LAYER":
                in_layer = {}
            continue
        if in_layer is not None:
            if code == 2:
                in_layer["n"] = val
            elif code == 70 and "n" in in_layer and (int(val) & 5):
                D.capas_bloq.add(in_layer["n"])
            continue
        if cur is None:
            continue
        if cur["t"] == "LWPOLYLINE":
            if code == 10:
                cur["v"].append([float(val), 0.0, 0.0])
            elif code == 20:
                cur["v"][-1][1] = float(val)
            elif code == 42:
                cur["v"][-1][2] = float(val)
            elif code in (70, 38, 5, 8) or code in PROP_CODES or code in (210, 220, 230):
                cur[code] = val
        else:
            if code in (10, 20, 30, 11, 21, 31, 40, 50, 51):
                cur["g"][code] = val
            elif code == 5 or code in PROP_CODES or code in (210, 220, 230):
                cur[code] = val
    if cur is not None:
        flush(cur)
    for k, g in enumerate(D.geo):
        if D.tipo[k] == "LWPOLYLINE":
            D.geo[k] = (g[0], g[1], tuple(tuple(v) for v in g[2]))
    D.n = len(D.tipo)
    return D


# ======================================================================= utilidades
class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        p = self.p
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            if a < b:
                self.p[b] = a
            else:
                self.p[a] = b


# ======================================================================= líneas
def _prep_lines(X0, Y0, Z0, X1, Y1, Z1, tol):
    dx, dy = X1 - X0, Y1 - Y0
    L = np.sqrt(dx * dx + dy * dy + (Z1 - Z0) ** 2)
    Lxy = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)
    th = np.where(th < 0, th + PI, th)
    th = np.where(th >= PI, th - PI, th)
    with np.errstate(divide="ignore"):
        D = np.where(Lxy > 0, np.minimum(PI / 2, 2.0 * tol / np.maximum(Lxy, 1e-300) * 1.0001 + 1e-15), PI / 2)
    return L, Lxy, th, D


def _pair_ok(i, j, X0, Y0, Z0, X1, Y1, Z1, L, tol, e2e):
    """Verificación exacta. Devuelve True si i y j deben fusionarse."""
    if L[j] > L[i] or (L[j] == L[i] and j < i):
        i, j = j, i                                  # i = la más larga
    ax, ay, az = X0[i], Y0[i], Z0[i]
    Li = L[i]
    ux, uy, uz = (X1[i] - ax) / Li, (Y1[i] - ay) / Li, (Z1[i] - az) / Li
    s = []
    for (qx, qy, qz) in ((X0[j], Y0[j], Z0[j]), (X1[j], Y1[j], Z1[j])):
        vx, vy, vz = qx - ax, qy - ay, qz - az
        t = vx * ux + vy * uy + vz * uz
        cx, cy, cz = vy * uz - vz * uy, vz * ux - vx * uz, vx * uy - vy * ux
        if cx * cx + cy * cy + cz * cz > tol * tol:
            return False
        s.append(t)
    lo, hi = min(s), max(s)
    ov = min(hi, Li) - max(lo, 0.0)
    if ov > tol:
        return True
    return e2e and ov >= -tol


_COLS = [None]


def _init(cols):
    _COLS[0] = cols


def _bucket_pairs(task):
    """Trabajador: pares candidatos verificados dentro de un lote de cubetas."""
    tol, e2e, groups = task
    X0, Y0, Z0, X1, Y1, Z1, L, Lxy, D = _COLS[0]
    pairs = []
    for b, ids in groups:
        th_b = (b + 0.5) * W_ANG
        nx, ny = -math.sin(th_b), math.cos(th_b)
        ux, uy = math.cos(th_b), math.sin(th_b)
        recs = []
        lmax = 0.0
        dmax = 0.0
        for i in ids:
            mx, my = (X0[i] + X1[i]) / 2, (Y0[i] + Y1[i]) / 2
            recs.append((nx * mx + ny * my, i))
            if Lxy[i] > lmax:
                lmax = Lxy[i]
            if D[i] > dmax:
                dmax = D[i]
        recs.sort()
        win = 2 * tol + (W_ANG + 2 * dmax) * lmax          # margen en rho
        # grupos por rho (enlace simple)
        k = 0
        n = len(recs)
        while k < n:
            m = k + 1
            while m < n and recs[m][0] - recs[m - 1][0] <= win:
                m += 1
            if m - k > 1:
                items = []
                for _, i in recs[k:m]:
                    t0 = ux * X0[i] + uy * Y0[i]
                    t1 = ux * X1[i] + uy * Y1[i]
                    items.append((min(t0, t1), max(t0, t1), i))
                items.sort()
                act = []
                for t0, t1, i in items:
                    act = [a for a in act if a[0] >= t0 - 2 * tol]
                    for _, j in act:
                        if _pair_ok(i, j, X0, Y0, Z0, X1, Y1, Z1, L, tol, e2e):
                            pairs.append((i, j) if i < j else (j, i))
                    act.append((t1, i))
            k = m
    return pairs


def lineas(D, idx, tol, e2e, workers=1, pool=None, timings=None):
    """idx: índices de entidades LINE a tratar. Devuelve {sup: (p_ini, p_fin)} y set de borradas."""
    t = time.perf_counter()
    G = np.array([D.geo[i] for i in idx], dtype=np.float64).reshape(-1, 6)
    X0, Y0, Z0, X1, Y1, Z1 = (np.ascontiguousarray(G[:, k]) for k in range(6))
    L, Lxy, th, Dang = _prep_lines(X0, Y0, Z0, X1, Y1, Z1, tol)
    pid = {}
    P = np.array([pid.setdefault(D.prop[i], len(pid)) for i in idx], dtype=np.int64)
    n = len(idx)
    nb = NB
    uf = UF(n)

    # --- puntos (longitud <= tol): duplicados por posición
    pts = np.nonzero(L <= tol)[0]
    if len(pts):
        cell = defaultdict(list)
        for i in pts.tolist():
            cell[(P[i], math.floor(X0[i] / tol), math.floor(Y0[i] / tol), math.floor(Z0[i] / tol))].append(i)
        for (p, cx, cy, cz), ids in cell.items():
            for i in ids:
                for ddx in (-1, 0, 1):
                    for ddy in (-1, 0, 1):
                        for ddz in (-1, 0, 1):
                            for j in cell.get((p, cx + ddx, cy + ddy, cz + ddz), ()):
                                if j > i and (X0[i] - X0[j]) ** 2 + (Y0[i] - Y0[j]) ** 2 + (Z0[i] - Z0[j]) ** 2 <= tol * tol:
                                    uf.union(i, j)

    # --- líneas reales
    # verticales puras (sin longitud en XY): cubeta especial por posición XY
    seg = np.nonzero(L > tol)[0]
    vert = seg[Lxy[seg] <= tol]
    seg = seg[Lxy[seg] > tol]
    lo = np.floor((th[seg] - Dang[seg]) / W_ANG).astype(np.int64)
    hi = np.floor((th[seg] + Dang[seg]) / W_ANG).astype(np.int64)
    cnt = hi - lo + 1
    rep = np.repeat(seg, cnt)
    off = np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    bk = (np.repeat(lo, cnt) + off) % nb
    key = P[rep] * nb + bk
    order = np.lexsort((rep, key))
    key, rep = key[order], rep[order]
    cuts = np.nonzero(np.diff(key))[0] + 1
    starts = np.concatenate([[0], cuts]); ends = np.concatenate([cuts, [len(key)]])
    sizes = ends - starts
    multi = np.nonzero(sizes > 1)[0]
    groups = [(int(key[starts[g]] % nb), rep[starts[g]:ends[g]].tolist()) for g in multi.tolist()]
    t1 = time.perf_counter()

    cols = (X0, Y0, Z0, X1, Y1, Z1, L, Lxy, Dang)
    if workers > 1 and len(groups) > 1:
        nparts = workers * 4
        parts = [[] for _ in range(nparts)]
        load = [0] * nparts
        for g in sorted(groups, key=lambda g: -len(g[1])):
            k = load.index(min(load)); parts[k].append(g); load[k] += len(g[1]) ** 1.2
        tasks = [(tol, e2e, p) for p in parts if p]
        own = True
        pool = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn").Pool(
            workers, initializer=_init, initargs=(cols,))
        try:
            outs = pool.map(_bucket_pairs, tasks, chunksize=1)
        finally:
            if own:
                pool.close(); pool.join()
        pairs = [p for o in outs for p in o]
    else:
        _COLS[0] = cols
        pairs = _bucket_pairs((tol, e2e, groups))
    # verticales puras: agrupar por (prop, celda XY) y verificar
    if len(vert):
        cell = defaultdict(list)
        h = max(tol, 1e-9) * 4
        for i in vert.tolist():
            cell[(P[i], math.floor(X0[i] / h), math.floor(Y0[i] / h))].append(i)
        for (p, cx, cy), ids in cell.items():
            near = [j for ddx in (-1, 0, 1) for ddy in (-1, 0, 1) for j in cell.get((p, cx + ddx, cy + ddy), ())]
            for i in ids:
                for j in near:
                    if j > i and _pair_ok(i, j, X0, Y0, Z0, X1, Y1, Z1, L, tol, e2e):
                        pairs.append((i, j))
    t2 = time.perf_counter()
    for i, j in pairs:
        uf.union(i, j)
    comp = defaultdict(list)
    for i in range(n):
        comp[uf.find(i)].append(i)
    nuevos, borr = {}, set()
    for r, mem in comp.items():
        if len(mem) == 1:
            continue
        ref = max(mem, key=lambda k: (L[k], -k))
        if L[ref] <= tol:                       # todo puntos
            for k in mem[1:]:
                borr.add(idx[k])
            continue
        ux, uy, uz = (X1[ref] - X0[ref]) / L[ref], (Y1[ref] - Y0[ref]) / L[ref], (Z1[ref] - Z0[ref]) / L[ref]
        best_lo = best_hi = None
        for k in mem:
            for (x, y, z) in ((X0[k], Y0[k], Z0[k]), (X1[k], Y1[k], Z1[k])):
                s = (x - X0[ref]) * ux + (y - Y0[ref]) * uy + (z - Z0[ref]) * uz
                if best_lo is None or s < best_lo[0]:
                    best_lo = (s, (x, y, z))
                if best_hi is None or s > best_hi[0]:
                    best_hi = (s, (x, y, z))
        sup = mem[0]                             # primera del archivo (mem está ordenado)
        a, b = best_lo[1], best_hi[1]
        fwd = (X1[sup] - X0[sup]) * ux + (Y1[sup] - Y0[sup]) * uy + (Z1[sup] - Z0[sup]) * uz >= 0
        nuevos[idx[sup]] = (a, b) if fwd else (b, a)
        for k in mem[1:]:
            borr.add(idx[k])
    if timings is not None:
        timings.update(lin_preparar=t1 - t, lin_pares=t2 - t1, lin_unir=time.perf_counter() - t2,
                       lin_pares_n=len(pairs), lin_cubetas=len(groups))
    return nuevos, borr


# ======================================================================= arcos y círculos
def arcos(D, idx, tol, e2e):
    """Círculos y arcos sobre la misma circunferencia (centro, radio, normal y propiedades)."""
    h = max(tol, 1e-9) * 4
    cell = defaultdict(list)
    for i in idx:
        g = D.geo[i]
        cell[(D.prop[i], math.floor(g[0] / h), math.floor(g[1] / h), math.floor(g[2] / h))].append(i)
    uf = {i: i for i in idx}

    def find(a):
        while uf[a] != a:
            uf[a] = uf[uf[a]]; a = uf[a]
        return a
    for (p, cx, cy, cz), ids in cell.items():
        near = [j for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) for j in cell.get((p, cx + a, cy + b, cz + c), ())]
        for i in ids:
            gi = D.geo[i]
            for j in near:
                if j <= i:
                    continue
                gj = D.geo[j]
                if (gi[0] - gj[0]) ** 2 + (gi[1] - gj[1]) ** 2 + (gi[2] - gj[2]) ** 2 <= tol * tol and abs(gi[3] - gj[3]) <= tol:
                    a, b = find(i), find(j)
                    if a != b:
                        uf[max(a, b)] = min(a, b)
    circ = defaultdict(list)
    for i in idx:
        circ[find(i)].append(i)
    borr, nuevos = set(), {}
    for mem in circ.values():
        if len(mem) == 1:
            continue
        mem.sort()
        r = D.geo[mem[0]][3]
        atol = math.degrees(tol / r)
        circles = [i for i in mem if D.tipo[i] == "CIRCLE"]
        if circles:                              # un círculo cubre todo lo demás
            keep = circles[0]
            borr.update(k for k in mem if k != keep)
            continue
        iv = {}
        for i in mem:
            a0 = D.geo[i][4] % 360.0
            sw = (D.geo[i][5] - D.geo[i][4]) % 360.0 or 360.0
            iv[i] = (a0, sw)
        for comp in _arcos_unir(iv, atol, e2e):
            if len(comp) < 2:
                continue
            sup = comp[0]
            ini, barr = _arco_cubierto([iv[k] for k in comp], atol)
            nuevos[sup] = "circulo" if barr >= 360.0 - atol else (ini % 360.0, (ini + barr) % 360.0)
            borr.update(comp[1:])
    return nuevos, borr


def _arcos_unir(iv, atol, e2e):
    """iv: {id: (inicio, barrido)} en grados sobre una misma circunferencia.
    Barre la lista duplicada (+360) para ver solapes a través de 0 grados. -> componentes."""
    ext = sorted([(a, a + sw, i) for i, (a, sw) in iv.items()] + [(a + 360, a + sw + 360, i) for i, (a, sw) in iv.items()])
    par = {i: i for i in iv}

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]; x = par[x]
        return x
    s0 = s1 = None
    last = None
    for a, b, i in ext:
        if s1 is not None and (a < s1 - atol or (e2e and a <= s1 + atol) or (abs(a - s0) <= atol and abs(b - s1) <= atol)):
            x, y = find(i), find(last)
            if x != y:
                par[max(x, y)] = min(x, y)
            s1 = max(s1, b)
        else:
            s0, s1 = a, b
        last = i
    comp = defaultdict(list)
    for i in sorted(iv):
        comp[find(i)].append(i)
    return list(comp.values())


def _arco_cubierto(arcs, atol):
    """Unión de arcos ya conectados -> (inicio, barrido). Prueba cada inicio como origen."""
    best = None
    for a_s, _ in arcs:
        rot = sorted(((a - a_s) % 360.0, sw) for a, sw in arcs)
        if rot[0][0] > atol and rot[0][0] < 360 - atol:
            continue
        hi = 0.0
        ok = True
        for a, sw in rot:
            if a > 360 - atol:
                a -= 360.0
            if a > hi + atol:
                ok = False
                break
            hi = max(hi, a + sw)
        if ok and (best is None or hi > best[1]):
            best = (a_s, min(hi, 360.0))
    return best


# ======================================================================= polilíneas
def polilineas(D, idx, tol):
    def canon(g):
        closed, elev, vs = g
        pts = [(round(x / tol), round(y / tol), round(bu, 9)) for x, y, bu in vs]
        cands = []
        n = len(pts)
        seqs = [pts]
        rev = [(x, y, -pts[(k - 1) % n][2] if closed else (-pts[k - 1][2] if k > 0 else 0.0))
               for k, (x, y, _) in reversed(list(enumerate(pts)))]
        seqs.append(rev)
        for s in seqs:
            if closed:
                for k in range(n):
                    cands.append(tuple(s[k:] + s[:k]))
            else:
                cands.append(tuple(s))
        return (closed, round(elev / tol), min(cands))
    seen, borr = {}, set()
    for i in sorted(idx):
        k = (D.prop[i], canon(D.geo[i]))
        if k in seen:
            borr.add(i)
        else:
            seen[k] = i
    return {}, borr


# ======================================================================= comando
def overkill(D, tol=1e-6, e2e=True, workers=1, pool=None, timings=None):
    """Devuelve (nuevos, borradas). nuevos: índice -> geometría nueva del superviviente."""
    t = time.perf_counter()
    por = defaultdict(list)
    for i in range(D.n):
        if D.capa[i] in D.capas_bloq:
            continue
        por[D.tipo[i]].append(i)
    nuevos, borr = {}, set()
    tm = {} if timings is None else timings
    a, b = lineas(D, por["LINE"], tol, e2e, workers, pool, tm)
    nuevos.update(a); borr |= b
    a, b = arcos(D, por["ARC"] + por["CIRCLE"], tol, e2e)
    nuevos.update(a); borr |= b
    a, b = polilineas(D, por["LWPOLYLINE"], tol)
    borr |= b
    tm["total_calculo"] = time.perf_counter() - t
    return nuevos, borr


def contar_por_capa(D, borr):
    from collections import Counter
    return Counter(D.capa[i] for i in range(D.n) if i not in borr)


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf")
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--hilos", type=int, default=1)
    ap.add_argument("--csv", help="escribe capa;cantidad")
    a = ap.parse_args()
    t = time.perf_counter()
    D = leer(a.dxf)
    t1 = time.perf_counter()
    tm = {}
    nuevos, borr = overkill(D, e2e=a.e2e, workers=a.hilos, timings=tm)
    print(f"leídas {D.n:,} en {t1 - t:.1f} s; borradas {len(borr):,}, modificadas {len(nuevos):,}; quedan {D.n - len(borr):,}")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in tm.items()}))
    if a.csv:
        c = contar_por_capa(D, borr)
        with open(a.csv, "w", encoding="utf-8") as f:
            for k in sorted(set(D.capa)):
                f.write(f"{k};{c.get(k, 0)}\n")
