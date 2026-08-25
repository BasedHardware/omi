using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;

// win-automation-helper — long-running stdio helper.
// Request  frame: [uint32 LE length][1 byte opcode][UTF-8 JSON payload]
//   opcode 1 = SNAPSHOT  payload = {"windowHandle":"<optional hex/decimal>"}
//   opcode 2 = STEP      payload = a single AutomationStep object
// Response frame: [uint32 LE length][UTF-8 JSON]
//   SNAPSHOT: {"ok":true,"window":{...},"elements":[...]} | {"ok":false,"code","message"}
//   STEP:     {"ok":true} | {"ok":false,"message":"..."}

internal static class Program
{
    private const byte OpSnapshot = 1;
    private const byte OpStep = 2;
    private const byte OpHello = 3;
    // Must match PROTOCOL_VERSION in src/main/automation/protocol.ts. The bridge
    // asserts a match on spawn and fails loudly on drift (e.g. a stale helper).
    private const int ProtocolVersion = 1;
    private const int MaxNodes = 400;
    private const int MaxDepth = 12;

    private static readonly JsonSerializerOptions JsonOpts =
        new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    private static readonly UIA3Automation Automation = new();

    private static async Task<int> Main(string[] args)
    {
        if (args.Contains("--selftest")) return SelfTest();

        var stdin = Console.OpenStandardInput();
        var stdout = Console.OpenStandardOutput();
        while (true)
        {
            var header = await ReadExactly(stdin, 4);
            if (header is null) return 0;
            var len = BitConverter.ToUInt32(header, 0);
            if (len == 0) continue;
            var body = await ReadExactly(stdin, (int)len);
            if (body is null) return 0;

            var opcode = body[0];
            var payload = Encoding.UTF8.GetString(body, 1, body.Length - 1);
            string json;
            try
            {
                json = opcode switch
                {
                    OpHello => Hello(),
                    OpSnapshot => Snapshot(payload),
                    OpStep => RunStep(payload),
                    _ => Err($"unknown opcode {opcode}")
                };
            }
            catch (Exception e)
            {
                json = Err(e.Message);
            }
            await WriteFrame(stdout, json);
        }
    }

    // ───────────────────────── snapshot ─────────────────────────
    private static string Snapshot(string payload)
    {
        var handle = TryGetHandle(payload);
        var hwnd = handle != IntPtr.Zero ? handle : GetForegroundWindow();
        if (hwnd == IntPtr.Zero) return Err("no foreground window", "NO_WINDOW");

        var element = Automation.FromHandle(hwnd);
        if (element is null) return Err("could not attach to window", "NO_WINDOW");

        GetWindowThreadProcessId(hwnd, out var pid);
        var procName = SafeProcName((int)pid);
        var rect = SafeGet(() => element.BoundingRectangle, System.Drawing.Rectangle.Empty);

        var count = 0;
        var root = BuildNode(element, 0, ref count);

        var window = new
        {
            handle = hwnd.ToInt64().ToString(),
            title = SafeGet(() => element.Name ?? "", ""),
            processName = procName,
            rect = new { x = (double)rect.X, y = (double)rect.Y, w = (double)rect.Width, h = (double)rect.Height }
        };
        return JsonSerializer.Serialize(
            new { ok = true, window, elements = root?.children ?? new List<object>() }, JsonOpts);
    }

    private sealed class Node
    {
        public string ref_ = "";
        public string controlType = "";
        public string name = "";
        public string automationId = "";
        public object rect = new { x = 0.0, y = 0.0, w = 0.0, h = 0.0 };
        public List<string> patterns = new();
        public bool enabled;
        public List<object> children = new();
    }

