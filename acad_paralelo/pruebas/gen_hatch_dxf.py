"""DXF para medir HATCH: rejilla de k x k celdas cerradas hechas con LINE (4 lados, sin repetir los compartidos)
y un POINT en el centro de cada celda (el "punto interior" que se le da a HATCH).
Sin dependencias: escribe DXF R12 a mano.

Uso:  python gen_hatch_dxf.py --k 50 --out h50.dxf
Escribe además h50.puntos.txt (x,y por línea) para el script de -HATCH nativo.
"""
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--k", type=int, default=50)
ap.add_argument("--size", type=float, default=10.0)
ap.add_argument("--out", required=True)
a = ap.parse_args()
k, s = a.k, a.size

ents = []
def line(x0, y0, x1, y1, layer="CELDAS"):
    ents.append(f"0\nLINE\n8\n{layer}\n10\n{x0}\n20\n{y0}\n30\n0.0\n11\n{x1}\n21\n{y1}\n31\n0.0\n")
for j in range(k + 1):           # horizontales y verticales, un segmento por lado de celda
    for i in range(k):
        line(i * s, j * s, (i + 1) * s, j * s)
        line(j * s, i * s, j * s, (i + 1) * s)
pts = [((i + 0.5) * s, (j + 0.5) * s) for j in range(k) for i in range(k)]
for x, y in pts:
    ents.append(f"0\nPOINT\n8\nPUNTOS\n10\n{x}\n20\n{y}\n30\n0.0\n")

with open(a.out, "w", newline="\r\n") as f:
    f.write("0\nSECTION\n2\nENTITIES\n" + "".join(ents) + "0\nENDSEC\n0\nEOF\n")
with open(a.out.rsplit(".", 1)[0] + ".puntos.txt", "w", newline="\r\n") as f:
    f.write("".join(f"{x},{y}\n" for x, y in pts))
print(f"{a.out}: {k*k} celdas, {2*k*(k+1)} lineas, {len(pts)} puntos")
