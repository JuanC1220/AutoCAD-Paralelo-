// Plugin de AutoCAD: OVERKILL paralelo sobre LINE con el núcleo de overkill_cs.
// Receta: leer (hilo principal, API de AutoCAD) -> copiar a columnas -> calcular en paralelo
// (sin tocar AutoCAD) -> reensamblar -> aplicar borrados/fusiones en una transacción (hilo principal).
// La API de AutoCAD no es segura entre hilos: sólo el cálculo corre en paralelo.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AcadParalelo.OverkillCommands))]

namespace AcadParalelo
{
    public class OverkillCommands
    {
        // ajustes de la sesión (no tocan los de OVERKILL de AutoCAD)
        static int sThreads = Environment.ProcessorCount;
        static double sTol = 1e-6;
        static bool sIgnoreLayer = false;
        static bool sE2e = true;

        sealed class Drawing
        {
            public ObjectId[] Ids;
            public double[] Z;
            public Overkill.Lines L;
            public long[] Props;
            public int Skipped;
        }

        // POVERKILL: selecciona, ajusta opciones y aplica
        [CommandMethod("POVERKILL", CommandFlags.Modal | CommandFlags.UsePickSet)]
        public void PoverKill()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor;
            var ids = SelectLines(ed);
            if (ids == null) return;
            if (!AskOptions(ed)) return;

            var sw = Stopwatch.StartNew();
            var d = ReadLines(doc.Database, ids, sIgnoreLayer);
            double tRead = sw.Elapsed.TotalSeconds;
            var tm = new Dictionary<string, double>();
            var res = Overkill.Run(d.L, d.Props, sTol, sE2e, sThreads, tm);
            double tComp = sw.Elapsed.TotalSeconds;
            var (kept, erased, changed) = Apply(doc.Database, d, res);
            double tTotal = sw.Elapsed.TotalSeconds;

            Informe.Escribir($"\nPOVERKILL ({Settings()}): {d.L.N} líneas analizadas" +
                            (d.Skipped > 0 ? $", {d.Skipped} omitidas (capa bloqueada o no planas en XY)" : "") +
                            $".\n  Quedan {kept}: borradas {erased}, alargadas {changed}." +
                            $"\n  Tiempos: leer {tRead:F3} s, calcular {tComp - tRead:F3} s, aplicar {tTotal - tComp:F3} s, total {tTotal:F3} s.\n");
        }

        // POVERKILLBENCH: no modifica el dibujo; mide el cálculo con 1..N hilos y verifica que el resultado sea idéntico
        [CommandMethod("POVERKILLBENCH", CommandFlags.Modal | CommandFlags.UsePickSet)]
        public void PoverKillBench()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor;
            var ids = SelectLines(ed);
            if (ids == null) return;
            if (!AskOptions(ed)) return;