    private static Node? BuildNode(AutomationElement el, int depth, ref int count)
    {
        if (count >= MaxNodes || depth > MaxDepth) return null;

        // IsOffscreen and BoundingRectangle may throw PropertyNotSupportedException
        // on some elements (e.g. raw UIA system items); treat those as on-screen.
        bool offscreen = false;
        try { offscreen = el.IsOffscreen; } catch { /* unsupported — treat on-screen */ }
        System.Drawing.Rectangle r = System.Drawing.Rectangle.Empty;
        bool sized = false;
        try { r = el.BoundingRectangle; sized = r.Width > 0 && r.Height > 0; } catch { /* keep */ }

        // Recurse BEFORE deciding whether to keep this node. A window's real
        // content usually hangs off a client-area container that itself reports a
        // zero/odd bounding rect; pruning that container up front (as we used to)
        // silently dropped the entire content subtree, leaving only the title bar.
        var children = new List<object>();
        foreach (var child in el.FindAllChildren())
        {
            if (count >= MaxNodes) break;
            var c = BuildNode(child, depth + 1, ref count);
            if (c is not null) children.Add(SerializeNode(c));
        }

        // Keep a node if it's visible+sized itself, or it's a structural ancestor
        // of something we kept. Drop only invisible/zero-size leaves.
        if ((offscreen || !sized) && children.Count == 0) return null;

        count++;
        var ct = SafeGet(() => el.ControlType.ToString(), "Unknown");
        var name = SafeGet(() => el.Name ?? "", "");
        var autoId = SafeGet(() => el.AutomationId ?? "", "");
        var enabled = SafeGet(() => el.IsEnabled, true);
        return new Node
        {
            controlType = ct,
            name = name,
            automationId = autoId,
            ref_ = autoId.Length > 0 ? $"a:{autoId}" : $"n:{ct}:{name}",
            rect = new { x = (double)r.X, y = (double)r.Y, w = (double)r.Width, h = (double)r.Height },
            patterns = SupportedPatterns(el),
            enabled = enabled,
            children = children
        };
    }

    // Emit camelCase keys with "ref" (reserved word avoided in the field name).
    private static object SerializeNode(Node n) => new
    {
        @ref = n.ref_,
        controlType = n.controlType,
        name = n.name,
        automationId = n.automationId,
        rect = n.rect,
        patterns = n.patterns,
        enabled = n.enabled,
        children = n.children
    };

    private static T SafeGet<T>(Func<T> getter, T fallback)
    {
        try { return getter(); }
        catch { return fallback; }
    }

    private static List<string> SupportedPatterns(AutomationElement el)
    {
        var list = new List<string>();
        if (el.Patterns.Invoke.IsSupported) list.Add("invoke");
        if (el.Patterns.Value.IsSupported) list.Add("value");
        if (el.Patterns.SelectionItem.IsSupported) list.Add("selectionItem");
        if (el.Patterns.Toggle.IsSupported) list.Add("toggle");
        return list;
    }

    // ───────────────────────── step execution ─────────────────────────
    private static string RunStep(string payload)
    {
        using var doc = JsonDocument.Parse(payload);
        var root = doc.RootElement;
        var type = root.GetProperty("type").GetString();

        switch (type)
        {
            case "focus_window":
            {
                var hwnd = ResolveWindowHandle(root.GetProperty("windowRef").GetString() ?? "");
                if (hwnd == IntPtr.Zero) return Err("window not found");
                // Verify the window actually came to the foreground. A plain
                // SetForeground from a background helper is silently no-op'd by
                // Windows' foreground lock, which would leave a following
                // send_keys typing into whatever else had focus. Fail loudly
                // instead so the plan halts rather than acting on the wrong app.
                if (!ForceForeground(hwnd))
                    return Err("could not bring window to the foreground (it may be elevated or blocked)");
                return Ok();
            }
            case "invoke_element":
            {
                var el = ResolveInActiveWindow(root.GetProperty("elementRef").GetString() ?? "");
                if (el is null) return Err("element not found");
                el.Patterns.Invoke.Pattern.Invoke();
                return Ok();
            }
            case "set_value":
            {
                var el = ResolveInActiveWindow(root.GetProperty("elementRef").GetString() ?? "");
                if (el is null) return Err("element not found");
                el.Patterns.Value.Pattern.SetValue(root.GetProperty("value").GetString() ?? "");
                return Ok();
            }
            case "select_item":
            {
                var el = ResolveInActiveWindow(root.GetProperty("elementRef").GetString() ?? "");
                if (el is null) return Err("element not found");
                el.Patterns.SelectionItem.Pattern.Select();
                return Ok();
            }
            case "toggle":
            {
                var el = ResolveInActiveWindow(root.GetProperty("elementRef").GetString() ?? "");
                if (el is null) return Err("element not found");
                // Honor the desired state: only flip when not already there, so a
                // re-run is idempotent rather than inverting a correct value.
                var want = root.TryGetProperty("state", out var st) && st.ValueKind == JsonValueKind.True;
                var toggle = el.Patterns.Toggle.Pattern;
                var current = toggle.ToggleState.Value == ToggleState.On;
                if (current != want) toggle.Toggle();
                return Ok();
            }
            case "send_keys":
            {
                TypeKeys(root.GetProperty("keys").GetString() ?? "");
                return Ok();
            }
            case "click":
            {
                var refStr = root.TryGetProperty("elementRef", out var er) ? er.GetString() : null;
                if (string.IsNullOrEmpty(refStr)) return Err("click requires elementRef");
                var el = ResolveInActiveWindow(refStr);
                if (el is null) return Err("element not found");
                el.Click();
                return Ok();
            }
            case "wait_for":
            {
                var refStr = root.GetProperty("elementRef").GetString() ?? "";
                var timeout = root.GetProperty("timeoutMs").GetInt32();
                var deadline = DateTime.UtcNow.AddMilliseconds(timeout);
                while (DateTime.UtcNow < deadline)
                {
                    if (ResolveInActiveWindow(refStr) is not null) return Ok();
                    Thread.Sleep(100);
                }
                return Err("wait_for timed out");
            }
            default:
                return Err($"unknown step type {type}");
        }
    }

