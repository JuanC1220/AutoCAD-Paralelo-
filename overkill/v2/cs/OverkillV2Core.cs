// OVERKILL v2: núcleo geométrico en C#, sin dependencias de AutoCAD (lo puede usar el plugin).
// Misma regla que overkill/v2/overkill_v2.py (referencia):
//   * tolerancia = distancia real en 3D: dos líneas se tratan si los extremos de la más corta
//     quedan a <= tol de la recta de la más larga; se fusionan si se solapan más de tol (o si se
//     tocan a tol con "extremo a extremo");
//   * propiedades: el llamador las codifica en un entero (igual entero = mismas propiedades);
//   * arcos/círculos: mismo centro, radio (a tol) y propiedades (incluida la normal);
//   * polilíneas: duplicadas idénticas (también invertidas o con otro inicio si son cerradas).
// Candidatos: cubetas angulares de ancho exacto pi/NB con una normal fija por cubeta (robusto con
// coordenadas grandes), grupos por distancia a esa normal y barrido por intervalos. Cada cubeta es
// independiente: se reparten entre hilos y el resultado no depende del reparto.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;

public static class OverkillV2
{
    public const int NB = 31416;
    static readonly double W = Math.PI / NB;

    // ------------------------------------------------------------------ datos
    public sealed class Lineas
    {
        public int N;
        public double[] X0, Y0, Z0, X1, Y1, Z1;
        public int[] Prop;
    }

    /// Ángulos en radianes. Para un círculo, Ini/Fin se ignoran.
    public sealed class Arcos
    {
        public int N;
        public double[] CX, CY, CZ, R, Ini, Fin;
        public bool[] Circulo;
        public int[] Prop;
    }

    /// V[i] = x0, y0, bulge0, x1, y1, bulge1, ...
    public sealed class Polis
    {
        public int N;
        public int[] Prop;
        public bool[] Cerrada;
        public double[] Elev;
        public double[][] V;
    }

    public sealed class ResLineas
    {
        public bool[] Borrar;
        public Dictionary<int, (double X0, double Y0, double Z0, double X1, double Y1, double Z1)> Nueva = new();
        public long Pares, Cubetas;
        public double TPrep, TPares, TUnir;
    }

    public sealed class ResArcos
    {
        public bool[] Borrar;
        public Dictionary<int, (double Ini, double Fin)> Nuevo = new();
        public HashSet<int> ACirculo = new();   // arcos que pasan a cubrir la circunferencia entera
    }

    // ------------------------------------------------------------------ unión
    static int Find(int[] p, int a)
    {
        while (p[a] != a) { p[a] = p[p[a]]; a = p[a]; }
        return a;
    }

    static void Union(int[] p, int a, int b)
    {
        a = Find(p, a); b = Find(p, b);
        if (a == b) return;
        if (a < b) p[b] = a; else p[a] = b;
    }

    // ------------------------------------------------------------------ líneas
    static bool PairOk(int i, int j, Lineas E, double[] L, double tol, bool e2e)
    {
        if (L[j] > L[i] || (L[j] == L[i] && j < i)) { int t = i; i = j; j = t; }
        double ax = E.X0[i], ay = E.Y0[i], az = E.Z0[i], Li = L[i];
        double ux = (E.X1[i] - ax) / Li, uy = (E.Y1[i] - ay) / Li, uz = (E.Z1[i] - az) / Li;
        double tt = tol * tol, lo = double.MaxValue, hi = double.MinValue;
        for (int k = 0; k < 2; k++)
        {
            double vx = (k == 0 ? E.X0[j] : E.X1[j]) - ax;
            double vy = (k == 0 ? E.Y0[j] : E.Y1[j]) - ay;
            double vz = (k == 0 ? E.Z0[j] : E.Z1[j]) - az;
            double s = vx * ux + vy * uy + vz * uz;
            double cx = vy * uz - vz * uy, cy = vz * ux - vx * uz, cz = vx * uy - vy * ux;
            if (cx * cx + cy * cy + cz * cz > tt) return false;
            if (s < lo) lo = s;
            if (s > hi) hi = s;
        }
        double ov = Math.Min(hi, Li) - Math.Max(lo, 0.0);
        if (ov > tol) return true;
        return e2e && ov >= -tol;
    }

