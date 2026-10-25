# Paquete instalable para AutoCAD

Convierte un plugin de `acad_paralelo/` en algo que cualquiera instala con doble clic y que AutoCAD carga solo
al arrancar, sin `NETLOAD`. Usa el **cargador automático** de AutoCAD: una carpeta `.bundle` con un
`PackageContents.xml` que dice qué DLL cargar, en qué versión de AutoCAD y qué comandos trae.

Primer paquete: **POverkill** (`POVERKILL`, `POVERKILLBENCH`).

## Armar

```bash
cd paquete
python armar_paquete.py poverkill                                   # usa ../acad_paralelo/dist/AcadParalelo.dll
python armar_paquete.py poverkill --dll otra\AcadParalelo.dll --version 0.2.0
```

Sale `dist/POverkill-<versión>.zip` con:

```
POverkill-0.1.0/
  POverkill.bundle/
    PackageContents.xml        AutoCAD 2027 (R26.0) Win64, carga al arrancar, lista de comandos
    Contents/AcadParalelo.dll
    Contents/LEEME.txt
  instalar.bat / instalar.ps1  copia el .bundle a ApplicationPlugins y quita la marca "descargado de Internet"
  desinstalar.bat
  LEEME.txt                    instrucciones para el usuario final
```

Otro comando nuevo (PJOIN, PHATCH...) es una entrada más en `PAQUETES` dentro de `armar_paquete.py`: nombre,
comandos, descripción, LEEME y dos códigos GUID nuevos. `UpgradeCode` no se cambia nunca para un mismo plugin;
para sacar una versión nueva basta con `--version`.

## Instalar

Doble clic en `instalar.bat`. Opciones:

| Cómo | Dónde queda | Notas |
|---|---|---|
| `instalar.bat` | `%APPDATA%\Autodesk\ApplicationPlugins` | Sólo tu usuario, sin administrador. La primera vez AutoCAD pregunta si cargar la DLL (no está firmada): "Cargar siempre". |
| `instalar.bat -TodosLosUsuarios` | `%ProgramFiles%\Autodesk\ApplicationPlugins` | Pide administrador. Es ruta de confianza: AutoCAD no pregunta. |
| `desinstalar.bat` | quita las dos | |

Sólo carga en AutoCAD 2027 (R26.x): la DLL está compilada para .NET 10, y AutoCAD 2025/2026 usan .NET 8.
No funciona en AutoCAD LT (no admite plugins .NET).

## Compartirlo de forma legal

**Lo que ya está bien.** Hacer y repartir plugins con la API .NET de AutoCAD es lo previsto por Autodesk; cada
persona lo usa con su propia licencia de AutoCAD. El paquete sólo lleva nuestra DLL: las de AutoCAD
(`AcCoreMgd`, `AcDbMgd`) se usan para compilar pero no se copian (`ExcludeAssets="runtime"`), así que no se
redistribuye nada de Autodesk.

**Lo que falta decidir:**

1. **Licencia del código.** El repo no tiene `LICENSE`, y sin ella nadie puede legalmente copiar ni repartir el
   código o la DLL, aunque el repo sea público. Opciones típicas: MIT (cualquiera lo usa, modifica y reparte,
   sin garantía), GPL (igual, pero quien lo modifique debe publicar sus cambios), o propietaria (uso gratis o de
   pago, sin derecho a modificar ni revender).
2. **Nombre.** "AutoCAD" es marca de Autodesk: el producto no debe llamarse "AutoCAD algo"; "para AutoCAD" sí
   se puede. Por eso el paquete se llama POverkill.
3. **Firma digital (opcional, recomendable para otros usuarios).** Con un certificado de firma de código
   (de una autoridad como Sectigo o DigiCert, o Azure Trusted Signing) se firma la DLL con `signtool`. AutoCAD
   muestra entonces el nombre del autor y el usuario puede confiar en él una vez para siempre. Sin firma
   funciona igual, sólo con el aviso de la primera vez.

**Dónde publicarlo:**

- **GitHub Releases** (lo más simple): subir el `.zip` a una versión del repo. Gratis e inmediato.
- **Autodesk App Store** (apps.autodesk.com): se crea una cuenta de publicador y se sube este mismo `.bundle`;
  Autodesk lo revisa, lo prueba y lo ofrece con su propio instalador, gratis o de pago. Pide además icono,
  descripción, página de ayuda y una política de soporte. Es el canal que la gente de AutoCAD ya conoce.

Ninguna de las dos exige cambiar el código.

## Pendiente

- Menú o cinta con los comandos: la DLL sólo usa la parte de AutoCAD sin interfaz (para correr también en
  `accoreconsole`), así que la cinta iría en una segunda DLL pequeña dentro del mismo `.bundle`.
- La DLL actual también trae los comandos de medición `PLEERMEDIR` y `PHATCHMEDIR`; funcionan pero no se anuncian.
