"""Genera DXF de prueba con "basura" que PURGE debe quitar: capas, tipos de línea, estilos de texto y de cota,
regapps y bloques sin usar (algunos anidados: necesitan varias pasadas). También lleva geometría usada que
PURGE no debe tocar. Escribe <nombre>.json con lo que debería quedar.

    python gen_basura_dxf.py --n 20 --out carpeta [--lineas 20000] [--basura 300]
"""
import argparse, json, os, random
import ezdxf


def uno(ruta, lineas, basura, rnd):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    usadas = [f"USADA_{i}" for i in range(10)]
    for c in usadas:
        doc.layers.add(c)
    for i in range(lineas):
        x, y = rnd.uniform(0, 1e4), rnd.uniform(0, 1e4)
        msp.add_line((x, y), (x + rnd.uniform(-50, 50), y + rnd.uniform(-50, 50)), dxfattribs={"layer": rnd.choice(usadas)})
    blk = doc.blocks.new("USADO")
    blk.add_circle((0, 0), 5)
    for i in range(50):
        msp.add_blockref("USADO", (rnd.uniform(0, 1e4), rnd.uniform(0, 1e4)), dxfattribs={"layer": usadas[0]})
    for i in range(basura):
        doc.layers.add(f"BASURA_{i}")
        doc.styles.add(f"TXT_BASURA_{i}", font="txt.shx")
        doc.appids.add(f"APP_BASURA_{i}")
    for i in range(basura // 10):
        doc.linetypes.add(f"LT_BASURA_{i}", pattern=[0.75, 0.5, -0.25], description="basura")
        doc.dimstyles.add(f"COTA_BASURA_{i}")
    # bloques sin usar; cada tercero lleva dentro otro bloque sin usar (anidado)
    for i in range(basura // 3):
        b = doc.blocks.new(f"BLQ_BASURA_{i}")
        for k in range(20):
            b.add_line((k, 0), (k, 10), dxfattribs={"layer": f"BASURA_{i}"})
        if i % 3 == 0:
            interno = doc.blocks.new(f"BLQ_INTERNO_{i}")
            interno.add_circle((0, 0), 1)
            b.add_blockref(f"BLQ_INTERNO_{i}", (0, 0))
    doc.saveas(ruta)
    esperado = {"capas_usadas": usadas + ["0"], "bloques_usados": ["USADO"], "lineas": lineas, "inserciones": 50,
                "capas_basura": basura, "bloques_basura": basura // 3 + len(range(0, basura // 3, 3))}
    with open(ruta + ".json", "w") as f:
        json.dump(esperado, f, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="prueba_lotes")
    ap.add_argument("--lineas", type=int, default=20000)
    ap.add_argument("--basura", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rnd = random.Random(a.seed)
    for i in range(a.n):
        # tamaños distintos para que el reparto no sea parejo
        uno(os.path.join(a.out, f"plano_{i:03d}.dxf"), int(a.lineas * rnd.uniform(0.2, 2.0)), a.basura, rnd)
        print(f"plano_{i:03d}.dxf")
