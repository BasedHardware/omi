abstract class Env {
  static late final EnvFields _instance;
  static String? _apiBaseUrlOverride;
  static String? _agentProxyWsUrlOverride;
  static bool isTestFlight = false;

  /// Cached effective API base URL — fixed at init time to prevent
  /// prod/staging split on WebSocket reconnect (#5949).
  /// Use [apiBaseUrl] for the current value or [forceRefreshApiBaseUrl]
  /// to update after an environment switch.
  static String? _cachedApiBaseUrl;

  static void init(EnvFields instance) {
    _instance = instance;
    // Cache the effective API base URL at init time so that WS reconnects
    // always use the same backend as the initial connection.
    _cachedApiBaseUrl = _apiBaseUrlOverride ?? _instance.apiBaseUrl;
  }

  static void overrideApiBaseUrl(String url) {
    _apiBaseUrlOverride = url;
    // Refresh the cached URL so that subsequent WS reconnects use the new backend.
    _cachedApiBaseUrl = _apiBaseUrlOverride ?? _instance.apiBaseUrl;
  }

  static void overrideAgentProxyWsUrl(String url) {
    _agentProxyWsUrlOverride = url;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  // static String? get apiBaseUrl => 'https://omi-backend.ngrok.app/';
  static String? get apiBaseUrl {
    // Return override if set, otherwise the cached URL set at init time
    // (which is updated by overrideApiBaseUrl for TestFlight staging).
    // This ensures WS reconnects always use the same backend as the initial connection.
    if (_apiBaseUrlOverride != null) return _apiBaseUrlOverride;
    return _cachedApiBaseUrl ?? _instance.apiBaseUrl;
  }

  static String get stagingApiUrl {
    final url = _instance.stagingApiUrl;
    if (url != null && url.isNotEmpty) return url;
    return 'https://api.omiapi.com/';
  }

  static bool get isUsingStagingApi {
    final effective = apiBaseUrl;
    if (effective == null) return false;
    return _normalizeUrl(effective) == _normalizeUrl(stagingApiUrl);
  }

  static String _normalizeUrl(String url) {
    var s = url.trim().toLowerCase();
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    return s;
  }

  /// WebSocket URL for the agent proxy service.
  /// Derives from apiBaseUrl: api.omi.me → agent.omi.me, api.omiapi.com → agent.omiapi.com.
  /// Can be overridden via Env.overrideAgentProxyWsUrl() for local testing.
  static String get agentProxyWsUrl {
    if (_agentProxyWsUrlOverride != null) return _agentProxyWsUrlOverride!;
    final base = apiBaseUrl ?? 'https://api.omi.me';
    final host = Uri.parse(base).host.replaceFirst('api.', 'agent.');
    return 'wss://$host/v1/agent/ws';
  }

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get googleClientId => _instance.googleClientId;

  static String? get googleClientSecret => _instance.googleClientSecret;

  static bool get useWebAuth => _instance.useWebAuth ?? false;

  static bool get useAuthCustomToken => _instance.useAuthCustomToken ?? false;
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get googleClientId;

  String? get googleClientSecret;

  bool? get useWebAuth;

  bool? get useAuthCustomToken;

  String? get stagingApiUrl;
}