    // Plain text is sent as exact Unicode via SendInput (KEYEVENTF_UNICODE), which
    // preserves case and shifted symbols regardless of keyboard layout — typing
    // char-by-char through FlaUI dropped the shift state (e.g. "Hi!" → "hi").
    // Named keys ({ENTER}, {TAB}, …) still go through FlaUI's virtual-key path;
    // modifier chords are rejected upstream by capabilities.ts.
    private static void TypeKeys(string keys)
    {
        var i = 0;
        while (i < keys.Length)
        {
            if (keys[i] == '{')
            {
                var end = keys.IndexOf('}', i);
                if (end > i)
                {
                    PressNamed(keys.Substring(i + 1, end - i - 1));
                    i = end + 1;
                    continue;
                }
            }
            SendUnicodeChar(keys[i]);
            i++;
        }
    }

    // Emit one character as a Unicode key down+up pair. wVk=0 + KEYEVENTF_UNICODE
    // tells Windows to deliver the literal code point, so case/symbols survive.
    private static void SendUnicodeChar(char ch)
    {
        var inputs = new INPUT[2];
        inputs[0].type = INPUT_KEYBOARD;
        inputs[0].U.ki.wVk = 0;
        inputs[0].U.ki.wScan = ch;
        inputs[0].U.ki.dwFlags = KEYEVENTF_UNICODE;
        inputs[1].type = INPUT_KEYBOARD;
        inputs[1].U.ki.wVk = 0;
        inputs[1].U.ki.wScan = ch;
        inputs[1].U.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP;
        var sent = SendInput(2, inputs, Marshal.SizeOf<INPUT>());
        if (sent != 2)
            Console.Error.WriteLine($"[send_keys] SendInput sent={sent} err={Marshal.GetLastWin32Error()} cb={Marshal.SizeOf<INPUT>()}");
    }

    private static void PressNamed(string name)
    {
        var key = name switch
        {
            "ENTER" => VirtualKeyShort.ENTER,
            "TAB" => VirtualKeyShort.TAB,
            "ESC" => VirtualKeyShort.ESCAPE,
            "BACKSPACE" => VirtualKeyShort.BACK,
            "DELETE" => VirtualKeyShort.DELETE,
            "UP" => VirtualKeyShort.UP,
            "DOWN" => VirtualKeyShort.DOWN,
            "LEFT" => VirtualKeyShort.LEFT,
            "RIGHT" => VirtualKeyShort.RIGHT,
            "HOME" => VirtualKeyShort.HOME,
            "END" => VirtualKeyShort.END,
            "SPACE" => VirtualKeyShort.SPACE,
            _ => (VirtualKeyShort?)null
        };
        if (key is not null) Keyboard.Press(key.Value);
    }

    // ───────────────────────── element resolution ─────────────────────────
    // Resolve a windowRef (numeric handle, or title substring) to an HWND.
    private static IntPtr ResolveWindowHandle(string windowRef)
    {
        if (long.TryParse(windowRef, out var h) && h != 0) return new IntPtr(h);
        var match = Automation.GetDesktop().FindAllChildren()
            .FirstOrDefault(w => (w.Name ?? "").Contains(windowRef, StringComparison.OrdinalIgnoreCase));
        if (match is null) return IntPtr.Zero;
        try { return match.Properties.NativeWindowHandle.Value; }
        catch { return IntPtr.Zero; }
    }

