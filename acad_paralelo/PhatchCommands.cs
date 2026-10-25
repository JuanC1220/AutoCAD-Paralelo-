// PHATCH: sombrea muchas áreas a la vez, como -HATCH con un punto interior por área, pero analizando el dibujo
// una sola vez (ContornosCore.cs) en vez de una vez por clic. Receta: leer (hilo principal) -> contornos en
// paralelo -> crear los sombreados en transacciones de 5.000 (hilo principal).
// Contorno: LINE y polilíneas de tramos rectos visibles del espacio actual (capas no congeladas ni apagadas).
// Islas: estilo "Exterior" (sólo las islas directas). Arcos, círculos, splines y tramos curvos aún no se usan
// como contorno: se cuentan y se avisa.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AcadParalelo.PhatchCommands))]

namespace AcadParalelo
{
    public class PhatchCommands
    {
        static string sPatron = "ANSI31";
        static double sEscala = 1.0, sAngulo = 0.0;
        static int sHilos = Environment.ProcessorCount;
        static bool sVerificar = false;

        static string Ajustes() =>
            $"patrón {sPatron}, escala {sEscala:G}, ángulo {sAngulo:G}, hilos {sHilos}, verificar con AutoCAD {(sVerificar ? "Sí" : "No")}";

        [CommandMethod("PHATCH", CommandFlags.Modal)]
        public void Phatch()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            var ed = doc.Editor; var db = doc.Database;

            // puntos interiores: clics, o POINT seleccionados
            var pts = new List<Point3d>();
            while (true)
            {
                var ppo = new PromptPointOptions($"\n{Ajustes()}\nPunto interior o [Puntos/Patron/Escala/Angulo/Hilos/Verificar] <terminar>: ",
                                                 "Puntos Patron Escala Angulo Hilos Verificar") { AllowNone = true };
                var r = ed.GetPoint(ppo);
                if (r.Status == PromptStatus.OK) { pts.Add(r.Value.TransformBy(ed.CurrentUserCoordinateSystem)); continue; }   // SCP -> SCU
                if (r.Status == PromptStatus.None) break;
                if (r.Status != PromptStatus.Keyword) return;
                switch (r.StringResult)
                {
                    case "Puntos":
                        var filter = new SelectionFilter(new[] { new TypedValue((int)DxfCode.Start, "POINT") });
                        var psr = ed.GetSelection(new PromptSelectionOptions { MessageForAdding = "\nSeleccione los POINT (puntos interiores): " }, filter);
                        if (psr.Status == PromptStatus.OK)
                            foreach (var id in psr.Value.GetObjectIds())
                            {
#pragma warning disable 618
                                using var p = (DBPoint)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                                pts.Add(p.Position);
                            }
                        break;
                    case "Patron":
                        var ps = ed.GetString(new PromptStringOptions($"\nNombre del patrón <{sPatron}>: ") { AllowSpaces = false });
                        if (ps.Status == PromptStatus.OK && ps.StringResult.Trim() != "") sPatron = ps.StringResult.Trim().ToUpperInvariant();
                        break;
                    case "Escala":
                        var pe = ed.GetDouble(new PromptDoubleOptions($"\nEscala del patrón <{sEscala:G}>: ") { AllowNone = true, AllowZero = false, AllowNegative = false });
                        if (pe.Status == PromptStatus.OK) sEscala = pe.Value;
                        break;
                    case "Angulo":
                        var pa = ed.GetDouble(new PromptDoubleOptions($"\nÁngulo del patrón en grados <{sAngulo:G}>: ") { AllowNone = true });
                        if (pa.Status == PromptStatus.OK) sAngulo = pa.Value;
                        break;
                    case "Hilos":
                        var pi = ed.GetInteger(new PromptIntegerOptions($"\nHilos (1 = secuencial) <{sHilos}>: ") { AllowNone = true, AllowZero = false, AllowNegative = false });
                        if (pi.Status == PromptStatus.OK) sHilos = pi.Value;
                        break;
                    case "Verificar":
                        var pk = ed.GetKeywords(new PromptKeywordOptions($"\n¿Comparar cada contorno con el de AutoCAD (lento)? [Si/No] <{(sVerificar ? "Sí" : "No")}>: ", "Si No") { AllowNone = true });
                        if (pk.Status == PromptStatus.OK) sVerificar = pk.StringResult == "Si";
                        break;
                }
            }
            if (pts.Count == 0) return;