    public static ResLineas ProcesarLineas(Lineas E, double tol, bool e2e, int hilos)
    {
        int n = E.N;
        var sw = Stopwatch.StartNew();
        var L = new double[n]; var Lxy = new double[n]; var th = new double[n]; var Da = new double[n];
        var po = new ParallelOptions { MaxDegreeOfParallelism = Math.Max(1, hilos) };
        Parallel.For(0, n, po, i =>
        {
            double dx = E.X1[i] - E.X0[i], dy = E.Y1[i] - E.Y0[i], dz = E.Z1[i] - E.Z0[i];
            L[i] = Math.Sqrt(dx * dx + dy * dy + dz * dz);
            Lxy[i] = Math.Sqrt(dx * dx + dy * dy);
            double t = Math.Atan2(dy, dx);
            if (t < 0) t += Math.PI;
            if (t >= Math.PI) t -= Math.PI;
            th[i] = t;
            Da[i] = Lxy[i] > 0 ? Math.Min(Math.PI / 2, 2.0 * tol / Lxy[i] * 1.0001 + 1e-15) : Math.PI / 2;
        });

        var pares = new List<long>();
        void Par(int a, int b) => pares.Add(a < b ? (long)a * n + b : (long)b * n + a);

        // puntos (longitud <= tol): duplicados por posición
        var celdaP = new Dictionary<(int, long, long, long), List<int>>();
        var verticales = new List<int>();
        var segs = new List<int>(n);
        for (int i = 0; i < n; i++)
        {
            if (L[i] <= tol)
            {
                var k = (E.Prop[i], (long)Math.Floor(E.X0[i] / tol), (long)Math.Floor(E.Y0[i] / tol), (long)Math.Floor(E.Z0[i] / tol));
                if (!celdaP.TryGetValue(k, out var l)) celdaP[k] = l = new List<int>();
                l.Add(i);
            }
            else if (Lxy[i] <= tol) verticales.Add(i);
            else segs.Add(i);
        }
        foreach (var kv in celdaP)
        {
            var (p, cx, cy, cz) = kv.Key;
            foreach (int i in kv.Value)
                for (int a = -1; a <= 1; a++) for (int b = -1; b <= 1; b++) for (int c = -1; c <= 1; c++)
                            if (celdaP.TryGetValue((p, cx + a, cy + b, cz + c), out var near))
                                foreach (int j in near)
                                {
                                    double ddx = E.X0[i] - E.X0[j], ddy = E.Y0[i] - E.Y0[j], ddz = E.Z0[i] - E.Z0[j];
                                    if (j > i && ddx * ddx + ddy * ddy + ddz * ddz <= tol * tol) Par(i, j);
                                }
        }
        // verticales puras: por celda XY
        if (verticales.Count > 0)
        {
            double h = Math.Max(tol, 1e-9) * 4;
            var celdaV = new Dictionary<(int, long, long), List<int>>();
            foreach (int i in verticales)
            {
                var k = (E.Prop[i], (long)Math.Floor(E.X0[i] / h), (long)Math.Floor(E.Y0[i] / h));
                if (!celdaV.TryGetValue(k, out var l)) celdaV[k] = l = new List<int>();
                l.Add(i);
            }
            foreach (var kv in celdaV)
            {
                var (p, cx, cy) = kv.Key;
                foreach (int i in kv.Value)
                    for (int a = -1; a <= 1; a++) for (int b = -1; b <= 1; b++)
                            if (celdaV.TryGetValue((p, cx + a, cy + b), out var near))
                                foreach (int j in near)
                                    if (j > i && PairOk(i, j, E, L, tol, e2e)) Par(i, j);
            }
        }

        // registro en cubetas angulares: clave compuesta (prop*NB + cubeta) * n + id
        long total = 0;
        var lo = new long[segs.Count]; var cnt = new int[segs.Count];
        for (int k = 0; k < segs.Count; k++)
        {
            int i = segs[k];
            long a = (long)Math.Floor((th[i] - Da[i]) / W), b = (long)Math.Floor((th[i] + Da[i]) / W);
            lo[k] = a; cnt[k] = (int)(b - a + 1); total += cnt[k];
        }
        var claves = new long[total];
        long pos = 0;
        for (int k = 0; k < segs.Count; k++)
        {
            int i = segs[k];
            for (int c = 0; c < cnt[k]; c++)
            {
                long bk = ((lo[k] + c) % NB + NB) % NB;
                claves[pos++] = ((long)E.Prop[i] * NB + bk) * n + i;
            }
        }
        Array.Sort(claves);
        var grupos = new List<(int ini, int fin)>();
        for (int s = 0; s < claves.Length;)
        {
            long g = claves[s] / n;
            int e = s + 1;
            while (e < claves.Length && claves[e] / n == g) e++;
            if (e - s > 1) grupos.Add((s, e));
            s = e;
        }
        grupos.Sort((x, y) => (y.fin - y.ini).CompareTo(x.fin - x.ini));
        var res = new ResLineas { Cubetas = grupos.Count };
        res.TPrep = sw.Elapsed.TotalSeconds; sw.Restart();

        var bolsa = new ConcurrentBag<List<long>>();
        Parallel.ForEach(System.Collections.Concurrent.Partitioner.Create(0, grupos.Count, Math.Max(1, grupos.Count / (Math.Max(1, hilos) * 16) + 1)), po,
            () => new List<long>(),
            (rango, _, local) =>
            {
                for (int g = rango.Item1; g < rango.Item2; g++)
                    Cubeta(E, L, Lxy, Da, claves, grupos[g].ini, grupos[g].fin, n, tol, e2e, local);
                return local;
            },
            local => bolsa.Add(local));
        foreach (var l in bolsa) pares.AddRange(l);
        res.Pares = pares.Count;
        res.TPares = sw.Elapsed.TotalSeconds; sw.Restart();

        // unir y reemplazar cada componente por su superviviente estirado
        var uf = new int[n];
        for (int i = 0; i < n; i++) uf[i] = i;
        foreach (long q in pares) Union(uf, (int)(q / n), (int)(q % n));
        // componentes en formato compacto (inicio por raíz + lista), en orden de archivo
        var raiz = new int[n]; var tam = new int[n];
        for (int i = 0; i < n; i++) { raiz[i] = Find(uf, i); tam[raiz[i]]++; }
        var comps = new List<int>();                       // raíces con más de un miembro
        var ini = new int[n];
        int acc = 0;
        for (int i = 0; i < n; i++)
            if (raiz[i] == i && tam[i] > 1) { comps.Add(i); ini[i] = acc; acc += tam[i]; }
        var mem = new int[acc]; var lleno = new int[n];
        for (int i = 0; i < n; i++)
        {
            int r = raiz[i];
            if (tam[r] > 1) mem[ini[r] + lleno[r]++] = i;
        }
        res.Borrar = new bool[n];
        var nueva = new (double, double, double, double, double, double)[comps.Count];
        var tiene = new bool[comps.Count];
        Parallel.For(0, comps.Count, po, c =>
        {
            int r = comps[c], o = ini[r], m = tam[r];
            int refi = mem[o];
            for (int q = 0; q < m; q++) { int k = mem[o + q]; if (L[k] > L[refi]) refi = k; }
            for (int q = 1; q < m; q++) res.Borrar[mem[o + q]] = true;
            if (L[refi] <= tol) return;
            double ux = (E.X1[refi] - E.X0[refi]) / L[refi], uy = (E.Y1[refi] - E.Y0[refi]) / L[refi], uz = (E.Z1[refi] - E.Z0[refi]) / L[refi];
            double sLo = double.MaxValue, sHi = double.MinValue;
            (double, double, double) pLo = default, pHi = default;
            for (int q = 0; q < m; q++)
            {
                int k = mem[o + q];
                for (int w = 0; w < 2; w++)
                {
                    double x = w == 0 ? E.X0[k] : E.X1[k], y = w == 0 ? E.Y0[k] : E.Y1[k], z = w == 0 ? E.Z0[k] : E.Z1[k];
                    double s = (x - E.X0[refi]) * ux + (y - E.Y0[refi]) * uy + (z - E.Z0[refi]) * uz;
                    if (s < sLo) { sLo = s; pLo = (x, y, z); }
                    if (s > sHi) { sHi = s; pHi = (x, y, z); }
                }
            }
            int sup = mem[o];
            bool fwd = (E.X1[sup] - E.X0[sup]) * ux + (E.Y1[sup] - E.Y0[sup]) * uy + (E.Z1[sup] - E.Z0[sup]) * uz >= 0;
            var (a, b) = fwd ? (pLo, pHi) : (pHi, pLo);
            nueva[c] = (a.Item1, a.Item2, a.Item3, b.Item1, b.Item2, b.Item3);
            tiene[c] = true;
        });
        res.Nueva = new Dictionary<int, (double, double, double, double, double, double)>(comps.Count);
        for (int c = 0; c < comps.Count; c++) if (tiene[c]) res.Nueva[mem[ini[comps[c]]]] = nueva[c];
        res.TUnir = sw.Elapsed.TotalSeconds;
        return res;
    }

