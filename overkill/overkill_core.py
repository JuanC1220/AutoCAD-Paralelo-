"""OVERKILL simplificado para LINE: versión secuencial de referencia y versión paralela.

Receta: leer -> copiar -> calcular en paralelo -> reensamblar -> escribir.

Semántica (equivalente a OVERKILL con las opciones por defecto, sólo LINE):
  * Tolerancia = precisión numérica: cada coordenada se redondea a la rejilla `tol`
    (como hace OVERKILL al "comparar con esa precisión"). Tras el redondeo todo es
    aritmética entera exacta, así que no hay errores de redondeo ni fronteras.
  * Dos líneas son candidatas si tienen las mismas propiedades (capa, color, tipo de
    línea, salvo las ignoradas) y están sobre la misma recta portadora.
  * Sobre cada recta los segmentos son intervalos 1D. Se fusionan si se solapan
    (siempre) o si se tocan extremo con extremo (opción `end_to_end`).
  * De cada grupo fusionado sobrevive la entidad que aparece primero en el archivo;
    sus extremos pasan a ser los extremos reales más lejanos del grupo (coordenadas
    originales, sin recalcular) y conserva su orientación. El resto se borra.

La clave de recta portadora es exacta y hashable, así que el paralelismo es por
particiones de clave (hash), no por zonas del dibujo: una recta entera cae siempre
en un mismo trabajador y no existen "bordes" que coser.
"""
import hashlib
import math
import multiprocessing as mp
from collections import defaultdict

PROPS = ("layer", "color", "linetype")


# ---------------------------------------------------------------- leer / copiar
class Lines:
    """Copia plana (columnar) de las LINE del DXF. Es lo único que ven los cálculos."""

    def __init__(self):
        self.handle, self.layer, self.color, self.linetype = [], [], [], []
        self.x0, self.y0, self.x1, self.y1 = [], [], [], []
        self.layers = []          # nombres de capa (para escribir)

    def freeze(self):
        """Copia columnar en numpy (para la partición vectorizada)."""
        import numpy as np
        self.np = {k: np.asarray(getattr(self, k), dtype=np.float64) for k in ("x0", "y0", "x1", "y1")}

    def __len__(self):
        return len(self.x0)


def read_lines(path):
    """Lector rápido del ENTITIES de un DXF ASCII; sólo LINE, en orden de archivo."""
    L = Lines()
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = f.read().split("\n")
    n = len(rows) - 1
    i = 0
    section = None
    cur = None

    def flush(c):
        if c is not None:
            L.handle.append(c.get(5, ""))
            L.layer.append(c.get(8, "0"))
            L.color.append(int(c.get(62, 256)))
            L.linetype.append(c.get(6, "BYLAYER"))
            L.x0.append(float(c[10])); L.y0.append(float(c[20]))
            L.x1.append(float(c[11])); L.y1.append(float(c[21]))

    while i < n:
        code = int(rows[i]); val = rows[i + 1].strip(); i += 2
        if code == 0:
            if cur is not None:
                flush(cur); cur = None
            if val == "SECTION":
                section = rows[i + 1].strip(); i += 2
            elif val == "ENDSEC":
                section = None
            elif section == "ENTITIES" and val == "LINE":
                cur = {}
        elif cur is not None and code in (5, 8, 62, 6, 10, 20, 11, 21):
            cur[code] = val
    L.layers = sorted(set(L.layer))
    L.freeze()
    return L


def encode_props(L, ignore=()):
    """Propiedades -> un entero por entidad (estable entre procesos). Array numpy."""
    import numpy as np
    code = np.zeros(len(L), dtype=np.int64)
    for p in PROPS:
        if p in ignore:
            continue
        uniq, inv = np.unique(np.asarray(getattr(L, p), dtype=str), return_inverse=True)
        code = code * (len(uniq) + 1) + inv
    return code


# ---------------------------------------------------------------- cálculo
def carrier(prop, x0, y0, x1, y1, tol):
    """-> (clave_recta, t0, t1). Enteros exactos tras redondear a la rejilla tol."""
    X0, Y0 = round(x0 / tol), round(y0 / tol)
    X1, Y1 = round(x1 / tol), round(y1 / tol)
    dx, dy = X1 - X0, Y1 - Y0
    if dx == 0 and dy == 0:                       # línea de longitud cero
        return (prop, 0, 0, X0, Y0), 0, 0
    g = math.gcd(dx, dy)
    ux, uy = dx // g, dy // g
    if uy < 0 or (uy == 0 and ux < 0):          # dirección canónica
        ux, uy = -ux, -uy
    c = ux * Y0 - uy * X0                        # desplazamiento de la recta
    return (prop, ux, uy, c), ux * X0 + uy * Y0, ux * X1 + uy * Y1


