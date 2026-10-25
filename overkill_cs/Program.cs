// OVERKILL (modo AutoCAD) en C#: misma regla que overkill_core.acad_seq/acad_par en Python.
// Receta: leer -> copiar (columnas) -> calcular en paralelo por particiones -> reensamblar.
// Los hilos comparten memoria: no se copia nada a cada trabajador.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;

static class Overkill
{
    const double ATOL = 1e-10;   // corte angular medido en AutoCAD 2027

    // ------------------------------------------------------------ leer / copiar
    public sealed class Lines
    {
        public int N;
        public double[] X0, Y0, X1, Y1;
        public string[] Layer, Ltype;
        public int[] Color;
    }

    public static Lines Read(string path)
    {
        var x0 = new List<double>(); var y0 = new List<double>();
        var x1 = new List<double>(); var y1 = new List<double>();
        var lay = new List<string>(); var lt = new List<string>(); var col = new List<int>();
        var rows = File.ReadAllLines(path);
        string section = null; bool inLine = false;
        string cl = "0", clt = "BYLAYER"; int cc = 256; double a = 0, b = 0, c = 0, d = 0;
        var ci = CultureInfo.InvariantCulture;
        void Flush() { x0.Add(a); y0.Add(b); x1.Add(c); y1.Add(d); lay.Add(cl); lt.Add(clt); col.Add(cc); }
        for (int i = 0; i + 1 < rows.Length; i += 2)
        {
            int code = int.Parse(rows[i].Trim(), ci); string val = rows[i + 1].Trim();
            if (code == 0)
            {
                if (inLine) { Flush(); inLine = false; }
                if (val == "SECTION") { section = rows[i + 3].Trim(); i += 2; }
                else if (val == "ENDSEC") section = null;
                else if (section == "ENTITIES" && val == "LINE")
                { inLine = true; cl = "0"; clt = "BYLAYER"; cc = 256; }
            }
            else if (inLine)
            {
                switch (code)
                {
                    case 8: cl = val; break;
                    case 6: clt = val; break;
                    case 62: cc = int.Parse(val, ci); break;
                    case 10: a = double.Parse(val, ci); break;
                    case 20: b = double.Parse(val, ci); break;
                    case 11: c = double.Parse(val, ci); break;
                    case 21: d = double.Parse(val, ci); break;
                }
            }
        }
        return new Lines { N = x0.Count, X0 = x0.ToArray(), Y0 = y0.ToArray(), X1 = x1.ToArray(), Y1 = y1.ToArray(),
                           Layer = lay.ToArray(), Ltype = lt.ToArray(), Color = col.ToArray() };
    }

    // propiedades -> un entero por línea (igualdad = mismas propiedades)
    public static long[] EncodeProps(Lines L, bool ignoreLayer)
    {
        var ids = new Dictionary<(string, int, string), long>();
        var p = new long[L.N];
        for (int i = 0; i < L.N; i++)
        {
            var k = (ignoreLayer ? "" : L.Layer[i], L.Color[i], L.Ltype[i]);
            if (!ids.TryGetValue(k, out var v)) { v = ids.Count; ids[k] = v; }
            p[i] = v;
        }
        return p;
    }

    // ------------------------------------------------------------ cálculo
    public static long AngleBucket(double x0, double y0, double x1, double y1)
    {
        double dx = x1 - x0, dy = y1 - y0;
        if (dx == 0 && dy == 0) return -1;
        double th = Math.Atan2(dy, dx);
        if (th < 0) th += Math.PI;
        if (th >= Math.PI) th -= Math.PI;
        return (long)Math.Floor(th / ATOL);
    }

    struct It { public double TMin, TMax; public int Idx, EMinI, EMinW, EMaxI, EMaxW; }

