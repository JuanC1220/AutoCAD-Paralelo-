// Plugin de AutoCAD: OVERKILL paralelo sobre LINE, ARC, CIRCLE y LWPOLYLINE con el núcleo de overkill/v2
// (tolerancia geométrica real en 3D; 100 % en el dibujo extremo). Receta: leer (hilo principal, API de AutoCAD)
// -> copiar a columnas -> calcular en paralelo (sin tocar AutoCAD) -> aplicar en transacciones (hilo principal).
// La API de AutoCAD no es segura entre hilos: sólo el cálculo corre en paralelo.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.Colors;
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
            var d = Lector.LeerEntidades(doc.Database, ids, sIgnoreLayer);
            double tRead = sw.Elapsed.TotalSeconds;
            var rl = OverkillV2.ProcesarLineas(d.L, sTol, sE2e, sThreads);
            var ra = OverkillV2.ProcesarArcos(d.A, sTol, sE2e);
            var rp = OverkillV2.ProcesarPolis(d.P, sTol);
            double tComp = sw.Elapsed.TotalSeconds;
            var c = Apply(doc.Database, d, rl, ra, rp);
            double tTotal = sw.Elapsed.TotalSeconds;

            Informe.Escribir($"\nPOVERKILL ({Settings()}): {d.L.N} líneas, {d.A.N} arcos/círculos, {d.P.N} polilíneas" +
                            (d.Bloqueadas > 0 ? $", omitidas {d.Bloqueadas} en capa bloqueada" : "") +
                            (d.Otras > 0 ? $", {d.Otras} de otros tipos sin tocar" : "") +
                            $", {d.Grupos} combinaciones de propiedades" +
                            $".\n  Borradas: {c.lBorr} líneas, {c.aBorr} arcos/círculos, {c.pBorr} polilíneas; modificadas: {c.lMod} líneas, {c.aMod} arcos ({c.aCirc} pasan a círculo)." +
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
            var d = Lector.LeerEntidades(doc.Database, ids, sIgnoreLayer);
            Informe.Escribir($"\nPOVERKILLBENCH ({Settings()}): {d.L.N} líneas, leer {sw.Elapsed.TotalSeconds:F3} s, núcleos {Environment.ProcessorCount}\n");
            var ths = new List<int> { 1 };
            for (int t = 2; t < Environment.ProcessorCount; t *= 2) ths.Add(t);
            ths.Add(Environment.ProcessorCount);
            string refSha = null; double t1 = 0;
            foreach (var t in ths.Distinct())
            {
                double best = double.MaxValue; OverkillV2.ResLineas res = null;
                for (int r = 0; r < 4; r++)           // la primera pasada calienta el JIT
                {
                    var s0 = Stopwatch.StartNew();
                    res = OverkillV2.ProcesarLineas(d.L, sTol, sE2e, t);
                    if (r > 0) best = Math.Min(best, s0.Elapsed.TotalSeconds);
                }
                var (borradas, sha) = Huella(res);
                refSha ??= sha;
                if (t == 1) t1 = best;
                Informe.Escribir($"  hilos={t,2} quedan={d.L.N - borradas} calcular={best:F3} s ({t1 / best:F1}x) {(sha == refSha ? "IGUAL" : "DISTINTO")} sha={sha[..16]}\n");
            }
        }

        static (int borradas, string sha) Huella(OverkillV2.ResLineas r)
        {
            var sb = new System.Text.StringBuilder(); int b = 0;
            for (int i = 0; i < r.Borrar.Length; i++) if (r.Borrar[i]) { b++; sb.Append(i).Append('\n'); }
            foreach (var kv in r.Nueva.OrderBy(k => k.Key))
                sb.Append(kv.Key).Append(' ').Append(kv.Value.X0.ToString("R")).Append(' ').Append(kv.Value.Y0.ToString("R")).Append(' ').Append(kv.Value.Z0.ToString("R"))
                  .Append(' ').Append(kv.Value.X1.ToString("R")).Append(' ').Append(kv.Value.Y1.ToString("R")).Append(' ').Append(kv.Value.Z1.ToString("R")).Append('\n');
            var h = System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.ASCII.GetBytes(sb.ToString()));
            return (b, Convert.ToHexString(h).ToLowerInvariant());
        }

        static string Settings() =>
            $"hilos {sThreads}, tolerancia {sTol:G}, ignorar capa {(sIgnoreLayer ? "Sí" : "No")}, extremo con extremo {(sE2e ? "Sí" : "No")}";

        static ObjectId[] SelectLines(Editor ed)
        {
            var filter = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "LINE,ARC,CIRCLE,LWPOLYLINE") });
            var pso = new PromptSelectionOptions { MessageForAdding = "\nSeleccione objetos (se procesan LINE, ARC, CIRCLE y LWPOLYLINE): " };
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

        // ------------------------------------------------------------ aplicar (en bloques: ver Lector)
        static (int lBorr, int lMod, int aBorr, int aMod, int aCirc, int pBorr) Apply(Database db, Lector.Entidades d,
            OverkillV2.ResLineas rl, OverkillV2.ResArcos ra, bool[] rp)
        {
            var tareas = new List<Action<Transaction>>();
            int lBorr = 0, lMod = 0, aBorr = 0, aMod = 0, aCirc = 0, pBorr = 0;
            for (int i = 0; i < d.L.N; i++)
            {
                int k = i;
                if (rl.Borrar[i]) { lBorr++; tareas.Add(tr => tr.GetObject(d.IdL[k], OpenMode.ForWrite).Erase()); }
                else if (rl.Nueva.TryGetValue(i, out var g))
                {
                    // el superviviente suele quedar igual (copias exactas, contenidas): no reescribirlo ahorra tiempo
                    if (g.X0 == d.L.X0[i] && g.Y0 == d.L.Y0[i] && g.Z0 == d.L.Z0[i] && g.X1 == d.L.X1[i] && g.Y1 == d.L.Y1[i] && g.Z1 == d.L.Z1[i])
                        continue;
                    lMod++;
                    tareas.Add(tr =>
                    {
                        var ln = (Line)tr.GetObject(d.IdL[k], OpenMode.ForWrite);
                        ln.StartPoint = new Point3d(g.X0, g.Y0, g.Z0);
                        ln.EndPoint = new Point3d(g.X1, g.Y1, g.Z1);
                    });
                }
            }
            for (int i = 0; i < d.A.N; i++)
            {
                int k = i;
                if (ra.Borrar[i]) { aBorr++; tareas.Add(tr => tr.GetObject(d.IdA[k], OpenMode.ForWrite).Erase()); }
                else if (ra.ACirculo.Contains(i))
                {
                    aCirc++;
                    tareas.Add(tr =>
                    {
                        var ar = (Arc)tr.GetObject(d.IdA[k], OpenMode.ForWrite);
                        var ci = new Circle(ar.Center, ar.Normal, ar.Radius);
                        ci.SetPropertiesFrom(ar);
                        ci.Thickness = ar.Thickness;
                        var owner = (BlockTableRecord)tr.GetObject(ar.OwnerId, OpenMode.ForWrite);
                        owner.AppendEntity(ci); tr.AddNewlyCreatedDBObject(ci, true);
                        ar.Erase();
                    });
                }
                else if (ra.Nuevo.TryGetValue(i, out var g))
                {
                    if (g.Ini == d.A.Ini[i] && g.Fin == d.A.Fin[i]) continue;
                    aMod++;
                    tareas.Add(tr =>
                    {
                        var ar = (Arc)tr.GetObject(d.IdA[k], OpenMode.ForWrite);
                        ar.StartAngle = g.Ini; ar.EndAngle = g.Fin;
                    });
                }
            }
            for (int i = 0; i < d.P.N; i++)
            {
                int k = i;
                if (rp[i]) { pBorr++; tareas.Add(tr => tr.GetObject(d.IdP[k], OpenMode.ForWrite).Erase()); }
            }
            for (int s0 = 0; s0 < tareas.Count; s0 += Lector.Bloque)
            {
                using var tr = db.TransactionManager.StartTransaction();
                for (int i = s0; i < Math.Min(tareas.Count, s0 + Lector.Bloque); i++) tareas[i](tr);
                tr.Commit();
            }
            return (lBorr, lMod, aBorr, aMod, aCirc, pBorr);
        }
    }
}
