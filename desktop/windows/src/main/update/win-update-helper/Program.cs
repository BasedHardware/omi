// Native Windows update-progress dialog. Shows a Task Dialog (the modern native
// Windows dialog, same family as a message box) with a live progress bar, and
// updates it from commands on stdin sent by the Electron main process:
//   progress <0-100>   set the bar
//   done               close the dialog
// stdin EOF (parent exited) also closes it. argv[0] is the version string.
using System;
using System.Threading;
using System.Windows.Forms;

static class Program
{
    static volatile int _percent = 0;
    static volatile bool _done = false;

    [STAThread]
    static void Main(string[] args)
    {
        string version = args.Length > 0 ? args[0] : "update";
        Application.EnableVisualStyles();

        var page = new TaskDialogPage
        {
            Caption = "Omi",
            Heading = $"Downloading Omi {version}",
            Text = "You can keep using Omi while it downloads. Omi will restart to finish updating.",
            AllowCancel = true
        };
        var progress = new TaskDialogProgressBar { Minimum = 0, Maximum = 100, Value = 0 };
        page.ProgressBar = progress;
        var hideButton = new TaskDialogButton("Hide");
        page.Buttons.Add(hideButton);

        // The Task Dialog runs its own modal message loop; a WinForms Timer on that
        // (UI) thread is the safe way to apply progress posted from the stdin thread.
        page.Created += (_, _) =>
        {
            var timer = new System.Windows.Forms.Timer { Interval = 100 };
            timer.Tick += (_, _) =>
            {
                if (_done)
                {
                    timer.Stop();
                    hideButton.PerformClick(); // closes the dialog
                    return;
                }
                int p = Math.Clamp(_percent, 0, 100);
                if (progress.Value != p) progress.Value = p;
            };
            timer.Start();
        };

        var reader = new Thread(() =>
        {
            try
            {
                string? line;
                while ((line = Console.In.ReadLine()) != null)
                {
                    line = line.Trim();
                    if (line == "done") break;
                    if (line.StartsWith("progress ") &&
                        int.TryParse(line.AsSpan(9).Trim(), out int v))
                    {
                        _percent = v;
                    }
                }
            }
            catch { /* stdin closed / parse error */ }
            _done = true; // 'done' or stdin EOF (parent exited) → close the dialog
        })
        { IsBackground = true };
        reader.Start();

        TaskDialog.ShowDialog(page);
    }
}
