using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Omi.Windows.App.Services.Audio;
using Omi.Windows.App.Services.Transcription;

namespace Omi.Windows.App.ViewModels;

public sealed class CaptureViewModel : INotifyPropertyChanged
{
    private readonly AudioCaptureService _audioCaptureService;
    private readonly SttWebSocketClient _sttClient;
    private readonly CancellationTokenSource _cts = new();

    private bool _isRecording;
    private string _lastTranscript = string.Empty;

    public event PropertyChangedEventHandler? PropertyChanged;

    public bool IsRecording
    {
        get => _isRecording;
        private set
        {
            if (value == _isRecording) return;
            _isRecording = value;
            OnPropertyChanged();
        }
    }

    public string LastTranscript
    {
        get => _lastTranscript;
        private set
        {
            if (value == _lastTranscript) return;
            _lastTranscript = value;
            OnPropertyChanged();
        }
    }

    public CaptureViewModel(AudioCaptureService audioCaptureService, SttWebSocketClient sttClient)
    {
        _audioCaptureService = audioCaptureService;
        _sttClient = sttClient;

        _audioCaptureService.Configure(async bytes =>
        {
            await _sttClient.SendAudioAsync(bytes, _cts.Token).ConfigureAwait(false);
        });

        _sttClient.OnTranscriptJson += HandleTranscriptJsonAsync;
    }

    public async Task StartAsync()
    {
        if (IsRecording)
        {
            return;
        }

        if (!await _sttClient.ConnectAsync(ct: _cts.Token).ConfigureAwait(false))
        {
            return;
        }

        var ok = await _audioCaptureService.StartAsync(_cts.Token).ConfigureAwait(false);
        if (ok)
        {
            IsRecording = true;
        }
    }

    public async Task StopAsync()
    {
        if (!IsRecording)
        {
            return;
        }

        await _audioCaptureService.StopAsync().ConfigureAwait(false);
        IsRecording = false;
    }

    private Task HandleTranscriptJsonAsync(string json)
    {
        // Phase 1 : on stocke simplement le dernier message JSON reçu
        try
        {
            using var doc = JsonDocument.Parse(json);
            LastTranscript = doc.RootElement.ToString();
        }
        catch
        {
            LastTranscript = json;
        }

        return Task.CompletedTask;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}

