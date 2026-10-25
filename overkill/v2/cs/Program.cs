// Consola de OVERKILL v2: lee un DXF, aplica el núcleo y cuenta por capa.
// Uso: OverkillV2 dibujo.dxf [--e2e] [--hilos N] [--csv res.csv] [--bench 1,2,4,8,16]
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

static class Programa
{
    sealed class Dxf
    {
        public List<string> Tipo = new(), Capa = new();
        public List<int> Idx = new();                   // índice dentro de su tipo
        public HashSet<string> Bloq = new();
        public OverkillV2.Lineas L; public OverkillV2.Arcos A; public OverkillV2.Polis P;
        public List<int> LEnt = new(), AEnt = new(), PEnt = new();   // tipo -> entidad
    }

    static Dxf Leer(string path)
    {
        var ci = CultureInfo.InvariantCulture;
        var d = new Dxf();
        var props = new Dictionary<string, int>();
        var lx0 = new List<double>(); var ly0 = new List<double>(); var lz0 = new List<double>();
        var lx1 = new List<double>(); var ly1 = new List<double>(); var lz1 = new List<double>(); var lp = new List<int>();
        var cx = new List<double>(); var cy = new List<double>(); var cz = new List<double>(); var cr = new List<double>();
        var ca = new List<double>(); var cb = new List<double>(); var cc = new List<bool>(); var cp = new List<int>();
        var pp = new List<int>(); var pc = new List<bool>(); var pe = new List<double>(); var pv = new List<double[]>();
        string sec = null, tipo = null, capaTabla = null;
        bool enCapa = false;
        var g = new Dictionary<int, string>();
        var verts = new List<double>();
        var pr = new string[11];
        int Pid(string extra)
        {
            string k = string.Join("\u0001", pr) + "\u0001" + extra;
            if (!props.TryGetValue(k, out int v)) { v = props.Count; props[k] = v; }
            return v;
        }
        void Flush()
        {
            if (tipo == null) return;
            double G(int c, double def = 0) => g.TryGetValue(c, out var s) ? double.Parse(s, ci) : def;
            string capa = pr[0];
            string normal = pr[10];
            d.Tipo.Add(tipo); d.Capa.Add(capa);
            int e = d.Tipo.Count - 1;
            if (tipo == "LINE")
            {
                d.Idx.Add(lx0.Count); d.LEnt.Add(e);
                lx0.Add(G(10)); ly0.Add(G(20)); lz0.Add(G(30)); lx1.Add(G(11)); ly1.Add(G(21)); lz1.Add(G(31)); lp.Add(Pid(""));
            }
            else if (tipo == "ARC" || tipo == "CIRCLE")
            {
                d.Idx.Add(cx.Count); d.AEnt.Add(e);
                cx.Add(G(10)); cy.Add(G(20)); cz.Add(G(30)); cr.Add(G(40));
                ca.Add(G(50) * Math.PI / 180); cb.Add(G(51) * Math.PI / 180); cc.Add(tipo == "CIRCLE"); cp.Add(Pid(normal));
            }
            else
            {
                d.Idx.Add(pp.Count); d.PEnt.Add(e);
                pp.Add(Pid(normal)); pc.Add(g.TryGetValue(70, out var f) && (int.Parse(f, ci) & 1) == 1);
                pe.Add(G(38)); pv.Add(verts.ToArray());
            }
            tipo = null;
        }
        using var sr = new StreamReader(path, Encoding.UTF8, false, 1 << 20);
        while (true)
        {
            string a = sr.ReadLine(), b = sr.ReadLine();
            if (a == null || b == null) break;
            int code = int.Parse(a.Trim(), ci); string val = b.Trim();
            if (code == 0)
            {
                Flush();
                enCapa = false;
                if (val == "SECTION") { sr.ReadLine(); sec = sr.ReadLine().Trim(); }
                else if (val == "ENDSEC") sec = null;
                else if (sec == "ENTITIES" && (val == "LINE" || val == "ARC" || val == "CIRCLE" || val == "LWPOLYLINE"))
                {
                    tipo = val; g.Clear(); verts.Clear();
                    pr[0] = "0"; for (int k = 1; k < 10; k++) pr[k] = ""; pr[10] = "0,0,1";
                }
                else if (sec == "TABLES" && val == "LAYER") { enCapa = true; capaTabla = null; }
                continue;
            }
            if (enCapa)
            {
                if (code == 2) capaTabla = val;
                else if (code == 70 && capaTabla != null && (int.Parse(val, ci) & 5) != 0) d.Bloq.Add(capaTabla);
                continue;
            }
            if (tipo == null) continue;
            switch (code)
            {
                case 8: pr[0] = val; break;
                case 62: pr[1] = val; break;
                case 420: pr[2] = val; break;
                case 6: pr[3] = val; break;
                case 48: pr[4] = val; break;
                case 370: pr[5] = val; break;
                case 39: pr[6] = val; break;
                case 440: pr[7] = val; break;
                case 390: pr[8] = val; break;
                case 347: pr[9] = val; break;
                case 210: pr[10] = val + pr[10].Substring(pr[10].IndexOf(',')); break;
                case 220: { var s = pr[10].Split(','); pr[10] = s[0] + "," + val + "," + s[2]; break; }
                case 230: { var s = pr[10].Split(','); pr[10] = s[0] + "," + s[1] + "," + val; break; }
                default:
                    if (tipo == "LWPOLYLINE")
                    {
                        if (code == 10) { verts.Add(double.Parse(val, ci)); verts.Add(0); verts.Add(0); }
                        else if (code == 20) verts[verts.Count - 2] = double.Parse(val, ci);
                        else if (code == 42) verts[verts.Count - 1] = double.Parse(val, ci);
                        else g[code] = val;
                    }
                    else g[code] = val;
                    break;
            }
        }
        Flush();
        // las entidades en capas bloqueadas o congeladas no entran al cálculo: se les pone una
        // propiedad única para que nunca se emparejen
        int unico = props.Count + 1;
        for (int k = 0; k < d.LEnt.Count; k++) if (d.Bloq.Contains(d.Capa[d.LEnt[k]])) lp[k] = -(unico++);
        for (int k = 0; k < d.AEnt.Count; k++) if (d.Bloq.Contains(d.Capa[d.AEnt[k]])) cp[k] = -(unico++);
        for (int k = 0; k < d.PEnt.Count; k++) if (d.Bloq.Contains(d.Capa[d.PEnt[k]])) pp[k] = -(unico++);
        // normalizar propiedades a enteros >= 0
        int Norm(int v) => v >= 0 ? v : props.Count - v;
        d.L = new OverkillV2.Lineas { N = lx0.Count, X0 = lx0.ToArray(), Y0 = ly0.ToArray(), Z0 = lz0.ToArray(), X1 = lx1.ToArray(), Y1 = ly1.ToArray(), Z1 = lz1.ToArray(), Prop = lp.Select(Norm).ToArray() };
        d.A = new OverkillV2.Arcos { N = cx.Count, CX = cx.ToArray(), CY = cy.ToArray(), CZ = cz.ToArray(), R = cr.ToArray(), Ini = ca.ToArray(), Fin = cb.ToArray(), Circulo = cc.ToArray(), Prop = cp.Select(Norm).ToArray() };
        d.P = new OverkillV2.Polis { N = pp.Count, Prop = pp.Select(Norm).ToArray(), Cerrada = pc.ToArray(), Elev = pe.ToArray(), V = pv.ToArray() };
        return d;
    }

