// Contornos de HATCH en paralelo (lo que hace HATCH al hacer clic dentro de un área).
// Medido en AutoCAD 2027: detectar el contorno es el 98 % del tiempo de -HATCH y crece mucho más que lineal,
// porque cada clic vuelve a analizar el dibujo. Aquí el dibujo se analiza una sola vez y cada punto sólo
// consulta lo que tiene cerca:
//   1) rejilla espacial de segmentos,
//   2) cruces entre segmentos por celda (paralelo) y troceo de cada segmento en sus cruces (paralelo),
//   3) grafo plano: se fusionan vértices dentro de la tolerancia, se quitan aristas repetidas y colgantes,
//   4) caras: cada arista dirigida sigue a la siguiente en sentido horario en su vértice final;
//      ciclos antihorarios = borde exterior de una cara, horarios = borde exterior de una pieza suelta (isla),
//   5) por punto (paralelo): rayo hacia +x, la primera arista que mira al punto con ciclo antihorario es su contorno;
//      las piezas cuyo ciclo horario se cruza antes son islas y se saltan,
//   6) islas de cada cara (estilo "Exterior"): cada pieza suelta busca, con el mismo rayo, la cara que la contiene.
// Sólo segmentos rectos (LINE y tramos rectos de polilínea). Sin dependencias de AutoCAD: se prueba fuera de él.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

public static class Contornos
{
    public sealed class Resultado
    {
        public double[][] Exterior;      // por punto: x0,y0,x1,y1,... (antihorario) o null si el punto no está encerrado
        public double[][][] Islas;       // por punto: bordes de las islas directas (horario)
        public int Vertices, Aristas, Ciclos, Piezas;
        public Dictionary<string, double> Tiempos = new();
    }

    sealed class Rejilla
    {
        public double X0, Y0, Cell; public int NX, NY;
        public int[] Start, Items;
        public int CX(double x) => Math.Clamp((int)Math.Floor((x - X0) / Cell), 0, NX - 1);
        public int CY(double y) => Math.Clamp((int)Math.Floor((y - Y0) / Cell), 0, NY - 1);

        // celdas que toca el segmento: por cada fila de la caja, el tramo de x del segmento dentro de esa fila
        public void Celdas(double ax, double ay, double bx, double by, List<int> outCells)
        {
            outCells.Clear();
            int r0 = CY(Math.Min(ay, by)), r1 = CY(Math.Max(ay, by));
            for (int r = r0; r <= r1; r++)
            {
                double ylo = Y0 + r * Cell, yhi = ylo + Cell;
                double xa, xb;
                if (ay == by) { xa = Math.Min(ax, bx); xb = Math.Max(ax, bx); }
                else
                {
                    double t0 = (Math.Max(ylo, Math.Min(ay, by)) - ay) / (by - ay);
                    double t1 = (Math.Min(yhi, Math.Max(ay, by)) - ay) / (by - ay);
                    double x0 = ax + Math.Clamp(t0, 0, 1) * (bx - ax), x1 = ax + Math.Clamp(t1, 0, 1) * (bx - ax);
                    xa = Math.Min(x0, x1); xb = Math.Max(x0, x1);
                }
                int c0 = CX(xa), c1 = CX(xb);
                for (int c = c0; c <= c1; c++) outCells.Add(r * NX + c);
            }
        }

        public static Rejilla Crear(double[] ax, double[] ay, double[] bx, double[] by, int n)
        {
            double minX = double.MaxValue, minY = double.MaxValue, maxX = double.MinValue, maxY = double.MinValue;
            for (int i = 0; i < n; i++)
            {
                minX = Math.Min(minX, Math.Min(ax[i], bx[i])); maxX = Math.Max(maxX, Math.Max(ax[i], bx[i]));
                minY = Math.Min(minY, Math.Min(ay[i], by[i])); maxY = Math.Max(maxY, Math.Max(ay[i], by[i]));
            }
            if (n == 0) { minX = minY = 0; maxX = maxY = 1; }
            double w = Math.Max(maxX - minX, 1e-9), h = Math.Max(maxY - minY, 1e-9);
            double cell = Math.Max(Math.Sqrt(w * h / Math.Max(n, 1)) * 2, Math.Max(w, h) / 4096);
            var g = new Rejilla { X0 = minX, Y0 = minY, Cell = cell, NX = (int)(w / cell) + 1, NY = (int)(h / cell) + 1 };
            var count = new int[g.NX * g.NY + 1];
            var tmp = new List<int>();
            for (int i = 0; i < n; i++) { g.Celdas(ax[i], ay[i], bx[i], by[i], tmp); foreach (var c in tmp) count[c + 1]++; }
            for (int c = 0; c < g.NX * g.NY; c++) count[c + 1] += count[c];
            g.Start = count; g.Items = new int[count[^1]];
            var fill = (int[])count.Clone();
            for (int i = 0; i < n; i++) { g.Celdas(ax[i], ay[i], bx[i], by[i], tmp); foreach (var c in tmp) g.Items[fill[c]++] = i; }
            return g;
        }
    }

