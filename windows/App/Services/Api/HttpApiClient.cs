using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading;
using System.Threading.Tasks;
using Omi.Windows.App.Infrastructure;

namespace Omi.Windows.App.Services.Api;

public class HttpApiClient
{
    private readonly HttpClient _httpClient;
    private readonly IAuthTokenProvider _authTokenProvider;

    public HttpApiClient(HttpClient httpClient, IAuthTokenProvider authTokenProvider)
    {
        _httpClient = httpClient;
        _authTokenProvider = authTokenProvider;
        _httpClient.BaseAddress ??= new Uri(EnvConfig.ApiBaseUrl);
    }

    public async Task<T?> GetAsync<T>(string path, bool requireAuth = true, CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, path);
        await EnrichHeadersAsync(request, requireAuth, ct).ConfigureAwait(false);
        using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<T>(cancellationToken: ct).ConfigureAwait(false);
    }

    public async Task<TResponse?> PostJsonAsync<TRequest, TResponse>(
        string path,
        TRequest body,
        bool requireAuth = true,
        CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Content = JsonContent.Create(body)
        };

        await EnrichHeadersAsync(request, requireAuth, ct).ConfigureAwait(false);
        using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct)
            .ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength is 0)
        {
            return default;
        }
        return await response.Content.ReadFromJsonAsync<TResponse>(cancellationToken: ct).ConfigureAwait(false);
    }

    private async Task EnrichHeadersAsync(HttpRequestMessage request, bool requireAuth, CancellationToken ct)
    {
        request.Headers.Add("X-App-Platform", "windows");
        request.Headers.Add("X-App-Version", "0.1.0");
        request.Headers.Add("X-Request-Start-Time", (DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0).ToString("F3"));

        if (!requireAuth)
        {
            return;
        }

        var token = await _authTokenProvider.GetIdTokenAsync(ct).ConfigureAwait(false);
        if (!string.IsNullOrWhiteSpace(token))
        {
            request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);
        }
    }
}

