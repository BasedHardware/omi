using System;

namespace Omi.Windows.App.Infrastructure;

public static class EnvConfig
{
    // Point par défaut vers la prod, surchargeable via variable d'env
    private const string DefaultApiBaseUrl = "https://api.omi.me/";
    private const string DefaultFirebaseApiKey = "";

    public static string ApiBaseUrl
    {
        get
        {
            var fromEnv = Environment.GetEnvironmentVariable("OMI_API_BASE_URL");
            if (string.IsNullOrWhiteSpace(fromEnv))
            {
                return DefaultApiBaseUrl;
            }

            fromEnv = fromEnv.TrimEnd('/') + "/";
            return fromEnv;
        }
    }

    public static string FirebaseApiKey =>
        Environment.GetEnvironmentVariable("OMI_FIREBASE_API_KEY")
        ?? Environment.GetEnvironmentVariable("FIREBASE_API_KEY")
        ?? DefaultFirebaseApiKey;
}

