// Lector común de entidades: el paso "leer -> copiar" de la receta, compartido por todos los comandos.
// La base de datos de AutoCAD sólo se puede leer desde el hilo principal, así que esto es secuencial
// y conviene que sea lo más barato posible:
//   - abrir y cerrar cada objeto de inmediato (ObjectId.Open). Medido con PLEERMEDIR en AutoCAD 2027, 1,2M líneas:
//     una a una 0,38 s; transacción normal en bloques de 20.000 0,46 s; abrir/cerrar en bloques de 5.000 0,68 s,
//     de 100.000 8,0 s y todo en una transacción 92 s (el costo crece con lo que queda abierto),
//   - leer propiedades como ObjectId o valor, nunca como texto (Layer, Linetype, Color.ToString() resuelven
//     nombres en cada entidad),
//   - leer el estilo de trazado sólo si el dibujo usa estilos con nombre (STB).
// Propiedades que distinguen dos líneas (las de OVERKILL): capa, color, tipo de línea, escala del tipo de línea,
// grosor, altura de objeto, transparencia, estilo de trazado y material; además normal y elevación, para no mezclar planos.
// Se omiten las líneas en capas bloqueadas (no se pueden modificar) y las que no están en un plano XY.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace AcadParalelo
{
    public static class Lector
    {
        public const int Bloque = 5000;   // para escribir: transacciones de este tamaño

        public sealed class Lineas
        {
            public ObjectId[] Ids;
            public double[] Z;
            public Overkill.Lines L;   // columnas X0, Y0, X1, Y1 para el núcleo
            public long[] Props;       // un entero por combinación de propiedades
            public int Grupos;         // combinaciones distintas
            public int Bloqueadas, NoPlanas;
            public double TLeer;
        }

        readonly record struct Clave(ObjectId Capa, int ColorMetodo, int Color, ObjectId TipoLinea, double EscalaTipo,
                                     int Grosor, double Altura, int Transparencia, PlotStyleDescriptor Estilo,
                                     ObjectId Material, Vector3d Normal, double Z);

        public static Lineas LeerLineas(Database db, ObjectId[] sel, bool ignorarCapa)
        {
            int n = sel.Length;
            var ids = new List<ObjectId>(n);
            var x0 = new List<double>(n); var y0 = new List<double>(n);
            var x1 = new List<double>(n); var y1 = new List<double>(n);
            var z = new List<double>(n); var props = new List<long>(n);
            var claves = new Dictionary<Clave, long>();
            var bloqueada = new Dictionary<ObjectId, bool>();
            bool estilosConNombre = !db.PlotStyleMode;
            var r = new Lineas();
            var sw = Stopwatch.StartNew();
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())   // sólo para las capas
            {
                foreach (var id in sel)
                {
#pragma warning disable 618
                    using var ln = (Line)id.Open(OpenMode.ForRead);
#pragma warning restore 618
                    var capa = ln.LayerId;
                    if (!bloqueada.TryGetValue(capa, out var esBloq))
                        bloqueada[capa] = esBloq = ((LayerTableRecord)tr.GetObject(capa, OpenMode.ForRead)).IsLocked;
                    if (esBloq) { r.Bloqueadas++; continue; }
                    Point3d a = ln.StartPoint, b = ln.EndPoint;
                    if (a.Z != b.Z) { r.NoPlanas++; continue; }
                    var ec = ln.EntityColor;
                    var tp = ln.Transparency;
                    var k = new Clave(ignorarCapa ? ObjectId.Null : capa, (int)ec.ColorMethod, ec.TrueColor,
                                      ln.LinetypeId, ln.LinetypeScale, (int)ln.LineWeight, ln.Thickness,
                                      tp.IsByAlpha ? tp.Alpha : tp.IsByBlock ? -2 : -1,
                                      estilosConNombre ? ln.PlotStyleNameId : default, ln.MaterialId,
                                      ln.Thickness != 0 ? ln.Normal : Vector3d.ZAxis, a.Z);
                    if (!claves.TryGetValue(k, out var v)) { v = claves.Count; claves[k] = v; }
                    ids.Add(id); x0.Add(a.X); y0.Add(a.Y); x1.Add(b.X); y1.Add(b.Y); z.Add(a.Z); props.Add(v);
                }
                tr.Commit();
            }
            r.TLeer = sw.Elapsed.TotalSeconds;
            r.Ids = ids.ToArray(); r.Z = z.ToArray(); r.Props = props.ToArray(); r.Grupos = claves.Count;
            r.L = new Overkill.Lines { N = ids.Count, X0 = x0.ToArray(), Y0 = y0.ToArray(), X1 = x1.ToArray(), Y1 = y1.ToArray() };
            return r;
        }
    }
}