    // Bring a window to the foreground past Windows' foreground lock, which
    // otherwise silently ignores SetForegroundWindow calls from a process that
    // doesn't already own the foreground. We temporarily attach our input queue
    // (and the current foreground thread's) to the target's so the call is
    // honored, then confirm the switch actually took.
    private static bool ForceForeground(IntPtr hwnd)
    {
        if (hwnd == IntPtr.Zero) return false;
        if (IsIconic(hwnd)) ShowWindow(hwnd, SW_RESTORE);
        if (GetForegroundWindow() == hwnd) return true;

        var targetThread = GetWindowThreadProcessId(hwnd, out _);
        var foreThread = GetWindowThreadProcessId(GetForegroundWindow(), out _);
        var thisThread = GetCurrentThreadId();

        var attachedFore = foreThread != targetThread && AttachThreadInput(foreThread, targetThread, true);
        var attachedThis = thisThread != targetThread && AttachThreadInput(thisThread, targetThread, true);
        try
        {
            BringWindowToTop(hwnd);
            SetForegroundWindow(hwnd);
        }
        finally
        {
            if (attachedFore) AttachThreadInput(foreThread, targetThread, false);
            if (attachedThis) AttachThreadInput(thisThread, targetThread, false);
        }

        // Give the OS a moment to apply focus, then confirm it actually switched.
        for (var i = 0; i < 10; i++)
        {
            if (GetForegroundWindow() == hwnd) return true;
            Thread.Sleep(30);
        }
        return GetForegroundWindow() == hwnd;
    }

    private static AutomationElement? ResolveInActiveWindow(string refStr)
    {
        var hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero) return null;
        var root = Automation.FromHandle(hwnd);
        if (root is null) return null;

        if (refStr.StartsWith("a:"))
        {
            var id = refStr.Substring(2);
            return root.FindFirstDescendant(cf => cf.ByAutomationId(id));
        }
        if (refStr.StartsWith("n:"))
        {
            var rest = refStr.Substring(2);
            var sep = rest.IndexOf(':');
            if (sep < 0) return null;
            var ct = rest.Substring(0, sep);
            var name = rest.Substring(sep + 1);
            return root.FindAllDescendants(cf => cf.ByName(name))
                .FirstOrDefault(e => e.ControlType.ToString() == ct);
        }
        return null;
    }

    // ───────────────────────── stdio framing ─────────────────────────
    private static async Task<byte[]?> ReadExactly(Stream s, int n)
    {
        var buf = new byte[n];
        var read = 0;
        while (read < n)
        {
            var r = await s.ReadAsync(buf.AsMemory(read, n - read));
            if (r == 0) return null;
            read += r;
        }
        return buf;
    }

    private static async Task WriteFrame(Stream s, string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        await s.WriteAsync(BitConverter.GetBytes((uint)bytes.Length));
        await s.WriteAsync(bytes);
        await s.FlushAsync();
    }

    private static string Hello() =>
        JsonSerializer.Serialize(new { ok = true, protocolVersion = ProtocolVersion }, JsonOpts);

    private static string Ok() => JsonSerializer.Serialize(new { ok = true }, JsonOpts);
    private static string Err(string message, string code = "STEP_ERROR") =>
        JsonSerializer.Serialize(new { ok = false, code, message }, JsonOpts);

    private static IntPtr TryGetHandle(string payload)
    {
        try
        {
            using var doc = JsonDocument.Parse(payload);
            if (doc.RootElement.TryGetProperty("windowHandle", out var h) &&
                long.TryParse(h.GetString(), out var v) && v != 0)
                return new IntPtr(v);
        }
        catch { /* empty/absent payload → foreground window */ }
        return IntPtr.Zero;
    }

    private static string SafeProcName(int pid)
    {
        try { return System.Diagnostics.Process.GetProcessById(pid).ProcessName; }
        catch { return ""; }
    }

    private static int SelfTest()
    {
        var snap = Snapshot("{}");
        Console.Error.WriteLine($"[selftest] snapshot len={snap.Length} head={snap[..Math.Min(160, snap.Length)]}");
        return 0;
    }

    private const int SW_RESTORE = 9;

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool BringWindowToTop(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsIconic(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, [MarshalAs(UnmanagedType.Bool)] bool fAttach);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public InputUnion U;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct HARDWAREINPUT
    {
        public uint uMsg;
        public ushort wParamL;
        public ushort wParamH;
    }
}