def sweep(items, end_to_end):
    """items: [(tmin, tmax, idx, end_min, end_max)] de una misma recta.
    end_* = (idx, 0|1) el extremo real que da ese t.
    Devuelve [(sobreviviente, extremo_min, extremo_max)]."""
    items.sort()
    out = []
    s_min, s_max, surv, e_min, e_max = items[0]
    for tmin, tmax, idx, emin, emax in items[1:]:
        touch = tmin < s_max or (end_to_end and tmin == s_max)
        if touch:
            if tmin == s_min and emin[0] < e_min[0]:
                e_min = emin
            if tmax > s_max or (tmax == s_max and emax[0] < e_max[0]):
                e_max = emax
            s_max = max(s_max, tmax)
            surv = min(surv, idx)
        else:
            out.append((surv, e_min, e_max))
            s_min, s_max, surv, e_min, e_max = tmin, tmax, idx, emin, emax
    out.append((surv, e_min, e_max))
    return out


def item(i, prop, x0, y0, x1, y1, tol):
    key, t0, t1 = carrier(prop, x0, y0, x1, y1, tol)
    if t0 <= t1:
        return key, (t0, t1, i, (i, 0), (i, 1))
    return key, (t1, t0, i, (i, 1), (i, 0))


# ---------------------------------------------------------------- secuencial (referencia)
def overkill_seq(L, tol=1e-6, end_to_end=False, ignore=()):
    props = encode_props(L, ignore).tolist()
    groups = defaultdict(list)
    for i in range(len(L)):
        key, it = item(i, props[i], L.x0[i], L.y0[i], L.x1[i], L.y1[i], tol)
        groups[key].append(it)
    res = [(surv, a, wa, b, wb) for items in groups.values()
           for surv, (a, wa), (b, wb) in sweep(items, end_to_end)]
    res.sort()
    return res


# ---------------------------------------------------------------- paralelo
_G = {}   # estado heredado por fork (copia en escritura, sin serializar la entrada)


def _init(state):
    _G.update(state)


def _pool(workers):
    """fork donde existe (Linux/macOS): los trabajadores heredan _G sin copiarlo.
    En Windows no hay fork: spawn y se envía _G una vez a cada trabajador."""
    if "fork" in mp.get_all_start_methods():
        return mp.get_context("fork").Pool(workers)
    return mp.get_context("spawn").Pool(workers, initializer=_init, initargs=(dict(_G),))
_M = 2147483647   # primo 2^31-1: c mod _M cabe en int64 sin desbordar


def partition_ids(L, props, tol, nparts):
    """Partición de cada entidad = hash(clave de recta) mod nparts, vectorizado.

    Usa la misma aritmética que `carrier` (redondeo, mcd, dirección canónica) pero
    con el desplazamiento c tomado módulo un primo, así que dos líneas sobre la misma
    recta exacta caen SIEMPRE en la misma partición. Coste: milisegundos."""
    import numpy as np
    A = L.np
    X0 = np.rint(A["x0"] / tol).astype(np.int64)
    Y0 = np.rint(A["y0"] / tol).astype(np.int64)
    dx = np.rint(A["x1"] / tol).astype(np.int64) - X0
    dy = np.rint(A["y1"] / tol).astype(np.int64) - Y0
    g = np.gcd(dx, dy)
    zero = g == 0
    g[zero] = 1
    ux, uy = dx // g, dy // g
    flip = (uy < 0) | ((uy == 0) & (ux < 0))
    ux[flip] *= -1
    uy[flip] *= -1
    c = ((ux % _M) * (Y0 % _M) - (uy % _M) * (X0 % _M)) % _M
    c[zero] = ((X0[zero] % _M) * 1000003 + Y0[zero] % _M) % _M   # puntos: por posición
    h = c
    for col in (ux % _M, uy % _M, props % _M):
        h = (h * 1000003 + col) % _M
    return h % nparts


def _work(j):
    """Un trabajador: todas las rectas de su partición, de principio a fin."""
    L, props, tol, e2e = _G["L"], _G["props"], _G["tol"], _G["e2e"]
    x0, y0, x1, y1 = L.x0, L.y0, L.x1, L.y1
    groups = defaultdict(list)
    for i in _G["parts"][j]:
        key, it = item(i, props[i], x0[i], y0[i], x1[i], y1[i], tol)
        groups[key].append(it)
    flat = []                       # salida plana: enteros sueltos serializan rápido
    for items in groups.values():
        for surv, (a, wa), (b, wb) in sweep(items, e2e):
            flat += (surv, a, wa, b, wb)
    return flat


