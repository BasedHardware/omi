using System.Text;
using System.Text.Json;
using NAudio.CoreAudioApi;

// win-audio-helper — long-running stdio helper that mutes the default output
// device while push-to-talk is capturing, mirroring the macOS
// SystemAudioMuteController ("mute audio while dictating", Wispr Flow style).
//
// Request  frame: [uint32 LE length][1 byte opcode][UTF-8 JSON payload]
//   opcode 1 = MUTE     payload = {} (ignored)
//   opcode 2 = RESTORE  payload = {} (ignored)
//   opcode 3 = HELLO    payload = {} (ignored)
// Response frame: [uint32 LE length][UTF-8 JSON]
//   MUTE:    {"ok":true,"muted":true}
//            {"ok":true,"muted":false,"reason":"not_playing|user_muted|no_device","peak":0.0}
//            {"ok":false,"message":"..."}
//   RESTORE: {"ok":true,"muted":false}  | {"ok":false,"message":"..."}
//   HELLO:   {"ok":true,"protocolVersion":2}
//
// Mute contract (idempotent, exactly like the macOS controller):
//   * mute only when audio is ACTUALLY playing (MasterPeakValue > ~0), and
//   * NEVER touch a device the user has already muted themselves, and
//   * remember the device we muted so RESTORE unmutes exactly that device and
//     a second MUTE while already holding one is a no-op.
// RESTORE is unconditional + idempotent: a no-op when we hold no mute.
internal static class Program
{
    private const byte OpMute = 1;
    private const byte OpRestore = 2;
    private const byte OpHello = 3;

    // Must match PROTOCOL_VERSION in src/main/audio/protocol.ts. The bridge
    // asserts a match on spawn and logs loudly on drift (a stale helper build).
    private const int ProtocolVersion = 2;

    // MasterPeakValue is exactly 0 when nothing is rendering; a tiny epsilon
    // guards against float denormal noise. This is the point-in-time "is the
    // device running somewhere" check (macOS kAudioDevicePropertyDeviceIsRunning-
    // Somewhere), sampled once at mute time — not continuously.
    private const float PeakThreshold = 0.0001f;

    // Sampling window for the "is audio playing" test: up to 10 samples, 15ms
    // apart (~150ms worst case, and only when NOTHING is playing — the moment a
    // sample clears the threshold we mute immediately). The worst case is the
    // silent case, where being 150ms late costs nothing because there is nothing
    // to mute. Well inside the PTT hold, which is ≥350ms before capture even
    // starts, and it runs off the PTT path anyway (fire-and-forget IPC).
    private const int PeakSamples = 10;
    private const int PeakSampleIntervalMs = 15;

    private static readonly JsonSerializerOptions JsonOpts =
        new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };

    // The device WE muted (null = we currently hold no mute). Kept alive while
    // muted so RESTORE unmutes this exact endpoint even if the default output
    // device changes mid-hold. Guarded by Gate — MUTE/RESTORE can interleave.
    private static readonly object Gate = new();
    private static MMDevice? _mutedDevice;

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
            string json;
            try
            {
                json = opcode switch
                {
                    OpHello => Hello(),
                    OpMute => Mute(),
                    OpRestore => Restore(),
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

    // ───────────────────────── mute / restore ─────────────────────────
    private static string Mute()
    {
        lock (Gate)
        {
            if (_mutedDevice != null) return Ok(true); // already holding a mute — no-op

            MMDevice device;
            try
            {
                using var enumerator = new MMDeviceEnumerator();
                device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Console);
            }
            catch
            {
                return Skipped("no_device", 0f); // no default output device
            }

            try
            {
                // "never touch a device the user has muted themselves" — checked
                // FIRST: it's the more meaningful reason, and a muted endpoint
                // meters ~0 anyway, so checking peak first would mislabel every
                // user-muted device as "not_playing". Leaving _mutedDevice null
                // makes the paired RESTORE a no-op too, so we never un-mute them.
                if (device.AudioEndpointVolume.Mute)
                {
                    device.Dispose();
                    return Skipped("user_muted", 0f);
                }
                // "mute only if audio is actually playing". Sampled over a short
                // window, not a single instant: MasterPeakValue reports the peak of
                // the LAST device period, and a caller that happens to sample on a
                // quiet period (or between the render client's buffer fills) reads
                // 0 even while a stream is playing. One sample is a coin-flip; the
                // max over ~150ms is not. (Found live: the app's warm helper read a
                // single 0 and silently refused to mute while a tone was playing.)
                var peak = PeakOverWindow(device);
                if (peak <= PeakThreshold)
                {
                    device.Dispose();
                    return Skipped("not_playing", peak);
                }
                device.AudioEndpointVolume.Mute = true;
                _mutedDevice = device; // keep alive; RESTORE unmutes THIS device
                return Ok(true);
            }
            catch (Exception e)
            {
                TryDispose(device);
                return Err(e.Message);
            }
        }
    }

    private static string Restore()
    {
        lock (Gate)
        {
            var device = _mutedDevice;
            if (device == null) return Ok(false); // we hold no mute — no-op
            _mutedDevice = null;
            try
            {
                device.AudioEndpointVolume.Mute = false;
            }
            catch
            {
                // Device unplugged/vanished between mute and restore — nothing to do.
            }
            TryDispose(device);
            return Ok(false);
        }
    }

    // Peak over a short sampling window. WASAPI's MasterPeakValue is the peak of
    // the last device period only, so it legitimately reads 0 between a render
    // client's buffer fills — polling it once is not a reliable "is anything
    // playing" test. Returns as soon as it sees audio, so the common case (media
    // playing) costs a single sample and never delays the mute.
    private static float PeakOverWindow(MMDevice device)
    {
        var peak = 0f;
        for (var i = 0; i < PeakSamples; i++)
        {
            var v = device.AudioMeterInformation.MasterPeakValue;
            if (v > peak) peak = v;
            if (peak > PeakThreshold) return peak; // playing — decide immediately
            Thread.Sleep(PeakSampleIntervalMs);
        }
        return peak;
    }

    private static void TryDispose(MMDevice device)
    {
        try { device.Dispose(); }
        catch { /* already gone */ }
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

    private static string Ok(bool muted) =>
        JsonSerializer.Serialize(new { ok = true, muted }, JsonOpts);

    // A deliberate no-op, with the reason it happened. Muting silently declining
    // to act is a support nightmare ("PTT doesn't mute my music") — the bridge
    // logs this, so a refusal is always explainable.
    private static string Skipped(string reason, float peak) =>
        JsonSerializer.Serialize(new { ok = true, muted = false, reason, peak }, JsonOpts);

    private static string Err(string message) =>
        JsonSerializer.Serialize(new { ok = false, message }, JsonOpts);

    private static int SelfTest()
    {
        try
        {
            using var enumerator = new MMDeviceEnumerator();
            using var device = enumerator.GetDefaultAudioEndpoint(DataFlow.Render, Role.Console);
            Console.Error.WriteLine(
                $"[selftest] default render '{device.FriendlyName}' " +
                $"peak={device.AudioMeterInformation.MasterPeakValue:0.0000} " +
                $"muted={device.AudioEndpointVolume.Mute}");
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"[selftest] failed: {e.Message}");
            return 1;
        }
    }
}
