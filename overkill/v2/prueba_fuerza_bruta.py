"""Prueba aleatoria: el motor v2 debe encontrar exactamente los mismos grupos que la fuerza
bruta O(n^2) (verificar todos los pares con la misma regla geométrica y unir).

Escenas pequeñas pero hostiles: líneas casi colineales con giros y desplazamientos alrededor
de la tolerancia, coordenadas enormes, piezas muy cortas, verticales, 3D, casi paralelas al
eje, ángulos cerca de 0 y de pi (donde el ángulo "da la vuelta").
Uso: python prueba_fuerza_bruta.py [escenas] [semilla]
"""
import math
import random
import sys

import numpy as np

import overkill_v2 as v2


def escena(rnd, n):
    D = v2.Dib()
    tol = 1e-6
    base = rnd.choice([(0, 0), (5e5, 4.5e6), (-3e7, 2e7), (1e3, 1e3)])
    lines = []
    while len(lines) < n:
        th = rnd.choice([0.0, PI_ * 0.5, PI_ - 1e-12, 1e-12, rnd.uniform(0, PI_), rnd.uniform(0, PI_)])
        ux, uy = math.cos(th), math.sin(th)
        ox, oy = base[0] + rnd.uniform(-50, 50), base[1] + rnd.uniform(-50, 50)
        z = rnd.choice([0.0, 0.0, 0.0, 7.0])
        for _ in range(rnd.randint(1, 8)):
            s0 = rnd.uniform(-20, 20)
            L = rnd.choice([rnd.uniform(1e-4, 1e-2), rnd.uniform(0.1, 30), rnd.uniform(0.1, 30)])
            s1 = s0 + L
            d = rnd.choice([0.0, 0.0, rnd.uniform(-2e-6, 2e-6), rnd.uniform(-1.05e-6, 1.05e-6)])
            rot = rnd.choice([0.0, 0.0, rnd.uniform(-3e-7, 3e-7), rnd.uniform(-1e-9, 1e-9)])
            c, s = math.cos(th + rot), math.sin(th + rot)
            nx, ny = -s, c
            p0 = (ox + c * s0 + nx * d, oy + s * s0 + ny * d)
            p1 = (ox + c * s1 + nx * d, oy + s * s1 + ny * d)
            if rnd.random() < .5:
                p0, p1 = p1, p0
            dz = rnd.choice([0, 0, 0, 0, 1e-7, 3.0])
            lines.append((p0[0], p0[1], z, p1[0], p1[1], z + dz))
            if rnd.random() < .05:                            # vertical pura
                lines.append((p0[0], p0[1], 0.0, p0[0], p0[1], 5.0))
            if rnd.random() < .05:                            # punto
                lines.append((p0[0], p0[1], z, p0[0], p0[1], z))
    for g in lines[:n]:
        D.tipo.append("LINE"); D.capa.append("0"); D.prop.append(("0",)); D.handle.append(""); D.geo.append(g)
    D.n = len(D.tipo)
    return D


PI_ = math.pi


def bruta(D, tol, e2e):
    G = np.array(D.geo, dtype=np.float64)
    X0, Y0, Z0, X1, Y1, Z1 = (G[:, k].copy() for k in range(6))
    L = np.sqrt((X1 - X0) ** 2 + (Y1 - Y0) ** 2 + (Z1 - Z0) ** 2)
    uf = v2.UF(D.n)
    for i in range(D.n):
        for j in range(i + 1, D.n):
            if L[i] <= tol and L[j] <= tol:
                ok = (X0[i] - X0[j]) ** 2 + (Y0[i] - Y0[j]) ** 2 + (Z0[i] - Z0[j]) ** 2 <= tol * tol
            elif L[i] <= tol or L[j] <= tol:
                ok = False
            else:
                ok = v2._pair_ok(i, j, X0, Y0, Z0, X1, Y1, Z1, L, tol, e2e)
            if ok:
                uf.union(i, j)
    return sorted(i for i in range(D.n) if uf.find(i) != i)


def main():
    n_esc = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rnd = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    fallos = 0
    for k in range(n_esc):
        D = escena(rnd, rnd.randint(20, 300))
        e2e = rnd.random() < .5
        _, borr = v2.lineas(D, list(range(D.n)), 1e-6, e2e)
        esperado = bruta(D, 1e-6, e2e)
        if sorted(borr) != esperado:
            fallos += 1
            print(f"escena {k}: motor borra {len(borr)}, fuerza bruta {len(esperado)}")
    print(f"{n_esc} escenas, {fallos} con diferencias")
    sys.exit(1 if fallos else 0)


if __name__ == "__main__":
    main()
