"""DXF para medir HATCH: rejilla de k x k celdas cerradas hechas con LINE (4 lados, sin repetir los compartidos)
y un POINT dentro de cada celda (el "punto interior" que se le da a HATCH).
Opcional: islas (un cuadrado pequeño dentro de algunas celdas) y diagonales (una línea que parte la celda en dos).
Sin dependencias: escribe DXF R12 a mano.

Uso:  python gen_hatch_dxf.py --k 50 --out h50.dxf [--islas 0.2] [--diagonales 0.2] [--seed 1]
Escribe además h50.puntos.txt (x,y por línea, para -HATCH nativo) y h50.esperado.txt (área esperada por punto).
"""
import argparse
import random

ap = argparse.ArgumentParser()
ap.add_argument("--k", type=int, default=50)
ap.add_argument("--size", type=float, default=10.0)
ap.add_argument("--islas", type=float, default=0.0, help="fracción de celdas con una isla cuadrada")
ap.add_argument("--diagonales", type=float, default=0.0, help="fracción de celdas partidas por una diagonal")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--out", required=True)
a = ap.parse_args()
k, s = a.k, a.size
rnd = random.Random(a.seed)

ents = []
def line(x0, y0, x1, y1, layer="CELDAS"):
    ents.append(f"0\nLINE\n8\n{layer}\n10\n{x0!r}\n20\n{y0!r}\n30\n0.0\n11\n{x1!r}\n21\n{y1!r}\n31\n0.0\n")
for j in range(k + 1):           # horizontales y verticales, un segmento por lado de celda
    for i in range(k):
        line(i * s, j * s, (i + 1) * s, j * s)
        line(j * s, i * s, j * s, (i + 1) * s)
pts, areas = [], []
for j in range(k):
    for i in range(k):
        x, y = i * s, j * s
        if rnd.random() < a.diagonales:          # diagonal de esquina a esquina: el punto queda en el triángulo inferior
            line(x, y, x + s, y + s, "DIAGONALES")
            pts.append((x + 0.75 * s, y + 0.25 * s)); areas.append(s * s / 2)
        elif rnd.random() < a.islas:             # isla cuadrada de lado s/4 centrada; el punto queda fuera de ella
            q0, q1 = x + 0.375 * s, x + 0.625 * s
            r0, r1 = y + 0.375 * s, y + 0.625 * s
            line(q0, r0, q1, r0, "ISLAS"); line(q1, r0, q1, r1, "ISLAS")
            line(q1, r1, q0, r1, "ISLAS"); line(q0, r1, q0, r0, "ISLAS")
            pts.append((x + 0.15 * s, y + 0.15 * s)); areas.append(s * s - (s / 4) ** 2)
        else:
            pts.append((x + 0.5 * s, y + 0.5 * s)); areas.append(s * s)
for x, y in pts:
    ents.append(f"0\nPOINT\n8\nPUNTOS\n10\n{x!r}\n20\n{y!r}\n30\n0.0\n")

with open(a.out, "w", newline="\r\n") as f:
    f.write("0\nSECTION\n2\nENTITIES\n" + "".join(ents) + "0\nENDSEC\n0\nEOF\n")
base = a.out.rsplit(".", 1)[0]
with open(base + ".puntos.txt", "w", newline="\r\n") as f:
    f.write("".join(f"{x!r},{y!r}\n" for x, y in pts))
with open(base + ".esperado.txt", "w", newline="\r\n") as f:
    f.write("".join(f"{ar!r}\n" for ar in areas))
nl = sum(1 for e in ents if e.startswith("0\nLINE"))
print(f"{a.out}: {k*k} celdas, {nl} lineas, {len(pts)} puntos")
