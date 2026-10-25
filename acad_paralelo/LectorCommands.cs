// PLEERMEDIR: compara formas de leer las LINE del espacio actual para elegir la más rápida.
// No modifica el dibujo. Cada pasada sólo abre y toca lo indicado, y se informa en segundos.
using System;
using System.Collections.Generic;
using System.Diagnostics;
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
                sw.Restart();
                for (int s0 = 0; s0 < ids.Length; s0 += bloque)
                {
                    int cnt = Math.Min(bloque, ids.Length - s0);
                    using var tr = openClose ? db.TransactionManager.StartOpenCloseTransaction() : db.TransactionManager.StartTransaction();
                    for (int j = 0; j < cnt; j++) suma += ((Line)tr.GetObject(ids[s0 + j], OpenMode.ForRead)).StartPoint.X;
                    tr.Commit();
                }
                res.Add($"{nombre}: {T():F3} s");
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
            res.Add($"lector completo (ids y valores): {T():F3} s (abrir {d.TAbrir:F3}, propiedades {d.TPropiedades:F3}), {d.Grupos} combinaciones");
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

            Informe.Escribir($"\nPLEERMEDIR ({ids.Length} líneas, control {suma + h:G3}):\n  " + string.Join("\n  ", res) + "\n");
        }
    }
}