    static void Cubeta(Lineas E, double[] L, double[] Lxy, double[] Da, long[] claves, int ini, int fin, int n,
                       double tol, bool e2e, List<long> pares)
    {
        int m = fin - ini;
        long bk = (claves[ini] / n) % NB;
        double thb = (bk + 0.5) * W, nx = -Math.Sin(thb), ny = Math.Cos(thb), ux = Math.Cos(thb), uy = Math.Sin(thb);
        var rho = new double[m]; var id = new int[m];
        double lmax = 0, dmax = 0;
        for (int k = 0; k < m; k++)
        {
            int i = (int)(claves[ini + k] % n);
            id[k] = i;
            rho[k] = nx * (E.X0[i] + E.X1[i]) / 2 + ny * (E.Y0[i] + E.Y1[i]) / 2;
            if (Lxy[i] > lmax) lmax = Lxy[i];
            if (Da[i] > dmax) dmax = Da[i];
        }
        Array.Sort(rho, id);
        double win = 2 * tol + (W + 2 * dmax) * lmax;
        var t0s = new List<double>(); var t1s = new List<double>(); var ids = new List<int>();
        var act = new List<(double t1, int i)>();
        for (int k = 0; k < m;)
        {
            int e = k + 1;
            while (e < m && rho[e] - rho[e - 1] <= win) e++;
            if (e - k > 1)
            {
                int c = e - k;
                var a0 = new double[c]; var a1 = new double[c]; var ai = new int[c];
                for (int q = 0; q < c; q++)
                {
                    int i = id[k + q];
                    double t0 = ux * E.X0[i] + uy * E.Y0[i], t1 = ux * E.X1[i] + uy * E.Y1[i];
                    a0[q] = Math.Min(t0, t1); a1[q] = Math.Max(t0, t1); ai[q] = i;
                }
                var ord = Enumerable.Range(0, c).ToArray();
                Array.Sort(ord, (x, y) => { int r = a0[x].CompareTo(a0[y]); return r != 0 ? r : ai[x].CompareTo(ai[y]); });
                act.Clear();
                foreach (int q in ord)
                {
                    double t0 = a0[q];
                    act.RemoveAll(z => z.t1 < t0 - 2 * tol);
                    int i = ai[q];
                    foreach (var z in act)
                        if (PairOk(i, z.i, E, L, tol, e2e))
                            pares.Add(i < z.i ? (long)i * n + z.i : (long)z.i * n + i);
                    act.Add((a1[q], i));
                }
            }
            k = e;
        }
    }