            var sw = Stopwatch.StartNew();
            var seg = LeerContornos(db, out int curvas);
            double tLeer = sw.Elapsed.TotalSeconds;
            var px = new double[pts.Count]; var py = new double[pts.Count];
            for (int i = 0; i < pts.Count; i++) { px[i] = pts[i].X; py[i] = pts[i].Y; }
            var R = Contornos.Calcular(seg.x0.ToArray(), seg.y0.ToArray(), seg.x1.ToArray(), seg.y1.ToArray(), px, py, sHilos);
            double tCalc = sw.Elapsed.TotalSeconds - tLeer;
            sw.Restart();
            int hechos = 0, sin = 0;
            for (int s0 = 0; s0 < pts.Count; s0 += Lector.Bloque)
            {
                int s1 = Math.Min(pts.Count, s0 + Lector.Bloque);
                using var tr = db.TransactionManager.StartTransaction();
                var ms = (BlockTableRecord)tr.GetObject(db.CurrentSpaceId, OpenMode.ForWrite);
                for (int i = s0; i < s1; i++)
                {
                    if (R.Exterior[i] == null) { sin++; continue; }
                    var h = new Hatch();
                    h.SetDatabaseDefaults();
                    ms.AppendEntity(h); tr.AddNewlyCreatedDBObject(h, true);
                    h.SetHatchPattern(HatchPatternType.PreDefined, sPatron);
                    h.PatternScale = sEscala;
                    h.PatternAngle = sAngulo * Math.PI / 180;
                    h.Associative = false;
                    h.HatchStyle = HatchStyle.Outer;
                    h.Elevation = pts[i].Z;
                    Lazo(h, HatchLoopTypes.External | HatchLoopTypes.Polyline, R.Exterior[i]);
                    foreach (var isla in R.Islas[i]) Lazo(h, HatchLoopTypes.Outermost | HatchLoopTypes.Polyline, isla);
                    h.EvaluateHatch(true);
                    hechos++;
                }
                tr.Commit();
            }
            double tCrear = sw.Elapsed.TotalSeconds;

            string ver = "";
            if (sVerificar)
            {
                sw.Restart();
                int iguales = 0, distintos = 0, soloNuestro = 0, soloAcad = 0;
                for (int i = 0; i < pts.Count; i++)
                {
                    double? aAcad = null;
                    var objs = ed.TraceBoundary(pts[i], false);
                    if (objs.Count > 0 && objs[0] is Polyline pl && pl.Closed) aAcad = Math.Abs(pl.Area);
                    foreach (DBObject o in objs) o.Dispose();
                    double? aNuestro = R.Exterior[i] == null ? null : Math.Abs(Contornos.Area(R.Exterior[i]));
                    if (aAcad == null && aNuestro == null) iguales++;
                    else if (aAcad == null) soloNuestro++;
                    else if (aNuestro == null) soloAcad++;
                    else if (Math.Abs(aAcad.Value - aNuestro.Value) <= 1e-6 * Math.Max(1, aAcad.Value)) iguales++;
                    else distintos++;
                }
                ver = $"\n  Verificación contra AutoCAD (TraceBoundary, {sw.Elapsed.TotalSeconds:F3} s): iguales {iguales}, área distinta {distintos}, " +
                      $"sólo nosotros {soloNuestro}, sólo AutoCAD {soloAcad}";
            }