def overkill_par(L, workers=4, tol=1e-6, end_to_end=False, ignore=(), timings=None):
    import time
    import numpy as np
    t = time.perf_counter()
    props = encode_props(L, ignore)
    nparts = workers * 4                        # más partes que hilos = mejor reparto
    pid = partition_ids(L, props, tol, nparts)
    order = np.argsort(pid, kind="stable")
    cuts = np.searchsorted(pid[order], np.arange(1, nparts))
    parts = [p.tolist() for p in np.split(order, cuts)]
    _G.update(L=L, props=props.tolist(), tol=tol, e2e=end_to_end, parts=parts)
    t1 = time.perf_counter()
    # calcular en paralelo: cada partición es independiente (sin bordes que coser)
    with _pool(workers) as pool:
        outs = pool.map(_work, sorted(range(nparts), key=lambda j: -len(parts[j])), chunksize=1)
    t2 = time.perf_counter()
    # reensamblar: orden determinista por índice de entidad original
    flat = np.concatenate([np.asarray(f, dtype=np.int64) for f in outs]).reshape(-1, 5)
    res = flat[np.argsort(flat[:, 0])].tolist()
    _G.clear()
    if timings is not None:
        timings.update(partition=t1 - t, compute=t2 - t1, reassemble=time.perf_counter() - t2)
    return res


# ---------------------------------------------------------------- modo "acad" (regla medida en AutoCAD 2027)
# Medido en AutoCAD 2027 con DXF sintéticos: OVERKILL sólo considera iguales o
# colineales dos líneas casi exactamente paralelas (corte angular interno ~1e-10 rad,
# independiente de la Tolerancia). Después usa la Tolerancia para la distancia entre
# rectas paralelas y para los extremos. Una copia movida 0,3e-6 en cada extremo queda
# girada ~1e-9 rad y AutoCAD NO la borra; una copia sólo trasladada sí.
ATOL = 1e-10


def angle_buckets(L):
    """Cubeta angular de cada línea, en [0, pi) / ATOL (-1 = longitud cero).
    Se calcula una sola vez y la usan igual la versión secuencial y la paralela."""
    import numpy as np
    A = L.np
    dx, dy = A["x1"] - A["x0"], A["y1"] - A["y0"]
    th = np.arctan2(dy, dx)
    th = np.where(th < 0, th + np.pi, th)
    th = np.where(th >= np.pi, th - np.pi, th)
    b = np.floor(th / ATOL).astype(np.int64)
    b[(dx == 0) & (dy == 0)] = -1
    return b


def acad_group(rows, b, tol, end_to_end):
    """rows: [(i, x0, y0, x1, y1)] con mismas propiedades y misma cubeta angular b.
    Agrupa por distancia perpendicular (enlace simple, hueco <= tol) y barre cada
    recta como intervalos 1D con tolerancia. Devuelve [(surv, i_min, e_min, i_max, e_max)]."""
    if b < 0:                                   # longitud cero: duplicados por posición
        seen = {}
        for i, x0, y0, _, _ in rows:
            k = (round(x0 / tol), round(y0 / tol))
            seen[k] = min(seen.get(k, i), i)
        return [(i, i, 0, i, 1) for i in seen.values()]
    th = (b + 0.5) * ATOL
    ux, uy = math.cos(th), math.sin(th)
    recs = []
    for i, x0, y0, x1, y1 in rows:
        rho = ux * (y0 + y1) / 2 - uy * (x0 + x1) / 2
        t0, t1 = ux * x0 + uy * y0, ux * x1 + uy * y1
        recs.append((rho, i, (t0, t1, i, (i, 0), (i, 1)) if t0 <= t1 else (t1, t0, i, (i, 1), (i, 0))))
    recs.sort()
    out, cluster, last = [], [], None
    for rho, _, it in recs:
        if last is not None and rho - last > tol:
            out += _sweep_tol(cluster, tol, end_to_end)
            cluster = []
        cluster.append(it)
        last = rho
    out += _sweep_tol(cluster, tol, end_to_end)
    return out


def _sweep_tol(items, tol, end_to_end):
    items.sort()
    out = []
    s_min, s_max, surv, e_min, e_max = items[0]
    for tmin, tmax, idx, emin, emax in items[1:]:
        if tmin < s_max - tol or (end_to_end and tmin <= s_max + tol) or \
                (abs(tmin - s_min) <= tol and abs(tmax - s_max) <= tol):     # duplicado
            if tmax > s_max + tol or (abs(tmax - s_max) <= tol and emax[0] < e_max[0] and tmax >= s_max):
                e_max = emax
            s_max = max(s_max, tmax)
            surv = min(surv, idx)
        else:
            out.append((surv, e_min[0], e_min[1], e_max[0], e_max[1]))
            s_min, s_max, surv, e_min, e_max = tmin, tmax, idx, emin, emax
    out.append((surv, e_min[0], e_min[1], e_max[0], e_max[1]))
    return out


