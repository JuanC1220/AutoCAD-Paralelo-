"""Compara el resultado de un OVERKILL con los conteos esperados del dibujo extremo.

Fuentes de conteo (una):
  --dxf RES.dxf        cuenta entidades por capa en un DXF ya procesado (AutoCAD, POVERKILL...)
  --csv RES.csv        CSV capa;cantidad (lo escribe contar_capas.lsp dentro de AutoCAD)
  --motor exacto|acad  corre overkill_core (sólo LINE) sobre el DXF original y cuenta

Uso:  python verificar_extremo.py extremo_3M.dxf.json --motor acad [--e2e]
      python verificar_extremo.py extremo_3M.dxf.json --csv res_e2e.csv --e2e
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def count_dxf(path, types=("LINE", "ARC", "CIRCLE", "LWPOLYLINE")):
    c = Counter()
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = f.read().split("\n")
    sec, typ = None, None
    for i in range(0, len(rows) - 1, 2):
        code, val = rows[i].strip(), rows[i + 1].strip()
        if code == "0":
            typ = val if sec == "ENTITIES" and val in types else None
            if val == "ENDSEC":
                sec = None
        elif code == "2" and rows[i - 1].strip() == "SECTION":
            sec = val
        elif code == "8" and typ:
            c[val] += 1
            typ = None
    return c


def count_engine(src, motor, e2e, workers):
    import overkill_core as ok
    t = time.perf_counter()
    L = ok.read_lines(src)
    t1 = time.perf_counter()
    if motor == "exacto":
        res = ok.overkill_seq(L, end_to_end=e2e)
    else:
        res = ok.acad_par(L, workers=workers, end_to_end=e2e) if workers > 1 else ok.acad_seq(L, end_to_end=e2e)
    t2 = time.perf_counter()
    print(f"motor {motor}: {len(L):,} LINE leídas en {t1 - t:.1f} s, cálculo {t2 - t1:.1f} s, quedan {len(res):,}")
    c = Counter(L.layer[r[0]] for r in res)
    return c, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dxf"); g.add_argument("--csv"); g.add_argument("--motor", choices=["exacto", "acad"])
    ap.add_argument("--e2e", action="store_true", help="se usó 'combinar extremo a extremo'")
    ap.add_argument("--hilos", type=int, default=1)
    a = ap.parse_args()
    exp = json.load(open(a.json, encoding="utf-8"))
    only_lines = False
    if a.dxf:
        got = count_dxf(a.dxf)
    elif a.csv:
        got = Counter()
        for ln in open(a.csv, encoding="utf-8", errors="replace"):
            if ";" in ln:
                k, v = ln.strip().rsplit(";", 1)
                got[k] += int(v)
    else:
        src = os.path.join(os.path.dirname(os.path.abspath(a.json)), os.path.basename(exp["archivo"]))
        got, only_lines = count_engine(src, a.motor, a.e2e, a.hilos)
    key = "esperado_con_e2e" if a.e2e else "esperado_sin_e2e"
    print(f"\n{'capa':34} {'clase':9} {'entrada':>9} {'esperado':>9} {'obtenido':>9}  dif")
    tot = Counter()
    for lay, info in exp["capas"].items():
        e = info[key]
        if only_lines:          # el motor sólo ve LINE: lo demás queda igual
            other = sum(v for t, v in info["por_tipo"].items() if t != "LINE")
            got[lay] += other
        g_ = got.get(lay, 0)
        d = g_ - e
        mark = "ok" if d == 0 else f"{d:+,}"
        print(f"{lay:34} {info['clase']:9} {info['entrada']:>9,} {e:>9,} {g_:>9,}  {mark}")
        tot[info["clase"], "e"] += e; tot[info["clase"], "g"] += g_
    print()
    for cl in ("seguro", "nuevo", "frontera"):
        e, g_ = tot[cl, "e"], tot[cl, "g"]
        print(f"total {cl:9}: esperado {e:,}  obtenido {g_:,}  dif {g_ - e:+,}")


if __name__ == "__main__":
    main()