    static double Cross(double ax, double ay, double bx, double by) => ax * by - ay * bx;

    public static Resultado Calcular(double[] sx0, double[] sy0, double[] sx1, double[] sy1, double[] px, double[] py, int hilos)
    {
        var R = new Resultado();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        double Lap(string k) { double t = sw.Elapsed.TotalSeconds; R.Tiempos[k] = t; sw.Restart(); return t; }
        var po = new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, hilos) };
        int n = sx0.Length;

        // tolerancia de fusión de vértices: relativa al tamaño del dibujo
        double ext = 1;
        for (int i = 0; i < n; i++) ext = Math.Max(ext, Math.Max(Math.Max(Math.Abs(sx0[i]), Math.Abs(sy0[i])), Math.Max(Math.Abs(sx1[i]), Math.Abs(sy1[i]))));
        double tol = ext * 1e-10;

        // 1) rejilla de segmentos
        var G = Rejilla.Crear(sx0, sy0, sx1, sy1, n);
        Lap("rejilla");

        // 2) cruces por celda; cada cruce se anota sólo en la celda donde cae (sin duplicados entre celdas)
        var cortes = new List<double>[n];
        for (int i = 0; i < n; i++) cortes[i] = new List<double> { 0.0, 1.0 };
        var porHilo = new ThreadLocal<List<(int s, double t)>>(() => new List<(int, double)>(), true);
        Parallel.For(0, G.NX * G.NY, po, c =>
        {
            int a0 = G.Start[c], a1 = G.Start[c + 1];
            if (a1 - a0 < 2) return;
            var outl = porHilo.Value;
            for (int ia = a0; ia < a1; ia++)
            {
                int i = G.Items[ia];
                double pxi = sx0[i], pyi = sy0[i], rx = sx1[i] - pxi, ry = sy1[i] - pyi;
                double rl = Math.Sqrt(rx * rx + ry * ry);
                if (rl == 0) continue;
                for (int ib = ia + 1; ib < a1; ib++)
                {
                    int j = G.Items[ib];
                    double qx = sx0[j], qy = sy0[j], ux = sx1[j] - qx, uy = sy1[j] - qy;
                    double ul = Math.Sqrt(ux * ux + uy * uy);
                    if (ul == 0) continue;
                    // cajas
                    if (Math.Max(pxi, sx1[i]) < Math.Min(qx, sx1[j]) - tol || Math.Max(qx, sx1[j]) < Math.Min(pxi, sx1[i]) - tol ||
                        Math.Max(pyi, sy1[i]) < Math.Min(qy, sy1[j]) - tol || Math.Max(qy, sy1[j]) < Math.Min(pyi, sy1[i]) - tol) continue;
                    double den = Cross(rx, ry, ux, uy);
                    double wx = qx - pxi, wy = qy - pyi;
                    if (Math.Abs(den) > 1e-12 * rl * ul)
                    {
                        double t = Cross(wx, wy, ux, uy) / den, u = Cross(wx, wy, rx, ry) / den;
                        double et = tol / rl, eu = tol / ul;
                        if (t < -et || t > 1 + et || u < -eu || u > 1 + eu) continue;
                        t = Math.Clamp(t, 0, 1); u = Math.Clamp(u, 0, 1);
                        double ix = pxi + t * rx, iy = pyi + t * ry;
                        if (G.CY(iy) * G.NX + G.CX(ix) != c) continue;
                        outl.Add((i, t)); outl.Add((j, u));
                    }
                    else if (Math.Abs(Cross(wx, wy, rx, ry)) <= tol * rl)   // colineales: extremos de uno dentro del otro
                    {
                        void Proy(int seg, double ox, double oy, double dx, double dy, double dl2, double ex, double ey)
                        {
                            double t = ((ex - ox) * dx + (ey - oy) * dy) / dl2;
                            double e = tol / Math.Sqrt(dl2);
                            if (t <= e || t >= 1 - e) return;
                            if (G.CY(ey) * G.NX + G.CX(ex) != c) return;
                            outl.Add((seg, t));
                        }
                        Proy(i, pxi, pyi, rx, ry, rl * rl, qx, qy); Proy(i, pxi, pyi, rx, ry, rl * rl, sx1[j], sy1[j]);
                        Proy(j, qx, qy, ux, uy, ul * ul, pxi, pyi); Proy(j, qx, qy, ux, uy, ul * ul, sx1[i], sy1[i]);
                    }
                }
            }
        });
        foreach (var l in porHilo.Values) foreach (var (s, t) in l) cortes[s].Add(t);
        porHilo.Dispose();
        Lap("cruces");

        // 3) trocear y fusionar vértices (clave = coordenada redondeada a la tolerancia)
        var piezas = new (double x, double y)[n][];
        Parallel.For(0, n, po, i =>
        {
            var c = cortes[i]; c.Sort();
            var pts = new List<(double, double)>(c.Count);
            double rx = sx1[i] - sx0[i], ry = sy1[i] - sy0[i];
            foreach (var t in c) pts.Add(t == 1.0 ? (sx1[i], sy1[i]) : (sx0[i] + t * rx, sy0[i] + t * ry));
            piezas[i] = pts.ToArray();
        });
        var vid = new Dictionary<(long, long), int>();
        var vx = new List<double>(); var vy = new List<double>();
        var aristas = new HashSet<(int, int)>();
        int V((double x, double y) p)
        {
            var k = ((long)Math.Round(p.x / tol), (long)Math.Round(p.y / tol));
            if (!vid.TryGetValue(k, out var id)) { id = vx.Count; vid[k] = id; vx.Add(p.x); vy.Add(p.y); }
            return id;
        }
        foreach (var pts in piezas)
        {
            int prev = V(pts[0]);
            for (int k = 1; k < pts.Length; k++)
            {
                int cur = V(pts[k]);
                if (cur != prev) aristas.Add(prev < cur ? (prev, cur) : (cur, prev));
                prev = cur;
            }
        }
        int nv = vx.Count;
        Lap("trocear");

        // quitar aristas colgantes (vértices de grado 1), como hace HATCH
        var adj = new List<int>[nv];
        for (int v = 0; v < nv; v++) adj[v] = new List<int>(4);
        var ea = new List<int>(aristas.Count); var eb = new List<int>(aristas.Count);
        foreach (var (a, b) in aristas) { adj[a].Add(ea.Count); adj[b].Add(ea.Count); ea.Add(a); eb.Add(b); }
        var vivo = new bool[ea.Count]; Array.Fill(vivo, true);
        var grado = new int[nv]; for (int v = 0; v < nv; v++) grado[v] = adj[v].Count;
        var cola = new Queue<int>();
        for (int v = 0; v < nv; v++) if (grado[v] == 1) cola.Enqueue(v);
        while (cola.Count > 0)
        {
            int v = cola.Dequeue();
            if (grado[v] != 1) continue;
            foreach (var e in adj[v]) if (vivo[e])
                {
                    vivo[e] = false; grado[ea[e]]--; grado[eb[e]]--;
                    int o = ea[e] == v ? eb[e] : ea[e];
                    if (grado[o] == 1) cola.Enqueue(o);
                }
        }
        var E = new List<int>();
        for (int e = 0; e < ea.Count; e++) if (vivo[e]) E.Add(e);
        int ne = E.Count;
        // aristas dirigidas: 2k = a->b, 2k+1 = b->a
        var hFrom = new int[2 * ne]; var hTo = new int[2 * ne];
        for (int k = 0; k < ne; k++) { int e = E[k]; hFrom[2 * k] = ea[e]; hTo[2 * k] = eb[e]; hFrom[2 * k + 1] = eb[e]; hTo[2 * k + 1] = ea[e]; }
        R.Vertices = nv; R.Aristas = ne;
        Lap("grafo");

        // 4) orden angular de las salidas de cada vértice y siguiente arista de cada cara
        var outStart = new int[nv + 1];
        for (int h = 0; h < 2 * ne; h++) outStart[hFrom[h] + 1]++;
        for (int v = 0; v < nv; v++) outStart[v + 1] += outStart[v];
        var outH = new int[2 * ne]; var fillO = (int[])outStart.Clone();
        for (int h = 0; h < 2 * ne; h++) outH[fillO[hFrom[h]]++] = h;
        var pos = new int[2 * ne];
        Parallel.For(0, nv, po, v =>
        {
            int s0 = outStart[v], s1 = outStart[v + 1];
            if (s1 - s0 > 1)
                Array.Sort(outH, s0, s1 - s0, Comparer<int>.Create((p, q) =>
                    Math.Atan2(vy[hTo[p]] - vy[v], vx[hTo[p]] - vx[v]).CompareTo(Math.Atan2(vy[hTo[q]] - vy[v], vx[hTo[q]] - vx[v]))));
            for (int k = s0; k < s1; k++) pos[outH[k]] = k - s0;
        });
        var next = new int[2 * ne];
        Parallel.For(0, 2 * ne, po, h =>
        {
            int v = hTo[h], tw = h ^ 1, m = outStart[v + 1] - outStart[v];
            next[h] = outH[outStart[v] + (pos[tw] - 1 + m) % m];
        });
        var cyc = new int[2 * ne]; Array.Fill(cyc, -1);
        var area = new List<double>(); var cycStart = new List<int>();
        for (int h = 0; h < 2 * ne; h++)
        {
            if (cyc[h] >= 0) continue;
            int id = area.Count; double A = 0; int x = h;
            do { cyc[x] = id; A += Cross(vx[hFrom[x]], vy[hFrom[x]], vx[hTo[x]], vy[hTo[x]]); x = next[x]; } while (x != h);
            area.Add(A / 2); cycStart.Add(h);
        }
        R.Ciclos = area.Count;
        // piezas sueltas (unión de vértices)
        var par = new int[nv]; for (int v = 0; v < nv; v++) par[v] = v;
        int Find(int v) { while (par[v] != v) { par[v] = par[par[v]]; v = par[v]; } return v; }
        for (int k = 0; k < ne; k++) { int a = Find(hFrom[2 * k]), b = Find(hTo[2 * k]); if (a != b) par[a] = b; }
        var comp = new int[nv]; for (int v = 0; v < nv; v++) comp[v] = Find(v);
        Lap("caras");

        // rejilla de aristas finales para los rayos
        var ax = new double[ne]; var ay = new double[ne]; var bx = new double[ne]; var by = new double[ne];
        for (int k = 0; k < ne; k++) { ax[k] = vx[hFrom[2 * k]]; ay[k] = vy[hFrom[2 * k]]; bx[k] = vx[hTo[2 * k]]; by[k] = vy[hTo[2 * k]]; }
        var GE = Rejilla.Crear(ax, ay, bx, by, ne);

        // 5) rayo hacia +x: devuelve el ciclo antihorario que encierra (x,y) o -1; 'salta' = piezas a ignorar
        int Rayo(double x, double y, HashSet<int> salta)
        {
            int row = GE.CY(y);
            if (y < GE.Y0 || y > GE.Y0 + GE.NY * GE.Cell) return -1;
            var hits = new List<(double x, int k)>();
            for (int col = GE.CX(x); col < GE.NX; col++)
            {
                hits.Clear();
                int c = row * GE.NX + col;
                for (int ia = GE.Start[c]; ia < GE.Start[c + 1]; ia++)
                {
                    int k = GE.Items[ia];
                    if ((ay[k] <= y) == (by[k] <= y)) continue;          // regla semiabierta: rayo justo encima de y
                    double xi = ax[k] + (y - ay[k]) * (bx[k] - ax[k]) / (by[k] - ay[k]);
                    if (xi <= x || GE.CX(xi) != col) continue;
                    hits.Add((xi, k));
                }
                hits.Sort((p, q) => p.x.CompareTo(q.x));
                foreach (var (xi, k) in hits)
                {
                    int cp = comp[hFrom[2 * k]];
                    if (salta.Contains(cp)) continue;
                    int h = by[k] > ay[k] ? 2 * k : 2 * k + 1;            // la dirigida que sube tiene el punto a su izquierda
                    int cy = cyc[h];
                    if (area[cy] > 0) return cy;
                    salta.Add(cp);                                         // borde exterior de una isla: se salta la pieza
                }
            }
            return -1;
        }

        // 6) islas: cada pieza busca la cara que la contiene desde su vértice más a la derecha
        var masDerecha = new Dictionary<int, int>();
        for (int v = 0; v < nv; v++)
        {
            if (outStart[v + 1] == outStart[v]) continue;
            int cp = comp[v];
            if (!masDerecha.TryGetValue(cp, out var w) || vx[v] > vx[w]) masDerecha[cp] = v;
        }
        var piezasL = new List<int>(masDerecha.Keys);
        R.Piezas = piezasL.Count;
        var padre = new int[piezasL.Count];
        var exteriorPieza = new int[piezasL.Count];
        Parallel.For(0, piezasL.Count, po, i =>
        {
            int cp = piezasL[i], v = masDerecha[cp];
            padre[i] = Rayo(vx[v], vy[v], new HashSet<int> { cp });
            // su borde exterior: el ciclo horario de la pieza (área negativa más grande en valor absoluto)
            int best = -1;
            for (int k = outStart[v]; k < outStart[v + 1]; k++)
            {
                int c = cyc[outH[k]];
                if (area[c] < 0 && (best < 0 || area[c] < area[best])) best = c;
            }
            exteriorPieza[i] = best;
        });
        var hijos = new Dictionary<int, List<int>>();
        for (int i = 0; i < piezasL.Count; i++)
            if (padre[i] >= 0 && exteriorPieza[i] >= 0)
            {
                if (!hijos.TryGetValue(padre[i], out var l)) hijos[padre[i]] = l = new List<int>();
                l.Add(exteriorPieza[i]);
            }
        Lap("islas");

        double[] Ciclo(int c)
        {
            var xs = new List<double>();
            int h0 = cycStart[c], x = h0;
            do { xs.Add(vx[hFrom[x]]); xs.Add(vy[hFrom[x]]); x = next[x]; } while (x != h0);
            // quitar vértices alineados (las aristas troceadas en cruces que no doblan el contorno)
            var o = new List<double>();
            int m = xs.Count / 2;
            for (int i = 0; i < m; i++)
            {
                int p = (i + m - 1) % m, q = (i + 1) % m;
                double ux = xs[2 * i] - xs[2 * p], uy = xs[2 * i + 1] - xs[2 * p + 1];
                double wx = xs[2 * q] - xs[2 * i], wy = xs[2 * q + 1] - xs[2 * i + 1];
                double l = Math.Sqrt((ux * ux + uy * uy) * (wx * wx + wy * wy));
                if (Math.Abs(Cross(ux, uy, wx, wy)) <= 1e-12 * l && ux * wx + uy * wy > 0) continue;
                o.Add(xs[2 * i]); o.Add(xs[2 * i + 1]);
            }
            return o.ToArray();
        }

        int np = px.Length;
        R.Exterior = new double[np][]; R.Islas = new double[np][][];
        Parallel.For(0, np, po, i =>
        {
            int c = Rayo(px[i], py[i], new HashSet<int>());
            if (c < 0) return;
            R.Exterior[i] = Ciclo(c);
            R.Islas[i] = hijos.TryGetValue(c, out var l) ? l.ConvertAll(Ciclo).ToArray() : Array.Empty<double[]>();
        });
        Lap("puntos");
        return R;
    }

    public static double Area(double[] p)
    {
        double a = 0; int m = p.Length / 2;
        for (int i = 0; i < m; i++) { int j = (i + 1) % m; a += p[2 * i] * p[2 * j + 1] - p[2 * j] * p[2 * i + 1]; }
        return a / 2;
    }
}