    // salida: (surv, i_min, e_min, i_max, e_max) en 'res[surv]'
    static void Group(Lines L, List<int> ids, long b, double tol, bool e2e, int[,] res)
    {
        if (b < 0)
        {
            var seen = new Dictionary<(double, double), int>();
            foreach (var i in ids)
            {
                var k = (Math.Round(L.X0[i] / tol), Math.Round(L.Y0[i] / tol));
                seen[k] = seen.TryGetValue(k, out var v) ? Math.Min(v, i) : i;
            }
            foreach (var i in seen.Values) Put(res, i, i, 0, i, 1);
            return;
        }
        double th = (b + 0.5) * ATOL, ux = Math.Cos(th), uy = Math.Sin(th);
        var recs = new (double rho, int i, It it)[ids.Count];
        for (int k = 0; k < ids.Count; k++)
        {
            int i = ids[k];
            double x0 = L.X0[i], y0 = L.Y0[i], x1 = L.X1[i], y1 = L.Y1[i];
            double rho = ux * (y0 + y1) / 2 - uy * (x0 + x1) / 2;
            double t0 = ux * x0 + uy * y0, t1 = ux * x1 + uy * y1;
            var it = t0 <= t1
                ? new It { TMin = t0, TMax = t1, Idx = i, EMinI = i, EMinW = 0, EMaxI = i, EMaxW = 1 }
                : new It { TMin = t1, TMax = t0, Idx = i, EMinI = i, EMinW = 1, EMaxI = i, EMaxW = 0 };
            recs[k] = (rho, i, it);
        }
        Array.Sort(recs, (p, q) => p.rho != q.rho ? p.rho.CompareTo(q.rho) : p.i.CompareTo(q.i));
        var cluster = new List<It>();
        double last = double.NaN;
        foreach (var r in recs)
        {
            if (!double.IsNaN(last) && r.rho - last > tol) { Sweep(cluster, tol, e2e, res); cluster.Clear(); }
            cluster.Add(r.it); last = r.rho;
        }
        Sweep(cluster, tol, e2e, res);
    }

    static void Sweep(List<It> items, double tol, bool e2e, int[,] res)
    {
        items.Sort((p, q) => p.TMin != q.TMin ? p.TMin.CompareTo(q.TMin)
                           : p.TMax != q.TMax ? p.TMax.CompareTo(q.TMax) : p.Idx.CompareTo(q.Idx));
        var s = items[0];
        double sMin = s.TMin, sMax = s.TMax; int surv = s.Idx;
        int eMinI = s.EMinI, eMinW = s.EMinW, eMaxI = s.EMaxI, eMaxW = s.EMaxW;
        for (int k = 1; k < items.Count; k++)
        {
            var it = items[k];
            if (it.TMin < sMax - tol || (e2e && it.TMin <= sMax + tol) ||
                (Math.Abs(it.TMin - sMin) <= tol && Math.Abs(it.TMax - sMax) <= tol))
            {
                if (it.TMax > sMax + tol || (Math.Abs(it.TMax - sMax) <= tol && it.EMaxI < eMaxI && it.TMax >= sMax))
                { eMaxI = it.EMaxI; eMaxW = it.EMaxW; }
                sMax = Math.Max(sMax, it.TMax);
                surv = Math.Min(surv, it.Idx);
            }
            else
            {
                Put(res, surv, eMinI, eMinW, eMaxI, eMaxW);
                sMin = it.TMin; sMax = it.TMax; surv = it.Idx;
                eMinI = it.EMinI; eMinW = it.EMinW; eMaxI = it.EMaxI; eMaxW = it.EMaxW;
            }
        }
        Put(res, surv, eMinI, eMinW, eMaxI, eMaxW);
    }

    static void Put(int[,] res, int surv, int a, int wa, int b, int wb)
    { res[surv, 0] = 1; res[surv, 1] = a; res[surv, 2] = wa; res[surv, 3] = b; res[surv, 4] = wb; }