def acad_seq(L, tol=1e-6, end_to_end=False, ignore=()):
    props = encode_props(L, ignore).tolist()
    b = angle_buckets(L).tolist()
    groups = defaultdict(list)
    for i in range(len(L)):
        groups[(props[i], b[i])].append((i, L.x0[i], L.y0[i], L.x1[i], L.y1[i]))
    res = [r for (p, bb), rows in groups.items() for r in acad_group(rows, bb, tol, end_to_end)]
    res.sort()
    return res


def _acad_rows(task):
    """Trabajador: recibe sólo las filas de su partición (sirve igual con fork o spawn)."""
    tol, e2e, rows = task
    groups = defaultdict(list)
    for p, bb, i, x0, y0, x1, y1 in rows:
        groups[(p, bb)].append((i, x0, y0, x1, y1))
    flat = []
    for (p, bb), g in groups.items():
        for r in acad_group(g, bb, tol, e2e):
            flat += r
    return flat


def acad_par(L, workers=4, tol=1e-6, end_to_end=False, ignore=(), timings=None, pool=None):
    """pool: un multiprocessing.Pool ya abierto para reutilizarlo entre llamadas (en Windows
    arrancar procesos cuesta ~0,5 s cada vez); si no se pasa, se crea uno."""
    import time
    import numpy as np
    t = time.perf_counter()
    props = encode_props(L, ignore)
    b = angle_buckets(L)
    nparts = workers * 4
    pid = ((b % _M) * 1000003 + props % _M) % _M % nparts
    order = np.argsort(pid, kind="stable")
    cuts = np.searchsorted(pid[order], np.arange(1, nparts))
    A = L.np
    tasks = []
    for idx in np.split(order, cuts):
        cols = [props[idx], b[idx], idx, A["x0"][idx], A["y0"][idx], A["x1"][idx], A["y1"][idx]]
        rows = list(zip(*(c.tolist() for c in cols)))
        tasks.append((tol, end_to_end, rows))
    tasks.sort(key=lambda tk: -len(tk[2]))
    t1 = time.perf_counter()
    own = pool is None
    if own:
        pool = mp.get_context("fork" if "fork" in mp.get_all_start_methods() else "spawn").Pool(workers)
    try:
        outs = pool.map(_acad_rows, tasks, chunksize=1)
    finally:
        if own:
            pool.close(); pool.join()
    t2 = time.perf_counter()
    flat = np.concatenate([np.asarray(f, dtype=np.int64) for f in outs]).reshape(-1, 5)
    res = flat[np.argsort(flat[:, 0])].tolist()
    if timings is not None:
        timings.update(partition=t1 - t, compute=t2 - t1, reassemble=time.perf_counter() - t2)
    return res


# ---------------------------------------------------------------- escribir / comparar
def endpoint(L, i, which):
    return (L.x0[i], L.y0[i]) if which == 0 else (L.x1[i], L.y1[i])


def result_lines(L, res):
    """res: filas (sobreviviente, i_min, extremo_min, i_max, extremo_max) ordenadas.
    Devuelve líneas finales (handle, capa, color, tipo, p0, p1) en orden de archivo."""
    out = []
    for surv, a, wa, b, wb in res:
        a, b = endpoint(L, a, wa), endpoint(L, b, wb)
        # conservar orientación del sobreviviente
        forward = ((L.x1[surv] - L.x0[surv]) * (b[0] - a[0])
                   + (L.y1[surv] - L.y0[surv]) * (b[1] - a[1])) >= 0
        p0, p1 = (a, b) if forward else (b, a)
        out.append((L.handle[surv], L.layer[surv], L.color[surv], L.linetype[surv], p0, p1))
    return out


def fingerprint(lines):
    h = hashlib.sha256()
    for r in lines:
        h.update(repr(r).encode())
    return h.hexdigest()


def write_dxf(path, layers, lines):
    import ezdxf
    doc = ezdxf.new("R2010")
    for name in layers:
        if name not in doc.layers:
            doc.layers.add(name)
    msp = doc.modelspace()
    for _h, layer, color, lt, p0, p1 in lines:
        msp.add_line(p0, p1, dxfattribs={"layer": layer, "color": color, "linetype": lt})
    doc.saveas(path)