    static int Main(string[] args)
    {
        if (args.Length == 0) { Console.WriteLine("uso: OverkillV2 dibujo.dxf [--e2e] [--hilos N] [--csv res.csv] [--bench 1,2,4]"); return 1; }
        string path = args[0], csv = null, bench = null, borrFile = null;
        bool e2e = args.Contains("--e2e");
        int hilos = Environment.ProcessorCount;
        for (int k = 1; k < args.Length; k++)
        {
            if (args[k] == "--hilos") hilos = int.Parse(args[++k]);
            else if (args[k] == "--csv") csv = args[++k];
            else if (args[k] == "--bench") bench = args[++k];
            else if (args[k] == "--borradas") borrFile = args[++k];
        }
        const double tol = 1e-6;
        var sw = Stopwatch.StartNew();
        var d = Leer(path);
        double tLeer = sw.Elapsed.TotalSeconds;
        Console.WriteLine($"leído {d.Tipo.Count:N0} entidades ({d.L.N:N0} LINE, {d.A.N:N0} ARC/CIRCLE, {d.P.N:N0} LWPOLYLINE) en {tLeer:F2} s");
        var lista = bench != null ? bench.Split(',').Select(int.Parse).ToArray() : new[] { hilos };
        string huella0 = null;
        foreach (int h in lista)
        {
            for (int rep = 0; rep < (bench != null ? 3 : 1); rep++)
            {
                sw.Restart();
                var rl = OverkillV2.ProcesarLineas(d.L, tol, e2e, h);
                double t1 = sw.Elapsed.TotalSeconds;
                var ra = OverkillV2.ProcesarArcos(d.A, tol, e2e);
                var rp = OverkillV2.ProcesarPolis(d.P, tol);
                double t = sw.Elapsed.TotalSeconds;
                int borr = rl.Borrar.Count(x => x) + ra.Borrar.Count(x => x) + rp.Count(x => x);
                string huella = Huella(rl, ra, rp);
                huella0 ??= huella;
                Console.WriteLine($"hilos {h,2}: {t:F3} s (líneas {t1:F3}: preparar {rl.TPrep:F3} pares {rl.TPares:F3} unir {rl.TUnir:F3}; {rl.Pares:N0} pares) " +
                                  $"quedan {d.Tipo.Count - borr:N0}  huella {huella}{(huella == huella0 ? "" : "  ¡DISTINTA!")}");
                if (borrFile != null && h == lista[0] && rep == 0)
                {
                    var bl = new List<int>();
                    for (int k = 0; k < d.L.N; k++) if (rl.Borrar[k]) bl.Add(d.LEnt[k]);
                    for (int k = 0; k < d.A.N; k++) if (ra.Borrar[k]) bl.Add(d.AEnt[k]);
                    for (int k = 0; k < d.P.N; k++) if (rp[k]) bl.Add(d.PEnt[k]);
                    bl.Sort();
                    File.WriteAllLines(borrFile, bl.Select(x => x.ToString()));
                }
                if (csv != null && h == lista[0] && rep == 0)
                {
                    var cnt = new Dictionary<string, int>();
                    foreach (var c in d.Capa.Distinct()) cnt[c] = 0;
                    for (int k = 0; k < d.L.N; k++) if (!rl.Borrar[k]) cnt[d.Capa[d.LEnt[k]]]++;
                    for (int k = 0; k < d.A.N; k++) if (!ra.Borrar[k]) cnt[d.Capa[d.AEnt[k]]]++;
                    for (int k = 0; k < d.P.N; k++) if (!rp[k]) cnt[d.Capa[d.PEnt[k]]]++;
                    File.WriteAllLines(csv, cnt.OrderBy(x => x.Key, StringComparer.Ordinal).Select(x => $"{x.Key};{x.Value}"));
                }
            }
        }
        return 0;
    }

    static string Huella(OverkillV2.ResLineas rl, OverkillV2.ResArcos ra, bool[] rp)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < rl.Borrar.Length; i++) if (rl.Borrar[i]) sb.Append(i).Append(',');
        foreach (var kv in rl.Nueva.OrderBy(x => x.Key)) sb.Append(kv.Key).Append(kv.Value.ToString()).Append(';');
        for (int i = 0; i < ra.Borrar.Length; i++) if (ra.Borrar[i]) sb.Append(i).Append(',');
        foreach (var kv in ra.Nuevo.OrderBy(x => x.Key)) sb.Append(kv.Key).Append(kv.Value.ToString()).Append(';');
        for (int i = 0; i < rp.Length; i++) if (rp[i]) sb.Append(i).Append(',');
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sb.ToString())))[..12];
    }
}