    // threads = 1 -> todo en el hilo actual (secuencial); >1 -> Parallel.For
    public static int[,] Run(Lines L, long[] props, double tol, bool e2e, int threads, Dictionary<string, double> tm)
    {
        var sw = Stopwatch.StartNew();
        int n = L.N;
        var po = new ParallelOptions { MaxDegreeOfParallelism = threads };
        var bkt = new long[n];
        int nparts = Math.Max(1, threads * 8);
        var pid = new int[n];
        // 1) clave por línea (paralelo, memoria compartida)
        void Key(int i)
        {
            bkt[i] = AngleBucket(L.X0[i], L.Y0[i], L.X1[i], L.Y1[i]);
            ulong h = (ulong)bkt[i] * 0x9E3779B97F4A7C15UL ^ (ulong)props[i] * 0xC2B2AE3D27D4EB4FUL;
            pid[i] = (int)((h ^ (h >> 29)) % (ulong)nparts);
        }
        if (threads == 1) for (int i = 0; i < n; i++) Key(i);
        else Parallel.For(0, n, po, Key);
        double tKey = sw.Elapsed.TotalSeconds;
        // 2) repartir: orden por partición (conteo, O(n))
        var start = new int[nparts + 1];
        for (int i = 0; i < n; i++) start[pid[i] + 1]++;
        for (int p = 0; p < nparts; p++) start[p + 1] += start[p];
        var order = new int[n]; var fill = (int[])start.Clone();
        for (int i = 0; i < n; i++) order[fill[pid[i]]++] = i;
        double tPart = sw.Elapsed.TotalSeconds;
        // 3) calcular cada partición; cada sobreviviente escribe su propia fila de 'res'
        var res = new int[n, 5];
        void Part(int p)
        {
            var groups = new Dictionary<(long, long), List<int>>();
            for (int k = start[p]; k < start[p + 1]; k++)
            {
                int i = order[k]; var key = (props[i], bkt[i]);
                if (!groups.TryGetValue(key, out var g)) groups[key] = g = new List<int>();
                g.Add(i);
            }
            foreach (var kv in groups) Group(L, kv.Value, kv.Key.Item2, tol, e2e, res);
        }
        if (threads == 1) for (int p = 0; p < nparts; p++) Part(p);
        else Parallel.For(0, nparts, po, Part);
        double tComp = sw.Elapsed.TotalSeconds;
        if (tm != null) { tm["clave"] = tKey; tm["repartir"] = tPart - tKey; tm["calculo"] = tComp - tPart; tm["total"] = tComp; }
        return res;   // reensamblar = recorrer 'res' en orden de índice (sin ordenar)
    }

    public static (int count, string sha) Fingerprint(int[,] res)
    {
        var sb = new StringBuilder(); int count = 0;
        for (int i = 0; i < res.GetLength(0); i++)
            if (res[i, 0] == 1)
            { count++; sb.Append(i).Append(' ').Append(res[i, 1]).Append(' ').Append(res[i, 2]).Append(' ')
                .Append(res[i, 3]).Append(' ').Append(res[i, 4]).Append('\n'); }
        var h = SHA256.HashData(Encoding.ASCII.GetBytes(sb.ToString()));
        return (count, Convert.ToHexString(h).ToLowerInvariant());
    }

    static int Main(string[] args)
    {
        if (args.Length == 0) { Console.WriteLine("uso: OverkillCs archivo.dxf [--e2e] [--ignore-layer] [--threads 1,2,4,16] [--reps 3]"); return 1; }
        string path = args[0]; bool e2e = args.Contains("--e2e"), ign = args.Contains("--ignore-layer");
        int reps = 3; int[] ths = { 1, 2, 4, 8, 16 };
        for (int k = 1; k < args.Length - 1; k++)
        {
            if (args[k] == "--reps") reps = int.Parse(args[k + 1]);
            if (args[k] == "--threads") ths = args[k + 1].Split(',').Select(int.Parse).ToArray();
        }
        var sw = Stopwatch.StartNew();
        var L = Read(path);
        double tRead = sw.Elapsed.TotalSeconds;
        var props = EncodeProps(L, ign);
        Console.WriteLine($"lineas={L.N} leer={tRead:F3}s nucleos={Environment.ProcessorCount}");
        string refSha = null;
        foreach (var t in ths)
        {
            Dictionary<string, double> best = null; int[,] res = null;
            for (int r = 0; r < reps + 1; r++)           // la primera pasada calienta el JIT
            {
                var tm = new Dictionary<string, double>();
                res = Run(L, props, 1e-6, e2e, t, tm);
                if (r > 0 && (best == null || tm["total"] < best["total"])) best = tm;
            }
            var (count, sha) = Fingerprint(res);
            refSha ??= sha;
            Console.WriteLine($"hilos={t,2} quedan={count} total={best["total"]:F3}s (clave {best["clave"]:F3}, repartir {best["repartir"]:F3}, calculo {best["calculo"]:F3}) {(sha == refSha ? "IGUAL" : "DISTINTO")} sha={sha[..16]}");
        }
        return 0;
    }
}
