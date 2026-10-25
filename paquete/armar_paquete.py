"""Arma el paquete instalable de un plugin para el cargador automático de AutoCAD (carpeta .bundle).

    python armar_paquete.py poverkill                      # usa ../acad_paralelo/dist/AcadParalelo.dll
    python armar_paquete.py poverkill --dll ruta\\AcadParalelo.dll --version 0.2.0

Deja en dist/ la carpeta POverkill-<versión>/ y su .zip, listo para compartir:
    POverkill.bundle/PackageContents.xml   lo que lee AutoCAD: versión, AutoCAD compatible, DLL y comandos
    POverkill.bundle/Contents/             la DLL y el LEEME
    instalar.bat / desinstalar.bat         copian o quitan el .bundle en ApplicationPlugins
    LEEME.txt, LICENSE.txt

Para otro comando: añadir una entrada a PAQUETES (nombre, comandos, códigos fijos) y armarlo igual.
"""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape

AQUI = Path(__file__).resolve().parent
REPO = "https://github.com/JuanC1220/AutoCAD-Paralelo-"

# AutoCAD 2027 = R26.0 sobre .NET 10. La DLL compilada para .NET 10 no carga en 2025/2026 (.NET 8).
SERIE_MIN, SERIE_MAX = "R26.0", "R26.9"

# UpgradeCode no cambia nunca para un plugin: así AutoCAD y la App Store saben que una versión nueva
# reemplaza a la anterior. ProductCode es el de esta línea de versiones.
PAQUETES = {
    "poverkill": dict(
        nombre="POverkill",
        descripcion="OVERKILL en paralelo para LINE: mismo resultado que con un solo hilo, varias veces más rápido en dibujos grandes.",
        dll="AcadParalelo.dll",
        comandos=["POVERKILL", "POVERKILLBENCH"],
        product_code="{DFA83A3E-E293-4140-BAF0-B9A80DB54167}",
        upgrade_code="{A2B09AE6-5B54-4AA1-BAA1-58E526EEB381}",
        leeme="""\
POverkill: OVERKILL en paralelo para AutoCAD 2027
=================================================

Instalar
--------
1. Cierra AutoCAD.
2. Doble clic en instalar.bat (sólo para tu usuario, no pide administrador).
   Para todos los usuarios del PC: abre una consola aquí y escribe  instalar.bat -TodosLosUsuarios
3. Abre AutoCAD 2027. Si pregunta si cargar AcadParalelo.dll, elige "Cargar siempre".

Para quitarlo: desinstalar.bat.

Usar
----
POVERKILL        Selecciona las líneas (o Enter para todo el dibujo), ajusta opciones y Enter.
                 Opciones: Hilos, Tolerancia, Capa (ignorar capa), Extremo (unir extremo con extremo).
                 Borra líneas duplicadas o contenidas en otra y une las solapadas, como OVERKILL.
                 Todo queda en un solo paso: U lo deshace.
POVERKILLBENCH   No cambia el dibujo: mide el cálculo con 1, 2, 4... hilos y comprueba que el
                 resultado sea idéntico con cualquier número de hilos.

Los tiempos salen en la línea de comandos y se añaden a <dibujo>.acadparalelo.txt.

Qué hace y qué no
-----------------
- Sólo trabaja con LINE (no polilíneas, arcos ni bloques). Omite capas bloqueadas y líneas fuera del plano XY.
- Compara las mismas propiedades que OVERKILL por defecto: capa, color, tipo de línea, escala, grosor, etc.
- En dibujos medidos queda a menos de 0,2 % del OVERKILL de AutoCAD (AutoCAD deja algunas líneas más).
  Revisa el resultado antes de guardar sobre un plano importante.

Requisitos: AutoCAD 2027 para Windows (no AutoCAD LT, que no admite plugins .NET).
Gratis para uso no comercial (licencia PolyForm Noncommercial 1.0.0), sin garantía. Código y versiones: """ + REPO + """
""",
    ),
}


def package_contents(p, version):
    req = f'<RuntimeRequirements OS="Win64" Platform="AutoCAD*" SeriesMin="{SERIE_MIN}" SeriesMax="{SERIE_MAX}" />'
    cmds = "\n".join(f'          <Command Local="{c}" Global="{c}" />' for c in p["comandos"])
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="AutoCAD" ProductType="Application"
    Name="{p['nombre']}" AppVersion="{version}" FriendlyVersion="{version}"
    Description={quoteattr(p['descripcion'])}
    Author="juan C" SupportedLocales="Esp|Enu" HelpFile="./Contents/LEEME.txt"
    ProductCode="{p['product_code']}" UpgradeCode="{p['upgrade_code']}">
  <CompanyDetails Name="juan C" Url="{REPO}" />
  {req}
  <Components Description={quoteattr(escape(p['nombre']))}>
    {req}
    <ComponentEntry AppName="{p['nombre']}" Version="{version}" ModuleName="./Contents/{p['dll']}"
        AppDescription={quoteattr(p['descripcion'])} LoadOnAutoCADStartup="True">
      <Commands GroupName="{p['nombre'].upper()}">
{cmds}
      </Commands>
    </ComponentEntry>
  </Components>
</ApplicationPackage>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin", choices=sorted(PAQUETES))
    ap.add_argument("--dll", type=Path, default=AQUI.parent / "acad_paralelo" / "dist" / "AcadParalelo.dll")
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--out", type=Path, default=AQUI / "dist")
    a = ap.parse_args()

    p = PAQUETES[a.plugin]
    if not a.dll.is_file():
        sys.exit(f"No encuentro la DLL: {a.dll}  (compílala con 'dotnet build -c Release' en acad_paralelo/ o pasa --dll)")

    raiz = a.out / f"{p['nombre']}-{a.version}"
    if raiz.exists():
        shutil.rmtree(raiz)
    cont = raiz / f"{p['nombre']}.bundle" / "Contents"
    cont.mkdir(parents=True)

    shutil.copy2(a.dll, cont / p["dll"])
    leeme = p["leeme"].replace("\n", "\r\n")             # el Bloc de notas antiguo necesita CRLF
    (cont / "LEEME.txt").write_text(leeme, encoding="utf-8-sig")
    (raiz / "LEEME.txt").write_text(leeme, encoding="utf-8-sig")
    (cont.parent / "PackageContents.xml").write_text(package_contents(p, a.version), encoding="utf-8")
    for f in (AQUI / "plantilla").iterdir():
        shutil.copy2(f, raiz / f.name)
    shutil.copy2(AQUI.parent / "LICENSE", raiz / "LICENSE.txt")

    zpath = raiz.parent / (raiz.name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(raiz.rglob("*")):
            z.write(f, f.relative_to(a.out))
    print(f"Listo: {zpath}")
    for f in sorted(raiz.rglob("*")):
        if f.is_file():
            print("  ", f.relative_to(a.out))


if __name__ == "__main__":
    main()