            var tm = string.Join(", ", FormatearTiempos(R.Tiempos));
            Informe.Escribir($"\nPHATCH ({Ajustes()}): {pts.Count} puntos, {hechos} sombreados" + (sin > 0 ? $", {sin} puntos sin contorno cerrado" : "") +
                             $".\n  Contorno: {seg.x0.Count} segmentos, {R.Vertices} vértices, {R.Ciclos} ciclos, {R.Piezas} piezas" +
                             (curvas > 0 ? $"; {curvas} objetos curvos (arco, círculo, spline, tramo curvo) no usados como contorno" : "") +
                             $".\n  Tiempos: leer {tLeer:F3} s, contornos {tCalc:F3} s ({tm}), crear {tCrear:F3} s, total {tLeer + tCalc + tCrear:F3} s{ver}\n");
        }

        static List<string> FormatearTiempos(Dictionary<string, double> t)
        {
            var l = new List<string>();
            foreach (var kv in t) l.Add($"{kv.Key} {kv.Value:F3}");
            return l;
        }

        static void Lazo(Hatch h, HatchLoopTypes tipo, double[] xy)
        {
            var v = new Point2dCollection(); var b = new DoubleCollection();
            for (int k = 0; k < xy.Length; k += 2) { v.Add(new Point2d(xy[k], xy[k + 1])); b.Add(0); }
            v.Add(v[0]); b.Add(0);
            h.AppendLoop(tipo, v, b);
        }

        // segmentos rectos de LINE y polilíneas visibles del espacio actual
        static (List<double> x0, List<double> y0, List<double> x1, List<double> y1) LeerContornos(Database db, out int curvas)
        {
            var x0 = new List<double>(); var y0 = new List<double>(); var x1 = new List<double>(); var y1 = new List<double>();
            curvas = 0;
            var cLine = RXObject.GetClass(typeof(Line)); var cPoly = RXObject.GetClass(typeof(Polyline));
            var cArc = RXObject.GetClass(typeof(Arc)); var cCircle = RXObject.GetClass(typeof(Circle));
            var cEll = RXObject.GetClass(typeof(Ellipse)); var cSpl = RXObject.GetClass(typeof(Spline));
            var visible = new Dictionary<ObjectId, bool>();
            using var tr = db.TransactionManager.StartOpenCloseTransaction();
            bool Visible(ObjectId layer)
            {
                if (!visible.TryGetValue(layer, out var v))
                {
                    var l = (LayerTableRecord)tr.GetObject(layer, OpenMode.ForRead);
                    visible[layer] = v = !l.IsFrozen && !l.IsOff;
                }
                return v;
            }
            var space = (BlockTableRecord)tr.GetObject(db.CurrentSpaceId, OpenMode.ForRead);
            foreach (ObjectId id in space)
            {
                var c = id.ObjectClass;
                if (c == cLine)
                {
#pragma warning disable 618
                    using var ln = (Line)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                    if (!Visible(ln.LayerId)) continue;
                    x0.Add(ln.StartPoint.X); y0.Add(ln.StartPoint.Y); x1.Add(ln.EndPoint.X); y1.Add(ln.EndPoint.Y);
                }
                else if (c == cPoly)
                {
#pragma warning disable 618
                    using var pl = (Polyline)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                    if (!Visible(pl.LayerId)) continue;
                    int nvx = pl.NumberOfVertices, nseg = pl.Closed ? nvx : nvx - 1;
                    bool curva = false;
                    for (int k = 0; k < nseg; k++)
                    {
                        if (pl.GetBulgeAt(k) != 0) { curva = true; continue; }
                        var a = pl.GetPoint2dAt(k); var b = pl.GetPoint2dAt((k + 1) % nvx);
                        x0.Add(a.X); y0.Add(a.Y); x1.Add(b.X); y1.Add(b.Y);
                    }
                    if (curva) curvas++;
                }
                else if (c == cArc || c == cCircle || c == cEll || c == cSpl) curvas++;
            }
            tr.Commit();
            return (x0, y0, x1, y1);
        }
    }
}
