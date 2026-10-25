// Prueba de ContornosCore.cs: compara el área de cada contorno (exterior menos islas) con <dxf>.esperado.txt
// y comprueba que 1 y N hilos den exactamente lo mismo.
using System;
using System.Globalization;
using System.IO;
using System.Linq;

static class Programa
{
    static int Main(string[] args)
    {
        if (args.Length == 0) { Console.WriteLine("uso: HatchCs archivo.dxf [--threads 1,4] [--reps 3]"); return 1; }
        string dxf = args[0];
        int reps = 3; int[] ths = { 1, Environment.ProcessorCount };
        for (int k = 1; k < args.Length - 1; k++)
        {
            if (args[k] == "--reps") reps = int.Parse(args[k + 1]);
            if (args[k] == "--threads") ths = args[k + 1].Split(',').Select(int.Parse).ToArray();
        }
        var L = Overkill.Read(dxf);
        string b = Path.ChangeExtension(dxf, null);
        var ci = CultureInfo.InvariantCulture;
        var pts = File.ReadAllLines(b + ".puntos.txt").Where(l => l.Trim() != "").Select(l => l.Split(',')).ToArray();
        double[] px = pts.Select(p => double.Parse(p[0], ci)).ToArray(), py = pts.Select(p => double.Parse(p[1], ci)).ToArray();
        double[] esp = File.Exists(b + ".esperado.txt") ? File.ReadAllLines(b + ".esperado.txt").Where(l => l.Trim() != "").Select(l => double.Parse(l, ci)).ToArray() : null;
        Console.WriteLine($"lineas={L.N} puntos={px.Length} nucleos={Environment.ProcessorCount}");
        string refHuella = null;
        foreach (var t in ths)
        {
            Contornos.Resultado best = null; double bestT = double.MaxValue;
            for (int r = 0; r < reps + 1; r++)
            {
                var sw = System.Diagnostics.Stopwatch.StartNew();
                var R = Contornos.Calcular(L.X0, L.Y0, L.X1, L.Y1, px, py, t);
                double tt = sw.Elapsed.TotalSeconds;
                if (r > 0 && tt < bestT) { bestT = tt; best = R; }
            }
            int ok = 0, mal = 0, sin = 0;
            var h = new System.Text.StringBuilder();
            for (int i = 0; i < px.Length; i++)
            {
                if (best.Exterior[i] == null) { sin++; h.Append("-\n"); continue; }
                double a = Contornos.Area(best.Exterior[i]) + best.Islas[i].Sum(Contornos.Area);
                h.Append(string.Join(",", best.Exterior[i].Select(v => v.ToString("R", ci)))).Append('|').Append(best.Islas[i].Length).Append('\n');
                if (esp != null) { if (Math.Abs(a - esp[i]) <= 1e-6 * Math.Max(1, esp[i])) ok++; else { mal++; if (mal <= 5) Console.WriteLine($"  punto {i} ({px[i]},{py[i]}): area {a} esperada {esp[i]}"); } }
            }
            var sha = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.ASCII.GetBytes(h.ToString())))[..16];
            refHuella ??= sha;
            var tm = string.Join(", ", best.Tiempos.Select(kv => $"{kv.Key} {kv.Value:F3}"));
            Console.WriteLine($"hilos={t,2} total={bestT:F3}s ({tm}) vertices={best.Vertices} aristas={best.Aristas} ciclos={best.Ciclos} piezas={best.Piezas} " +
                              $"bien={ok} mal={mal} sin_contorno={sin} {(sha == refHuella ? "IGUAL" : "DISTINTO")} {sha}");
        }
        return 0;
    }
}
