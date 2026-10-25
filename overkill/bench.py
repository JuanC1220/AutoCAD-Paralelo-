"""Verifica y mide OVERKILL secuencial vs paralelo.

  python bench.py check  archivo.dxf            # conteos esperados + igualdad seq/par
  python bench.py time   archivo.dxf [reps]     # tiempos por fase con 1, 2 y 4 trabajadores
  python bench.py write  archivo.dxf salida.dxf [workers]
  python bench.py acad   archivo.dxf            # modo AutoCAD: conteos + igualdad seq/par
"""
import json
import statistics
import sys
import time

import overkill_core as ok


def check(path):
    L = ok.read_lines(path)
    exp = json.load(open(path + ".json"))
    assert len(L) == exp["n_lines"], (len(L), exp["n_lines"])
    cases = [("default", {}, exp["expected_lines_default"]),
             ("end_to_end", {"end_to_end": True}, exp["expected_lines_endtoend"]),
             ("ignore_layer", {"ignore": ("layer",)}, exp["expected_lines_ignore_layer"])]
    ok_all = True
    for name, kw, want in cases:
        ref = ok.result_lines(L, ok.overkill_seq(L, **kw))
        fp = ok.fingerprint(ref)
        line = f"{name:13s} esperado={want:8d} secuencial={len(ref):8d}"
        good = len(ref) == want
        for w in (1, 2, 4):
            par = ok.result_lines(L, ok.overkill_par(L, workers=w, **kw))
            same = ok.fingerprint(par) == fp
            good &= same
            line += f"  par{w}={'IGUAL' if same else 'DISTINTO'}"
        ok_all &= good
        print(line, "OK" if good else "FALLO")
    return ok_all


def timing(path, reps=3):
    t = time.perf_counter()
    L = ok.read_lines(path)
    t_read = time.perf_counter() - t
    row = {"file": path, "n": len(L), "read": round(t_read, 3)}
    best = lambda f: min(_t(f) for _ in range(reps))
    row["seq"] = round(best(lambda: ok.overkill_seq(L)), 3)
    fp = ok.fingerprint(ok.result_lines(L, ok.overkill_seq(L)))
    for w in (1, 2, 4):
        runs = []
        for _ in range(reps):
            tm = {}
            t = time.perf_counter()
            res = ok.overkill_par(L, workers=w, timings=tm)
            tm["total"] = time.perf_counter() - t
            runs.append(tm)
        assert ok.fingerprint(ok.result_lines(L, res)) == fp
        b = min(runs, key=lambda r: r["total"])
        row[f"par{w}"] = {k: round(v, 3) for k, v in b.items()}
    print(json.dumps(row))
    return row


def _t(f):
    t = time.perf_counter()
    f()
    return time.perf_counter() - t


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "check":
        sys.exit(0 if check(path) else 1)
    elif cmd == "time":
        timing(path, int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    elif cmd == "acad":
        L = ok.read_lines(path)
        for name, kw in [("default", {}), ("end_to_end", {"end_to_end": True}),
                         ("ignore_layer", {"ignore": ("layer",)})]:
            fp = ok.fingerprint(ok.result_lines(L, ok.acad_seq(L, **kw)))
            n = len(ok.acad_seq(L, **kw))
            same = all(ok.fingerprint(ok.result_lines(L, ok.acad_par(L, workers=w, **kw))) == fp
                       for w in (1, 2, 4))
            print(f"{name:13s} lineas={n:8d}  paralelo 1/2/4={'IGUAL' if same else 'DISTINTO'}")
    elif cmd == "write":
        L = ok.read_lines(path)
        w = int(sys.argv[4]) if len(sys.argv) > 4 else 4
        lines = ok.result_lines(L, ok.overkill_par(L, workers=w))
        ok.write_dxf(sys.argv[3], L.layers, lines)
        print(f"{len(L)} -> {len(lines)} líneas, escrito {sys.argv[3]}")
