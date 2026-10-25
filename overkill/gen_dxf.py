"""Generador de DXF sintético para probar OVERKILL (secuencial vs paralelo).

Crea N segmentos "base" únicos sobre rectas portadoras y les "planta" defectos
conocidos, de modo que el resultado correcto se sabe de antemano:

  dup        copia exacta                      -> se elimina
  rev        copia invertida (p1<->p0)         -> se elimina
  jitter     copia movida < tol/2 en cada coord -> se elimina
  contained  sub-segmento dentro del base       -> se elimina
  overlap    colineal que solapa parcialmente   -> se fusiona con el base
  endtoend   colineal que empieza donde acaba   -> se fusiona sólo con la opción
  layer      copia exacta en otra capa          -> se conserva (salvo ignorar capa)
  nearpar    paralela a 1000*tol de distancia   -> se conserva (no es colineal)

Todas las coordenadas base están en una rejilla de 1e-3 unidades y las rectas
usan vectores de dirección enteros, así la colinealidad es exacta.

Uso:  python gen_dxf.py --n 100000 --out sintetico_100k.dxf [--seed 1]
Genera además <out>.json con los conteos esperados.
"""
import argparse
import json
import math
import random

import ezdxf

GRID = 1e-3          # unidad de la rejilla base
TOL = 1e-6           # tolerancia por defecto de OVERKILL
PLANTS = ["dup", "rev", "jitter", "contained", "overlap", "endtoend", "layer", "nearpar"]


def generate(n_base, seed=1, n_layers=8, plant_rate=0.5, extent=10000.0):
    rnd = random.Random(seed)
    span = int(extent / GRID)
    layers = [f"CAPA_{i}" for i in range(n_layers)]
    lines = []          # (layer, color, (x0,y0), (x1,y1))
    counts = {p: 0 for p in PLANTS}

    def P(ix, iy):
        return (ix * GRID, iy * GRID)

    used = set()        # rectas ya usadas: evita fusiones no planeadas
    made = 0
    while made < n_base:
        # recta portadora: punto de origen entero + dirección entera pequeña
        if rnd.random() < 0.4:
            a, b = rnd.choice([(1, 0), (0, 1)])
        else:
            a, b = rnd.randint(-50, 50), rnd.randint(1, 50)
        ox, oy = rnd.randrange(span), rnd.randrange(span)
        g = math.gcd(a, b)
        key = (a // g, b // g, (a * oy - b * ox) // g)
        if key in used:
            continue
        used.add(key)
        layer = rnd.choice(layers)
        color = rnd.choice([256, 1, 3, 5])        # 256 = PorCapa
        s = 0
        for _ in range(rnd.randint(1, 6)):        # segmentos base en esta recta
            if made >= n_base:
                break
            s += rnd.randint(2000, 20000)           # hueco amplio entre bases
            L = rnd.randint(1000, 20000)
            s0, s1 = s, s + L
            s = s1
            base = (P(ox + a * s0, oy + b * s0), P(ox + a * s1, oy + b * s1))
            lines.append((layer, color, *base))
            made += 1
            if rnd.random() >= plant_rate:
                continue
            kind = rnd.choice(PLANTS)
            counts[kind] += 1
            (x0, y0), (x1, y1) = base
            if kind == "dup":
                lines.append((layer, color, base[0], base[1]))
            elif kind == "rev":
                lines.append((layer, color, base[1], base[0]))
            elif kind == "jitter":
                j = lambda v: v + rnd.uniform(-0.3, 0.3) * TOL
                lines.append((layer, color, (j(x0), j(y0)), (j(x1), j(y1))))
            elif kind == "contained":
                c0 = rnd.randint(s0 + 1, s0 + L // 2)
                c1 = rnd.randint(c0 + 1, s1 - 1)
                lines.append((layer, color, P(ox + a * c0, oy + b * c0), P(ox + a * c1, oy + b * c1)))
            elif kind == "overlap":
                c0 = rnd.randint(s0 + 1, s1 - 1)
                c1 = s1 + rnd.randint(1, 1000)      # < hueco mínimo
                s = c1
                lines.append((layer, color, P(ox + a * c0, oy + b * c0), P(ox + a * c1, oy + b * c1)))
            elif kind == "endtoend":
                c1 = s1 + rnd.randint(1, 1000)
                s = c1
                lines.append((layer, color, P(ox + a * s1, oy + b * s1), P(ox + a * c1, oy + b * c1)))
            elif kind == "layer":
                other = layers[(layers.index(layer) + 1) % n_layers]
                lines.append((other, color, base[0], base[1]))
            elif kind == "nearpar":
                # desplazar en la normal ~1000*tol (= 1 celda de rejilla)
                dx, dy = (0, 1) if b == 0 else (1, 0)
                lines.append((layer, color, P(ox + a * s0 + dx, oy + b * s0 + dy),
                              P(ox + a * s1 + dx, oy + b * s1 + dy)))
    rnd.shuffle(lines)    # el orden en el archivo no debe importar
    keep = n_base + counts["layer"] + counts["nearpar"]
    expected = {
        "n_base": n_base, "n_lines": len(lines), "plants": counts,
        "expected_lines_default": keep + counts["endtoend"],   # sin fusionar extremo a extremo
        "expected_lines_endtoend": keep,
        "expected_lines_ignore_layer": n_base + counts["nearpar"] + counts["endtoend"],
    }
    return layers, lines, expected


def write_dxf(path, layers, lines):
    doc = ezdxf.new("R2010")
    for name in layers:
        doc.layers.add(name)
    msp = doc.modelspace()
    for layer, color, p0, p1 in lines:
        msp.add_line(p0, p1, dxfattribs={"layer": layer, "color": color})
    doc.saveas(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000, help="segmentos base únicos")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--plant-rate", type=float, default=0.5)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    layers, lines, expected = generate(a.n, a.seed, plant_rate=a.plant_rate)
    write_dxf(a.out, layers, lines)
    with open(a.out + ".json", "w") as f:
        json.dump(expected, f, indent=2)
    print(json.dumps(expected, indent=2))