    // ------------------------------------------------------------------ arcos y círculos
    public static ResArcos ProcesarArcos(Arcos A, double tol, bool e2e)
    {
        int n = A.N;
        var res = new ResArcos { Borrar = new bool[n] };
        double h = Math.Max(tol, 1e-9) * 4;
        var celda = new Dictionary<(int, long, long, long), List<int>>();
        for (int i = 0; i < n; i++)
        {
            var k = (A.Prop[i], (long)Math.Floor(A.CX[i] / h), (long)Math.Floor(A.CY[i] / h), (long)Math.Floor(A.CZ[i] / h));
            if (!celda.TryGetValue(k, out var l)) celda[k] = l = new List<int>();
            l.Add(i);
        }
        var p = new int[n];
        for (int i = 0; i < n; i++) p[i] = i;
        foreach (var kv in celda)
        {
            var (pr, cx, cy, cz) = kv.Key;
            foreach (int i in kv.Value)
                for (int a = -1; a <= 1; a++) for (int b = -1; b <= 1; b++) for (int c = -1; c <= 1; c++)
                            if (celda.TryGetValue((pr, cx + a, cy + b, cz + c), out var near))
                                foreach (int j in near)
                                {
                                    if (j <= i) continue;
                                    double dx = A.CX[i] - A.CX[j], dy = A.CY[i] - A.CY[j], dz = A.CZ[i] - A.CZ[j];
                                    if (dx * dx + dy * dy + dz * dz <= tol * tol && Math.Abs(A.R[i] - A.R[j]) <= tol) Union(p, i, j);
                                }
        }
        var circ = new Dictionary<int, List<int>>();
        for (int i = 0; i < n; i++)
        {
            int r = Find(p, i);
            if (!circ.TryGetValue(r, out var l)) circ[r] = l = new List<int>();
            l.Add(i);
        }
        const double DOS_PI = 2 * Math.PI;
        foreach (var mem in circ.Values)
        {
            if (mem.Count < 2) continue;
            double atol = tol / A.R[mem[0]];
            int circulo = mem.FirstOrDefault(i => A.Circulo[i], -1);
            if (circulo >= 0)
            {
                foreach (int i in mem) if (i != circulo) res.Borrar[i] = true;
                continue;
            }
            var iv = new Dictionary<int, (double a, double sw)>();
            foreach (int i in mem)
            {
                double a0 = Mod(A.Ini[i], DOS_PI), sw = Mod(A.Fin[i] - A.Ini[i], DOS_PI);
                if (sw == 0) sw = DOS_PI;
                iv[i] = (a0, sw);
            }
            foreach (var comp in UnirArcos(iv, atol, e2e, DOS_PI))
            {
                if (comp.Count < 2) continue;
                int sup = comp[0];
                var (ini, barr) = Cubierto(comp.Select(k => iv[k]).ToList(), atol, DOS_PI);
                if (barr >= DOS_PI - atol) res.ACirculo.Add(sup);
                else res.Nuevo[sup] = (Mod(ini, DOS_PI), Mod(ini + barr, DOS_PI));
                for (int k = 1; k < comp.Count; k++) res.Borrar[comp[k]] = true;
            }
        }
        return res;
    }

