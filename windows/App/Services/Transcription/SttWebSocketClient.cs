using System;
using System.Net.WebSockets;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Omi.Windows.App.Infrastructure;
using Omi.Windows.App.Services.Api;

namespace Omi.Windows.App.Services.Transcription;

public sealed class SttWebSocketClient : IAsyncDisposable
{
    private readonly IAuthTokenProvider _authTokenProvider;
    private ClientWebSocket? _socket;

    public event Func<string, Task>? OnTranscriptJson;

    public SttWebSocketClient(IAuthTokenProvider authTokenProvider)
    {
        _authTokenProvider = authTokenProvider;
    }

    public async Task<bool> ConnectAsync(string language = "multi", CancellationToken ct = default)
    {
        if (_socket is { State: WebSocketState.Open })
        {
            return true;
        }

        var token = await _authTokenProvider.GetIdTokenAsync(ct).ConfigureAwait(false);
        if (string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        var apiUri = new Uri(EnvConfig.ApiBaseUrl);
        var wsScheme = apiUri.Scheme == "https" ? "wss" : "ws";
        var builder = new UriBuilder(apiUri)
        {
            Scheme = wsScheme,
            Path = "v4/listen",
            Query = $"language={language}&sample_rate=16000&codec=pcm16&channels=1&source=windows"
        };

        try
        {
            _socket?.Dispose();
            _socket = new ClientWebSocket();
            _socket.Options.SetRequestHeader("Authorization", $"Bearer {token}");

            await _socket.ConnectAsync(builder.Uri, ct).ConfigureAwait(false);

            _ = Task.Run(() => ReceiveLoopAsync(_socket, ct), ct);

            return _socket.State == WebSocketState.Open;
        }
        catch (Exception ex)
        {
            if (OnTranscriptJson is not null)
            {
                await OnTranscriptJson.Invoke($"{{\"type\":\"error\",\"message\":\"WebSocket connect failed: {ex.Message}\"}}")
                    .ConfigureAwait(false);
            }
            _socket?.Dispose();
            _socket = null;
            return false;
        }
    }

    public async Task SendAudioAsync(byte[] buffer, CancellationToken ct = default)
    {
        if (_socket is not { State: WebSocketState.Open })
        {
            return;
        }

        await _socket.SendAsync(buffer, WebSocketMessageType.Binary, true, ct).ConfigureAwait(false);
    }

    private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken ct)
    {
        var buffer = new byte[64 * 1024];
        while (!ct.IsCancellationRequested && socket.State == WebSocketState.Open)
        {
            var result = await socket.ReceiveAsync(buffer, ct).ConfigureAwait(false);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                break;
            }

            var json = System.Text.Encoding.UTF8.GetString(buffer, 0, result.Count);
            if (OnTranscriptJson is not null)
            {
                await OnTranscriptJson.Invoke(json).ConfigureAwait(false);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_socket is { State: WebSocketState.Open } s)
        {
            await s.CloseAsync(WebSocketCloseStatus.NormalClosure, "Disposing", CancellationToken.None)
                .ConfigureAwait(false);
        }

        _socket?.Dispose();
        _socket = null;
    }
}

