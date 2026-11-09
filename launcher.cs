using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Program {
    [STAThread]
    static void Main() {
        try {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string candidate = Path.Combine(localAppData, "Python", "pythoncore-3.14-64", "pythonw.exe");
            string exe = File.Exists(candidate) ? candidate : "pythonw.exe";

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = exe;
            psi.Arguments = "-X utf8 -m automation.review_loop.gui";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            Process.Start(psi);
        } catch (Exception ex) {
            MessageBox.Show("Không thể khởi động Agent GUI:\n" + ex.Message, "Agent GUI", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
