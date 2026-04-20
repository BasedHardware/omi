using System;
using System.Threading;
using System.Threading.Tasks;
using NAudio.Wave;

namespace Omi.Windows.App.Services.Audio;

public sealed class AudioCaptureService : IAsyncDisposable
{
    private const int TargetSampleRate = 16000;
    private const int Channels = 1;

    private WaveInEvent? _waveIn;
    private WaveFormat? _inputFormat;
    private readonly object _sync = new();
    private Func<byte[], Task>? _onAudioFrame;

    public bool IsCapturing { get; private set; }

    public void Configure(Func<byte[], Task> onAudioFrame)
    {
        _onAudioFrame = onAudioFrame;
    }

    public Task<bool> StartAsync(CancellationToken ct = default)
    {
        lock (_sync)
        {
            if (IsCapturing)
            {
                return Task.FromResult(true);
            }

            _waveIn = new WaveInEvent
            {
                WaveFormat = new WaveFormat(TargetSampleRate, 16, Channels),
                BufferMilliseconds = 100
            };

            _inputFormat = _waveIn.WaveFormat;
            _waveIn.DataAvailable += OnDataAvailable;
            _waveIn.RecordingStopped += OnRecordingStopped;
            _waveIn.StartRecording();
            IsCapturing = true;
        }

        return Task.FromResult(true);
    }

    public Task StopAsync()
    {
        lock (_sync)
        {
            if (!IsCapturing || _waveIn is null)
            {
                return Task.CompletedTask;
            }

            _waveIn.StopRecording();
        }

        return Task.CompletedTask;
    }

    private void OnDataAvailable(object? sender, WaveInEventArgs e)
    {
        var handler = _onAudioFrame;
        if (handler is null || e.BytesRecorded == 0)
        {
            return;
        }

        // e.Buffer est déjà en PCM16 mono à 16 kHz, on peut envoyer tel quel
        var buffer = new byte[e.BytesRecorded];
        Array.Copy(e.Buffer, buffer, e.BytesRecorded);

        _ = handler(buffer);
    }

    private void OnRecordingStopped(object? sender, StoppedEventArgs e)
    {
        lock (_sync)
        {
            if (_waveIn is not null)
            {
                _waveIn.DataAvailable -= OnDataAvailable;
                _waveIn.RecordingStopped -= OnRecordingStopped;
                _waveIn.Dispose();
                _waveIn = null;
            }

            IsCapturing = false;
        }
    }

    public async ValueTask DisposeAsync()
    {
        await StopAsync().ConfigureAwait(false);
    }
}

