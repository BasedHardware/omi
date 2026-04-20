using System;
using System.Net.Http;
using System.Net.Http.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Win32;
using Omi.Windows.App.Infrastructure;
using Omi.Windows.App.Services.Api;

namespace Omi.Windows.App.Services.Auth;

public class AuthService : IAuthTokenProvider
{
    private const string RegistryKeyPath = @"Software\Omi\WindowsApp";
    private const string TokenValueName = "IdToken";
    private const string DefaultRedirectUri = "omi://auth/callback";

    private readonly HttpClient _httpClient;

    private string? _cachedToken;

    public AuthService(HttpClient httpClient)
    {
        _httpClient = httpClient;
        _httpClient.BaseAddress ??= new Uri(EnvConfig.ApiBaseUrl);
        _cachedToken = LoadTokenFromRegistry();
    }

    public bool IsAuthenticated => !string.IsNullOrWhiteSpace(_cachedToken);

    /// <summary>
    /// Ouvre la page de connexion Omi dans le navigateur.
    /// </summary>
    public void OpenAuthPage(string provider = "apple", string? redirectUri = null)
    {
        var redirect = string.IsNullOrWhiteSpace(redirectUri) ? DefaultRedirectUri : redirectUri!;
        var baseUrl = EnvConfig.ApiBaseUrl.TrimEnd('/');
        var url = $"{baseUrl}/v1/auth/authorize?provider={provider}&redirect_uri={Uri.EscapeDataString(redirect)}";

        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true,
            });
        }
        catch
        {
            // Ignorer les erreurs d’ouverture de navigateur, l’utilisateur pourra copier l’URL manuellement si besoin.
        }
    }

    /// <summary>
    /// Mode développement / debug : accepte un token déjà prêt (Firebase ID token).
    /// </summary>
    public async Task<bool> SignInWithPastedTokenAsync(string rawToken, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(rawToken))
        {
            return false;
        }

        _cachedToken = rawToken.Trim();
        SaveTokenToRegistry(_cachedToken);
        return true;
    }

    /// <summary>
    /// Échange un auth_code Omi contre un Firebase ID token en utilisant
    /// /v1/auth/token (backend Python) puis Firebase Identity Toolkit.
    /// </summary>
    public async Task<bool> SignInWithAuthCodeAsync(string authCode, string? redirectUri = null, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(authCode))
        {
            return false;
        }

        var redirect = string.IsNullOrWhiteSpace(redirectUri) ? DefaultRedirectUri : redirectUri!;

        // 1) Échanger le code contre un custom_token via /v1/auth/token
        using var form = new FormUrlEncodedContent(new[]
        {
            new KeyValuePair<string?, string?>("grant_type", "authorization_code"),
            new KeyValuePair<string?, string?>("code", authCode.Trim()),
            new KeyValuePair<string?, string?>("redirect_uri", redirect),
            new KeyValuePair<string?, string?>("use_custom_token", "true"),
        });

        using var tokenResponse = await _httpClient.PostAsync("v1/auth/token", form, ct).ConfigureAwait(false);
        if (!tokenResponse.IsSuccessStatusCode)
        {
            return false;
        }

        var tokenPayload = await tokenResponse.Content.ReadFromJsonAsync<AuthTokenResponse>(cancellationToken: ct)
            .ConfigureAwait(false);
        if (tokenPayload is null || string.IsNullOrWhiteSpace(tokenPayload.CustomToken))
        {
            return false;
        }

        // 2) Échanger custom_token contre Firebase ID token via Identity Toolkit
        if (string.IsNullOrWhiteSpace(EnvConfig.FirebaseApiKey))
        {
            // Sans clé Firebase côté client, on ne peut pas obtenir d’ID token
            return false;
        }

        var firebaseUrl =
            $"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={EnvConfig.FirebaseApiKey}";

        var firebaseBody = new FirebaseSignInWithCustomTokenRequest
        {
            Token = tokenPayload.CustomToken,
            ReturnSecureToken = true,
        };

        using var firebaseResponse =
            await _httpClient.PostAsJsonAsync(firebaseUrl, firebaseBody, ct).ConfigureAwait(false);
        if (!firebaseResponse.IsSuccessStatusCode)
        {
            return false;
        }

        var firebasePayload =
            await firebaseResponse.Content.ReadFromJsonAsync<FirebaseSignInWithCustomTokenResponse>(
                cancellationToken: ct).ConfigureAwait(false);
        if (firebasePayload is null || string.IsNullOrWhiteSpace(firebasePayload.IdToken))
        {
            return false;
        }

        _cachedToken = firebasePayload.IdToken;
        SaveTokenToRegistry(_cachedToken);
        return true;
    }

    public Task SignOutAsync()
    {
        _cachedToken = null;
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RegistryKeyPath);
            key?.DeleteValue(TokenValueName, false);
        }
        catch
        {
            // Ignorer les erreurs de nettoyage
        }

        return Task.CompletedTask;
    }

    public Task<string?> GetIdTokenAsync(CancellationToken ct = default)
    {
        return Task.FromResult(_cachedToken);
    }

    private sealed class AuthTokenResponse
    {
        public string? Provider { get; set; }
        public string? IdToken { get; set; }
        public string? AccessToken { get; set; }
        public string? ProviderId { get; set; }
        public string? TokenType { get; set; }
        public int ExpiresIn { get; set; }
        public string? CustomToken { get; set; }
    }

    private sealed class FirebaseSignInWithCustomTokenRequest
    {
        public string Token { get; set; } = string.Empty;
        public bool ReturnSecureToken { get; set; }
    }

    private sealed class FirebaseSignInWithCustomTokenResponse
    {
        public string? IdToken { get; set; }
        public string? RefreshToken { get; set; }
        public string? LocalId { get; set; }
        public string? ExpiresIn { get; set; }
    }

    private static string? LoadTokenFromRegistry()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(RegistryKeyPath);
            return key?.GetValue(TokenValueName) as string;
        }
        catch
        {
            return null;
        }
    }

    private static void SaveTokenToRegistry(string token)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RegistryKeyPath);
            key?.SetValue(TokenValueName, token);
        }
        catch
        {
            // Ignorer les erreurs de persistance ; l’app restera fonctionnelle pour la session courante
        }
    }
}