    static double Mod(double a, double m) { double r = a % m; return r < 0 ? r + m : r; }

    static List<List<int>> UnirArcos(Dictionary<int, (double a, double sw)> iv, double atol, bool e2e, double vuelta)
    {
        var ext = new List<(double a, double b, int i)>();
        foreach (var kv in iv)
        {
            ext.Add((kv.Value.a, kv.Value.a + kv.Value.sw, kv.Key));
            ext.Add((kv.Value.a + vuelta, kv.Value.a + kv.Value.sw + vuelta, kv.Key));
        }
        ext.Sort();
        var par = iv.Keys.ToDictionary(k => k, k => k);
        int F(int x) { while (par[x] != x) { par[x] = par[par[x]]; x = par[x]; } return x; }
        double s0 = double.NaN, s1 = double.NaN; int last = -1;
        foreach (var (a, b, i) in ext)
        {
            if (!double.IsNaN(s1) && (a < s1 - atol || (e2e && a <= s1 + atol) || (Math.Abs(a - s0) <= atol && Math.Abs(b - s1) <= atol)))
            {
                int x = F(i), y = F(last);
                if (x != y) par[Math.Max(x, y)] = Math.Min(x, y);
                s1 = Math.Max(s1, b);
            }
            else { s0 = a; s1 = b; }
            last = i;
        }
        var comp = new SortedDictionary<int, List<int>>();
        foreach (int i in iv.Keys.OrderBy(k => k))
        {
            int r = F(i);
            if (!comp.TryGetValue(r, out var l)) comp[r] = l = new List<int>();
            l.Add(i);
        }
        return comp.Values.ToList();
    }

