// Informe común: escribe en la línea de comandos y añade lo mismo a <dibujo>.acadparalelo.txt
// (en accoreconsole es la forma cómoda de recoger los tiempos).
using System;
using System.IO;
using Autodesk.AutoCAD.ApplicationServices.Core;

namespace AcadParalelo
{
    static class Informe
    {
        public static void Escribir(string text)
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            doc.Editor.WriteMessage(text);
            try
            {
                if (Path.IsPathRooted(doc.Name))
                    File.AppendAllText(Path.ChangeExtension(doc.Name, ".acadparalelo.txt"), $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}]{text}\r\n");
            }
            catch (Exception) { }   // el informe en archivo es opcional
        }
    }
}
