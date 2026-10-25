// Programa de consola: lee un DXF, corre el núcleo (OverkillCore.cs) con 1..N hilos y compara la huella.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;

static partial class Overkill
{
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