    static (double ini, double barr) Cubierto(List<(double a, double sw)> arcs, double atol, double vuelta)
    {
        (double, double)? best = null;
        foreach (var (a_s, _) in arcs)
        {
            var rot = arcs.Select(x => (a: Mod(x.a - a_s, vuelta), x.sw)).OrderBy(x => x.a).ThenBy(x => x.sw).ToList();
            double hi = 0; bool ok = true;
            foreach (var (a0, sw) in rot)
            {
                double a = a0 > vuelta - atol ? a0 - vuelta : a0;
                if (a > hi + atol) { ok = false; break; }
                hi = Math.Max(hi, a + sw);
            }
            if (ok && (best == null || hi > best.Value.Item2)) best = (a_s, Math.Min(hi, vuelta));
        }
        return best ?? (arcs[0].a, arcs[0].sw);
    }

    // ------------------------------------------------------------------ polilíneas
    public static bool[] ProcesarPolis(Polis P, double tol)
    {
        var borrar = new bool[P.N];
        var vistos = new Dictionary<string, int>();
        for (int i = 0; i < P.N; i++)
        {
            string k = P.Prop[i] + "|" + (P.Cerrada[i] ? 1 : 0) + "|" + Math.Round(P.Elev[i] / tol) + "|" + Canon(P.V[i], P.Cerrada[i], tol);
            if (vistos.ContainsKey(k)) borrar[i] = true; else vistos[k] = i;
        }
        return borrar;
    }

    static string Canon(double[] v, bool cerrada, double tol)
    {
        int n = v.Length / 3;
        var pts = new (long x, long y, long b)[n];
        for (int k = 0; k < n; k++) pts[k] = ((long)Math.Round(v[3 * k] / tol), (long)Math.Round(v[3 * k + 1] / tol), (long)Math.Round(v[3 * k + 2] * 1e9));
        var rev = new (long x, long y, long b)[n];
        for (int k = 0; k < n; k++)
        {
            int o = n - 1 - k;                    // vértice original en la posición k invertida
            long b = cerrada ? -pts[(o - 1 + n) % n].b : (o > 0 ? -pts[o - 1].b : 0);
            rev[k] = (pts[o].x, pts[o].y, b);
        }
        string best = null;
        foreach (var s in new[] { pts, rev })
            for (int r = 0; r < (cerrada ? n : 1); r++)
            {
                var sb = new System.Text.StringBuilder();
                for (int k = 0; k < n; k++) { var q = s[(k + r) % n]; sb.Append(q.x).Append(',').Append(q.y).Append(',').Append(q.b).Append(';'); }
                string c = sb.ToString();
                if (best == null || string.CompareOrdinal(c, best) < 0) best = c;
            }
        return best;
    }
}
