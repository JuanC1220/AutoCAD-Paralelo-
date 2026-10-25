// HATCH: antes de paralelizar, medir dónde se va el tiempo.
// PHATCHMEDIR crea un sombreado por cada POINT seleccionado (el punto es el "punto interior" de -HATCH)
// y cronometra por separado las tres fases que hace HATCH:
//   1) detectar el contorno     (Editor.TraceBoundary: lo que hace HATCH al hacer clic dentro)
//   2) crear el sombreado       (Hatch + AppendLoop)
//   3) generar el patrón        (Hatch.EvaluateHatch: líneas del patrón, cálculo interno de AutoCAD)
// La fase 3 no se puede repartir entre hilos (es de AutoCAD); la 1 sí se podría reimplementar en paralelo.
using System.Diagnostics;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AcadParalelo.HatchCommands))]

namespace AcadParalelo
{
    public class HatchCommands
    {
        [CommandMethod("PHATCHMEDIR", CommandFlags.Modal | CommandFlags.UsePickSet)]
        public void PhatchMedir()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor; var db = doc.Database;
            var filter = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "POINT") });
            var psr = ed.GetSelection(new PromptSelectionOptions { MessageForAdding = "\nSeleccione los POINT (puntos interiores): " }, filter);
            if (psr.Status != PromptStatus.OK) return;
            var ids = psr.Value.GetObjectIds();

            var pts = new Point3d[ids.Length];
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())
            {
                for (int i = 0; i < ids.Length; i++) pts[i] = ((DBPoint)tr.GetObject(ids[i], OpenMode.ForRead)).Position;
                tr.Commit();
            }

            // 1) contornos
            var sw = Stopwatch.StartNew();
            var loops = new (Point2dCollection v, DoubleCollection b)[pts.Length];
            int fails = 0;
            for (int i = 0; i < pts.Length; i++)
            {
                var objs = ed.TraceBoundary(pts[i], false);
                if (objs.Count > 0 && objs[0] is Polyline pl && pl.Closed)
                {
                    var v = new Point2dCollection(); var b = new DoubleCollection();
                    for (int k = 0; k < pl.NumberOfVertices; k++) { v.Add(pl.GetPoint2dAt(k)); b.Add(pl.GetBulgeAt(k)); }
                    v.Add(v[0]); b.Add(0);
                    loops[i] = (v, b);
                }
                else fails++;
                foreach (DBObject o in objs) o.Dispose();
            }
            double tTrace = sw.Elapsed.TotalSeconds;

            // 2) y 3) crear + patrón, cronometrados por separado
            double tCreate = 0, tEval = 0; int made = 0;
            var sw2 = new Stopwatch();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
                foreach (var lp in loops)
                {
                    if (lp.v == null) continue;
                    sw2.Restart();
                    var h = new Hatch();
                    h.SetDatabaseDefaults();
                    ms.AppendEntity(h); tr.AddNewlyCreatedDBObject(h, true);
                    h.SetHatchPattern(HatchPatternType.PreDefined, "ANSI31");
                    h.PatternScale = 1.0;
                    h.Associative = false;
                    h.AppendLoop(HatchLoopTypes.External | HatchLoopTypes.Polyline, lp.v, lp.b);
                    tCreate += sw2.Elapsed.TotalSeconds;
                    sw2.Restart();
                    h.EvaluateHatch(true);
                    tEval += sw2.Elapsed.TotalSeconds;
                    made++;
                }
                sw2.Restart();
                tr.Commit();
                tCreate += sw2.Elapsed.TotalSeconds;
            }
            double tTot = tTrace + tCreate + tEval;
            string Pct(double t) => tTot > 0 ? $"{100 * t / tTot:F0} %" : "-";
            Informe.Escribir($"\nPHATCHMEDIR: {pts.Length} puntos, {made} sombreados ANSI31" + (fails > 0 ? $", {fails} sin contorno cerrado" : "") +
                            $"\n  1) detectar contorno {tTrace:F3} s ({Pct(tTrace)})" +
                            $"\n  2) crear sombreado   {tCreate:F3} s ({Pct(tCreate)})" +
                            $"\n  3) generar patrón    {tEval:F3} s ({Pct(tEval)})" +
                            $"\n  total {tTot:F3} s\n");
        }
    }
}