            var sw = Stopwatch.StartNew();
            var d = ReadLines(doc.Database, ids, sIgnoreLayer);
            Informe.Escribir($"\nPOVERKILLBENCH ({Settings()}): {d.L.N} líneas, leer {sw.Elapsed.TotalSeconds:F3} s, núcleos {Environment.ProcessorCount}\n");
            var ths = new List<int> { 1 };
            for (int t = 2; t < Environment.ProcessorCount; t *= 2) ths.Add(t);
            ths.Add(Environment.ProcessorCount);
            string refSha = null; double t1 = 0;
            foreach (var t in ths.Distinct())
            {
                double best = double.MaxValue; int[,] res = null;
                for (int r = 0; r < 4; r++)           // la primera pasada calienta el JIT
                {
                    var tm = new Dictionary<string, double>();
                    res = Overkill.Run(d.L, d.Props, sTol, sE2e, t, tm);
                    if (r > 0) best = Math.Min(best, tm["total"]);
                }
                var (count, sha) = Overkill.Fingerprint(res);
                refSha ??= sha;
                if (t == 1) t1 = best;
                Informe.Escribir($"  hilos={t,2} quedan={count} calcular={best:F3} s ({t1 / best:F1}x) {(sha == refSha ? "IGUAL" : "DISTINTO")} sha={sha[..16]}\n");
            }
        }

        static string Settings() =>
            $"hilos {sThreads}, tolerancia {sTol:G}, ignorar capa {(sIgnoreLayer ? "Sí" : "No")}, extremo con extremo {(sE2e ? "Sí" : "No")}";

        static ObjectId[] SelectLines(Editor ed)
        {
            var filter = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "LINE") });
            var pso = new PromptSelectionOptions { MessageForAdding = "\nSeleccione objetos (sólo se procesan LINE): " };
            var psr = ed.GetSelection(pso, filter);
            if (psr.Status != PromptStatus.OK) return null;
            return psr.Value.GetObjectIds();
        }

        static bool AskOptions(Editor ed)
        {
            while (true)
            {
                var pko = new PromptKeywordOptions($"\n{Settings()}\nOpción [Hilos/Tolerancia/Capa/Extremo/Hecho] <Hecho>: ", "Hilos Tolerancia Capa Extremo Hecho")
                { AllowNone = true };
                var r = ed.GetKeywords(pko);
                if (r.Status == PromptStatus.None || (r.Status == PromptStatus.OK && r.StringResult == "Hecho")) return true;
                if (r.Status != PromptStatus.OK) return false;
                switch (r.StringResult)
                {
                    case "Hilos":
                        var pi = ed.GetInteger(new PromptIntegerOptions($"\nHilos (1 = secuencial) <{sThreads}>: ")
                        { AllowNone = true, AllowZero = false, AllowNegative = false, DefaultValue = sThreads, UseDefaultValue = true });
                        if (pi.Status == PromptStatus.OK) sThreads = pi.Value;
                        break;
                    case "Tolerancia":
                        var pd = ed.GetDouble(new PromptDoubleOptions($"\nTolerancia <{sTol:G}>: ")
                        { AllowNone = true, AllowZero = false, AllowNegative = false, DefaultValue = sTol, UseDefaultValue = true });
                        if (pd.Status == PromptStatus.OK) sTol = pd.Value;
                        break;
                    case "Capa": sIgnoreLayer = AskYesNo(ed, "¿Ignorar la capa?", sIgnoreLayer); break;
                    case "Extremo": sE2e = AskYesNo(ed, "¿Combinar líneas alineadas extremo con extremo?", sE2e); break;
                }
            }
        }

        static bool AskYesNo(Editor ed, string q, bool cur)
        {
            var pko = new PromptKeywordOptions($"\n{q} [Si/No] <{(cur ? "Sí" : "No")}>: ", "Si No") { AllowNone = true };
            var r = ed.GetKeywords(pko);
            return r.Status == PromptStatus.OK ? r.StringResult == "Si" : cur;
        }

        // ------------------------------------------------------------ leer -> copiar
        static Drawing ReadLines(Database db, ObjectId[] sel, bool ignoreLayer)
        {
            var ids = new List<ObjectId>(sel.Length);
            var x0 = new List<double>(sel.Length); var y0 = new List<double>(sel.Length);
            var x1 = new List<double>(sel.Length); var y1 = new List<double>(sel.Length);
            var z = new List<double>(sel.Length); var props = new List<long>(sel.Length);
            // mismas propiedades -> mismo entero; incluye la elevación para no mezclar planos
            var keys = new Dictionary<(string, string, string, double, int, double, string, double), long>();
            var locked = new Dictionary<ObjectId, bool>();
            int skipped = 0;
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())
            {
                foreach (var id in sel)
                {
                    var ln = (Line)tr.GetObject(id, OpenMode.ForRead);
                    if (!locked.TryGetValue(ln.LayerId, out var isLocked))
                        locked[ln.LayerId] = isLocked = ((LayerTableRecord)tr.GetObject(ln.LayerId, OpenMode.ForRead)).IsLocked;
                    Point3d a = ln.StartPoint, b = ln.EndPoint;
                    if (isLocked || a.Z != b.Z) { skipped++; continue; }
                    var k = (ignoreLayer ? "" : ln.Layer, ln.Color.ToString(), ln.Linetype, ln.LinetypeScale,
                             (int)ln.LineWeight, ln.Thickness, ln.Transparency.ToString(), a.Z);
                    if (!keys.TryGetValue(k, out var v)) { v = keys.Count; keys[k] = v; }
                    ids.Add(id); x0.Add(a.X); y0.Add(a.Y); x1.Add(b.X); y1.Add(b.Y); z.Add(a.Z); props.Add(v);
                }
                tr.Commit();
            }
            return new Drawing
            {
                Ids = ids.ToArray(), Z = z.ToArray(), Props = props.ToArray(), Skipped = skipped,
                L = new Overkill.Lines { N = ids.Count, X0 = x0.ToArray(), Y0 = y0.ToArray(), X1 = x1.ToArray(), Y1 = y1.ToArray() },
            };
        }

        // ------------------------------------------------------------ reensamblar -> aplicar
        static (int kept, int erased, int changed) Apply(Database db, Drawing d, int[,] res)
        {
            var L = d.L;
            Point3d P(int i, int w) => w == 0 ? new Point3d(L.X0[i], L.Y0[i], d.Z[i]) : new Point3d(L.X1[i], L.Y1[i], d.Z[i]);
            int kept = 0, erased = 0, changed = 0;
            using (var tr = db.TransactionManager.StartTransaction())
            {
                for (int i = 0; i < L.N; i++)
                {
                    if (res[i, 0] == 1)
                    {
                        kept++;
                        bool same = res[i, 1] == i && res[i, 2] == 0 && res[i, 3] == i && res[i, 4] == 1;
                        if (same) continue;
                        var ln = (Line)tr.GetObject(d.Ids[i], OpenMode.ForWrite);
                        ln.StartPoint = P(res[i, 1], res[i, 2]);
                        ln.EndPoint = P(res[i, 3], res[i, 4]);
                        changed++;
                    }
                    else
                    {
                        ((Line)tr.GetObject(d.Ids[i], OpenMode.ForWrite)).Erase();
                        erased++;
                    }
                }
                tr.Commit();
            }
            return (kept, erased, changed);
        }
    }
}
