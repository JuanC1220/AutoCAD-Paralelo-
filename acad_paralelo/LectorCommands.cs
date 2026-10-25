// PLEERMEDIR: compara formas de leer las LINE del espacio actual para elegir la más rápida.
// No modifica el dibujo. Cada pasada sólo abre y toca lo indicado, y se informa en segundos.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AcadParalelo.LectorCommands))]

namespace AcadParalelo
{
    public class LectorCommands
    {
        [CommandMethod("PLEERMEDIR", CommandFlags.Modal)]
        public void PleerMedir()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor; var db = doc.Database;
            var sw = Stopwatch.StartNew();
            double T() { double t = sw.Elapsed.TotalSeconds; sw.Restart(); return t; }
            var res = new List<string>();

            // 1) obtener los ids
            sw.Restart();
            var psr = ed.SelectAll(new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "LINE") }));
            var ids = psr.Status == PromptStatus.OK ? psr.Value.GetObjectIds() : new ObjectId[0];
            res.Add($"seleccionar todo (filtro LINE): {T():F3} s, {ids.Length} líneas");
            var lineClass = RXObject.GetClass(typeof(Line));
            int cuenta = 0;
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())
            {
                var space = (BlockTableRecord)tr.GetObject(db.CurrentSpaceId, OpenMode.ForRead);
                foreach (ObjectId id in space) if (id.ObjectClass == lineClass) cuenta++;
                tr.Commit();
            }
            res.Add($"recorrer espacio actual sin abrir: {T():F3} s, {cuenta} líneas");
            if (ids.Length == 0) { Informe.Escribir("\nPLEERMEDIR: no hay LINE\n"); return; }

            double suma = 0;
            void Abrir(string nombre, int bloque, bool openClose)
            {
                int g2 = GC.CollectionCount(2);
                sw.Restart();
                for (int s0 = 0; s0 < ids.Length; s0 += bloque)
                {
                    int cnt = Math.Min(bloque, ids.Length - s0);
                    using var tr = openClose ? db.TransactionManager.StartOpenCloseTransaction() : db.TransactionManager.StartTransaction();
                    for (int j = 0; j < cnt; j++) suma += ((Line)tr.GetObject(ids[s0 + j], OpenMode.ForRead)).StartPoint.X;
                    tr.Commit();
                }
                res.Add($"{nombre}: {T():F3} s (recolecciones GC gen2 {GC.CollectionCount(2) - g2})");
            }

            // 2) abrir (sólo StartPoint): la primera pasada calienta la caché de AutoCAD
            Abrir("calentar (abrir/cerrar, bloques de 20000)", 20000, true);
            Abrir("abrir/cerrar, bloques de 5000", 5000, true);
            Abrir("abrir/cerrar, bloques de 20000", 20000, true);
            Abrir("abrir/cerrar, bloques de 100000", 100000, true);
            Abrir("transacción normal, bloques de 20000", 20000, false);
            sw.Restart();
            foreach (var id in ids)
            {
#pragma warning disable 618
                using var ln = (Line)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                suma += ln.StartPoint.X;
            }
            res.Add($"ObjectId.Open/cerrar una a una: {T():F3} s");
            Abrir("abrir/cerrar, todo en una transacción", ids.Length, true);

            // 3) costo de las propiedades (bloques de 20000)
            sw.Restart();
            var d = Lector.LeerLineas(db, ids, false);
            res.Add($"lector completo (uno a uno, ids y valores): {T():F3} s, {d.Grupos} combinaciones");
            sw.Restart();
            long h = 0;
            for (int s0 = 0; s0 < ids.Length; s0 += 20000)
            {
                int cnt = Math.Min(20000, ids.Length - s0);
                using var tr = db.TransactionManager.StartOpenCloseTransaction();
                for (int j = 0; j < cnt; j++)
                {
                    var ln = (Line)tr.GetObject(ids[s0 + j], OpenMode.ForRead);
                    h += ln.Layer.Length + ln.Linetype.Length + ln.Color.ToString().Length + ln.Transparency.ToString().Length;
                }
                tr.Commit();
            }
            res.Add($"propiedades como texto (versión 1): {T():F3} s");

            // 4) sin abrir objetos: AutoCAD escribe el dibujo como DXF y lo leemos como texto (handle -> ObjectId)
            string tmp = Path.Combine(Path.GetTempPath(), $"acadparalelo_{Guid.NewGuid():N}.dxf");
            try
            {
                sw.Restart();
                db.DxfOut(tmp, 16, DwgVersion.Current);
                res.Add($"DXFOUT a archivo temporal: {T():F3} s, {new FileInfo(tmp).Length / 1e6:F0} MB");
                var handles = new List<long>(ids.Length);
                string sec = null; bool inLine = false; string prev = null; int lineas = 0;
                foreach (var raw in File.ReadLines(tmp))
                {
                    if (prev == null) { prev = raw; continue; }
                    string code = prev.Trim(), val = raw.Trim(); prev = null;
                    if (code == "0")
                    {
                        inLine = sec == "ENTITIES" && val == "LINE";
                        if (inLine) lineas++;
                        if (val == "ENDSEC") sec = null;
                    }
                    else if (code == "2" && sec == null) sec = val;
                    else if (inLine && code == "5") handles.Add(Convert.ToInt64(val, 16));
                    else if (inLine && (code == "10" || code == "20" || code == "11" || code == "21"))
                        suma += double.Parse(val, System.Globalization.CultureInfo.InvariantCulture);
                }
                res.Add($"leer el DXF como texto: {T():F3} s, {lineas} LINE");
                int ok = 0;
                foreach (var hh in handles) if (db.TryGetObjectId(new Handle(hh), out var oid) && oid.ObjectClass == lineClass) ok++;
                res.Add($"handle -> ObjectId: {T():F3} s, {ok} encontrados");
            }
            catch (System.Exception ex) { res.Add($"DXFOUT falló: {ex.Message}"); }
            finally { try { File.Delete(tmp); } catch (System.Exception) { } }

            Informe.Escribir($"\nPLEERMEDIR ({ids.Length} líneas, control {suma + h:G3}):\n  " + string.Join("\n  ", res) + "\n");
        }
    }
}
