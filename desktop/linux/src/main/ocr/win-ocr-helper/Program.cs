using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage.Streams;

// win-ocr-helper — long-running stdio helper.
// Request  frame: [uint32 LE length][1 byte opcode][payload...]
//   opcode 1 = OCR     payload = JPEG bytes
//   opcode 2 = WINDOW  payload = empty
// Response frame: [uint32 LE length][UTF-8 JSON]
//   OCR:    {"ok":true,"fullText":"...","lines":[{text,x,y,w,h,confidence}]}
//        or {"ok":false,"code":"NO_LANGUAGE|DECODE_FAILED|HELPER_ERROR","message":"..."}
//   WINDOW: {"app":"...","title":"...","pid":123,"processName":"..."}

internal static class Program
{
    private const byte OpOcr = 1;
    private const byte OpWindow = 2;

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private static async Task<int> Main(string[] args)
    {
        if (args.Contains("--selftest"))
        {
            return await SelfTest();
        }

        var stdin = Console.OpenStandardInput();
        var stdout = Console.OpenStandardOutput();

        while (true)
        {
            var header = await ReadExactly(stdin, 4);
            if (header is null) return 0; // EOF — parent closed the pipe.
            var len = BitConverter.ToUInt32(header, 0);
            if (len == 0) continue;
            var body = await ReadExactly(stdin, (int)len);
            if (body is null) return 0;

            var opcode = body[0];
            var payload = new byte[body.Length - 1];
            Array.Copy(body, 1, payload, 0, payload.Length);

            string json;
            try
            {
                json = opcode switch
                {
                    OpOcr => await RunOcr(payload),
                    OpWindow => RunWindowInfo(),
                    _ => ErrorJson("HELPER_ERROR", $"unknown opcode {opcode}")
                };
            }
            catch (Exception e)
            {
                json = ErrorJson("HELPER_ERROR", e.Message);
            }

            await WriteFrame(stdout, json);
        }
    }

    private static async Task<byte[]?> ReadExactly(Stream s, int n)
    {
        var buf = new byte[n];
        var read = 0;
        while (read < n)
        {
            var r = await s.ReadAsync(buf.AsMemory(read, n - read));
            if (r == 0) return null; // EOF
            read += r;
        }
        return buf;
    }

    private static async Task WriteFrame(Stream s, string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        var header = BitConverter.GetBytes((uint)bytes.Length);
        await s.WriteAsync(header);
        await s.WriteAsync(bytes);
        await s.FlushAsync();
    }

    private static string ErrorJson(string code, string message) =>
        JsonSerializer.Serialize(new { ok = false, code, message }, JsonOpts);

    private static async Task<string> RunOcr(byte[] jpeg)
    {
        var engine = OcrEngine.TryCreateFromUserProfileLanguages();
        if (engine is null)
        {
            return ErrorJson("NO_LANGUAGE",
                "No Windows OCR language pack is installed.");
        }

        SoftwareBitmap bitmap;
        try
        {
            using var stream = new InMemoryRandomAccessStream();
            var writer = new DataWriter(stream);
            writer.WriteBytes(jpeg);
            await writer.StoreAsync();
            writer.DetachStream();
            stream.Seek(0);
            var decoder = await BitmapDecoder.CreateAsync(stream);
            bitmap = await decoder.GetSoftwareBitmapAsync();
        }
        catch (Exception e)
        {
            return ErrorJson("DECODE_FAILED", e.Message);
        }

        var width = bitmap.PixelWidth;
        var height = bitmap.PixelHeight;
        var result = await engine.RecognizeAsync(bitmap);
        bitmap.Dispose();

        var lines = result.Lines.Select(line =>
        {
            // Bounding rect = union of word rects (OcrLine has no rect of its own).
            double minX = double.MaxValue, minY = double.MaxValue, maxX = 0, maxY = 0;
            double confSum = 0;
            var count = 0;
            foreach (var word in line.Words)
            {
                var r = word.BoundingRect;
                minX = Math.Min(minX, r.X);
                minY = Math.Min(minY, r.Y);
                maxX = Math.Max(maxX, r.X + r.Width);
                maxY = Math.Max(maxY, r.Y + r.Height);
                confSum += 1.0; // Windows OCR exposes no per-word confidence; report 1.0.
                count++;
            }
            if (count == 0) { minX = minY = 0; }
            return new
            {
                text = line.Text,
                x = minX / width,
                y = minY / height,
                w = (maxX - minX) / width,
                h = (maxY - minY) / height,
                confidence = count > 0 ? confSum / count : 0.0
            };
        }).ToArray();

        var fullText = string.Join("\n", result.Lines.Select(l => l.Text));
        return JsonSerializer.Serialize(new { ok = true, fullText, lines }, JsonOpts);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    private static string RunWindowInfo()
    {
        var hwnd = GetForegroundWindow();
        var sb = new StringBuilder(512);
        GetWindowText(hwnd, sb, sb.Capacity);
        var title = sb.ToString();

        GetWindowThreadProcessId(hwnd, out var pid);
        var processName = "";
        var app = "";
        try
        {
            var proc = Process.GetProcessById((int)pid);
            processName = proc.ProcessName;
            app = string.IsNullOrWhiteSpace(proc.MainModule?.ModuleName)
                ? processName
                : Path.GetFileNameWithoutExtension(proc.MainModule!.ModuleName);
        }
        catch
        {
            // Access-denied (elevated/foreign process) — keep what we have.
        }

        return JsonSerializer.Serialize(
            new { app = string.IsNullOrEmpty(app) ? processName : app, title, pid = (int)pid, processName },
            JsonOpts);
    }

    private static async Task<int> SelfTest()
    {
        var win = RunWindowInfo();
        Console.Error.WriteLine($"[selftest] window: {win}");

        var engine = OcrEngine.TryCreateFromUserProfileLanguages();
        Console.Error.WriteLine(engine is null
            ? "[selftest] OCR: NO_LANGUAGE (no language pack installed)"
            : $"[selftest] OCR: engine ok ({engine.RecognizerLanguage.DisplayName})");

        if (engine is not null)
        {
            var jpeg = MakeWhiteJpeg(64, 32);
            var ocr = await RunOcr(jpeg);
            Console.Error.WriteLine($"[selftest] ocr round-trip: {ocr[..Math.Min(120, ocr.Length)]}");
        }
        await Task.CompletedTask;
        return 0;
    }

    private static byte[] MakeWhiteJpeg(int w, int h)
    {
        using var stream = new InMemoryRandomAccessStream();
        var encoder = BitmapEncoder.CreateAsync(BitmapEncoder.JpegEncoderId, stream)
            .AsTask().GetAwaiter().GetResult();
        var pixels = new byte[w * h * 4];
        Array.Fill(pixels, (byte)255);
        encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore,
            (uint)w, (uint)h, 96, 96, pixels);
        encoder.FlushAsync().AsTask().GetAwaiter().GetResult();
        stream.Seek(0);
        var bytes = new byte[stream.Size];
        var reader = new DataReader(stream);
        reader.LoadAsync((uint)stream.Size).AsTask().GetAwaiter().GetResult();
        reader.ReadBytes(bytes);
        return bytes;
    }
}
