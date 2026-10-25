// Lector común de entidades: el paso "leer -> copiar" de la receta, compartido por todos los comandos.
// La base de datos de AutoCAD sólo se puede leer desde el hilo principal, así que esto es secuencial
// y conviene que sea lo más barato posible:
//   - abrir y cerrar cada objeto de inmediato (ObjectId.Open). Medido con PLEERMEDIR en AutoCAD 2027, 1,2M líneas:
//     una a una 0,38 s; transacción normal en bloques de 20.000 0,46 s; abrir/cerrar en bloques de 5.000 0,68 s,
//     de 100.000 8,0 s y todo en una transacción 92 s (el costo crece con lo que queda abierto),
//   - leer propiedades como ObjectId o valor, nunca como texto (Layer, Linetype, Color.ToString() resuelven
//     nombres en cada entidad),
//   - leer el estilo de trazado sólo si el dibujo usa estilos con nombre (STB).
// Propiedades que distinguen dos entidades (las de OVERKILL): capa, color, tipo de línea, escala del tipo de línea,
// grosor, altura de objeto, transparencia, estilo de trazado, material y normal. Se codifican en un entero.
// Se omiten las entidades en capas bloqueadas (no se pueden modificar); las congeladas ya no entran en la selección.
// Lee LINE (3D), ARC, CIRCLE y LWPOLYLINE en las columnas de OverkillV2Core.cs.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

namespace AcadParalelo
{
    public static class Lector
    {
        public const int Bloque = 5000;   // para escribir: transacciones de este tamaño

        public sealed class Entidades
        {
            public ObjectId[] IdL, IdA, IdP;
            public OverkillV2.Lineas L;
            public OverkillV2.Arcos A;
            public OverkillV2.Polis P;
            public int Grupos;         // combinaciones distintas de propiedades
            public int Bloqueadas, Otras;
            public double TLeer;
        }

        readonly record struct Clave(ObjectId Capa, int ColorMetodo, int Color, ObjectId TipoLinea, double EscalaTipo,
                                     int Grosor, double Altura, int Transparencia, PlotStyleDescriptor Estilo,
                                     ObjectId Material, Vector3d Normal);

        public static Entidades LeerEntidades(Database db, ObjectId[] sel, bool ignorarCapa)
        {
            var cLine = RXObject.GetClass(typeof(Line)); var cArc = RXObject.GetClass(typeof(Arc));
            var cCircle = RXObject.GetClass(typeof(Circle)); var cPoly = RXObject.GetClass(typeof(Polyline));
            var claves = new Dictionary<Clave, int>();
            var bloqueada = new Dictionary<ObjectId, bool>();
            bool estilosConNombre = !db.PlotStyleMode;
            var r = new Entidades();
            var idL = new List<ObjectId>(); var lx0 = new List<double>(); var ly0 = new List<double>(); var lz0 = new List<double>();
            var lx1 = new List<double>(); var ly1 = new List<double>(); var lz1 = new List<double>(); var lp = new List<int>();
            var idA = new List<ObjectId>(); var cx = new List<double>(); var cy = new List<double>(); var cz = new List<double>();
            var cr = new List<double>(); var ca = new List<double>(); var cb = new List<double>(); var cc = new List<bool>(); var cp = new List<int>();
            var idP = new List<ObjectId>(); var pp = new List<int>(); var pc = new List<bool>(); var pe = new List<double>(); var pv = new List<double[]>();
            var sw = Stopwatch.StartNew();
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())   // sólo para las capas
            {
                int Prop(Entity e, Vector3d normal, double altura)
                {
                    var ec = e.EntityColor;
                    var tp = e.Transparency;
                    var k = new Clave(ignorarCapa ? ObjectId.Null : e.LayerId, (int)ec.ColorMethod, ec.TrueColor,
                                      e.LinetypeId, e.LinetypeScale, (int)e.LineWeight, altura,
                                      tp.IsByAlpha ? tp.Alpha : tp.IsByBlock ? -2 : -1,
                                      estilosConNombre ? e.PlotStyleNameId : default, e.MaterialId, normal);
                    if (!claves.TryGetValue(k, out var v)) { v = claves.Count; claves[k] = v; }
                    return v;
                }
                foreach (var id in sel)
                {
                    var c = id.ObjectClass;
                    if (c != cLine && c != cArc && c != cCircle && c != cPoly) { r.Otras++; continue; }
#pragma warning disable 618
                    using var e = (Entity)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                    var capa = e.LayerId;
                    if (!bloqueada.TryGetValue(capa, out var esBloq))
                        bloqueada[capa] = esBloq = ((LayerTableRecord)tr.GetObject(capa, OpenMode.ForRead)).IsLocked;
                    if (esBloq) { r.Bloqueadas++; continue; }
                    switch (e)
                    {
                        case Line ln:
                            Point3d a = ln.StartPoint, b = ln.EndPoint;
                            idL.Add(id); lx0.Add(a.X); ly0.Add(a.Y); lz0.Add(a.Z); lx1.Add(b.X); ly1.Add(b.Y); lz1.Add(b.Z);
                            lp.Add(Prop(ln, ln.Normal, ln.Thickness));
                            break;
                        case Arc ar:
                            idA.Add(id); cx.Add(ar.Center.X); cy.Add(ar.Center.Y); cz.Add(ar.Center.Z); cr.Add(ar.Radius);
                            ca.Add(ar.StartAngle); cb.Add(ar.EndAngle); cc.Add(false); cp.Add(Prop(ar, ar.Normal, ar.Thickness));
                            break;
                        case Circle ci:
                            idA.Add(id); cx.Add(ci.Center.X); cy.Add(ci.Center.Y); cz.Add(ci.Center.Z); cr.Add(ci.Radius);
                            ca.Add(0); cb.Add(0); cc.Add(true); cp.Add(Prop(ci, ci.Normal, ci.Thickness));
                            break;
                        case Polyline pl:
                            int nv = pl.NumberOfVertices;
                            var v = new double[3 * nv];
                            for (int k = 0; k < nv; k++) { var q = pl.GetPoint2dAt(k); v[3 * k] = q.X; v[3 * k + 1] = q.Y; v[3 * k + 2] = pl.GetBulgeAt(k); }
                            idP.Add(id); pp.Add(Prop(pl, pl.Normal, pl.Thickness)); pc.Add(pl.Closed); pe.Add(pl.Elevation); pv.Add(v);
                            break;
                    }
                }
                tr.Commit();
            }
            r.TLeer = sw.Elapsed.TotalSeconds;
            r.Grupos = claves.Count;
            r.IdL = idL.ToArray(); r.IdA = idA.ToArray(); r.IdP = idP.ToArray();
            r.L = new OverkillV2.Lineas { N = idL.Count, X0 = lx0.ToArray(), Y0 = ly0.ToArray(), Z0 = lz0.ToArray(), X1 = lx1.ToArray(), Y1 = ly1.ToArray(), Z1 = lz1.ToArray(), Prop = lp.ToArray() };
            r.A = new OverkillV2.Arcos { N = idA.Count, CX = cx.ToArray(), CY = cy.ToArray(), CZ = cz.ToArray(), R = cr.ToArray(), Ini = ca.ToArray(), Fin = cb.ToArray(), Circulo = cc.ToArray(), Prop = cp.ToArray() };
            r.P = new OverkillV2.Polis { N = idP.Count, Prop = pp.ToArray(), Cerrada = pc.ToArray(), Elev = pe.ToArray(), V = pv.ToArray() };
            return r;
        }
    }
}
