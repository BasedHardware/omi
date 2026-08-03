abstract class Env {
  static const productionApiBaseUrl = 'https://api.omi.me/';
  static const productionAgentProxyWsUrl = 'wss://agent.omi.me/v1/agent/ws';
  static late final EnvFields _instance;
  static String? _apiBaseUrlOverride;
  static String? _agentProxyWsUrlOverride;
  static bool isTestFlight = false;

  static void init(EnvFields instance) {
    _instance = instance;
  }

  static void overrideApiBaseUrl(String url) {
    _apiBaseUrlOverride = url;
  }

  static void clearApiBaseUrlOverrideForTesting() {
    _apiBaseUrlOverride = null;
  }

  static void overrideAgentProxyWsUrl(String url) {
    _agentProxyWsUrlOverride = url;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get posthogApiKey => _instance.posthogApiKey;

  // static String? get apiBaseUrl => 'https://omi-backend.ngrok.app/';
  static String? get apiBaseUrl => _apiBaseUrlOverride ?? _instance.apiBaseUrl;

  /// Production-family packages have one pinned backend authority. This runs
  /// during startup so a misconfigured signing group fails before networking.
  static void validateStartupRouting({required bool productionFamily, String? configuredApiBaseUrl}) {
    if (!productionFamily) return;
    final normalized = (configuredApiBaseUrl ?? apiBaseUrl ?? '').trim().replaceFirst(RegExp(r'/+$'), '');
    if (normalized != productionApiBaseUrl.replaceFirst(RegExp(r'/+$'), '')) {
      throw StateError('Production packages require API_BASE_URL=https://api.omi.me/');
    }
    if (_agentProxyWsUrlFor(normalized) != productionAgentProxyWsUrl) {
      throw StateError('Production packages require the production agent WebSocket endpoint.');
    }
  }

  static void requireProductionRouting() => validateStartupRouting(productionFamily: true);

  /// WebSocket URL for the agent proxy service.
  /// Derives from apiBaseUrl: api.omi.me → agent.omi.me, api.omiapi.com → agent.omiapi.com.
  /// Can be overridden via Env.overrideAgentProxyWsUrl() for local testing.
  static String get agentProxyWsUrl {
    if (_agentProxyWsUrlOverride != null) return _agentProxyWsUrlOverride!;
    return _agentProxyWsUrlFor(apiBaseUrl ?? productionApiBaseUrl);
  }

  static String _agentProxyWsUrlFor(String base) {
    final host = Uri.parse(base).host.replaceFirst('api.', 'agent.');
    return 'wss://$host/v1/agent/ws';
  }

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get googleClientId => _instance.googleClientId;

  static String? get googleClientSecret => _instance.googleClientSecret;

  static bool get useWebAuth => _instance.useWebAuth ?? false;

  static bool get useAuthCustomToken => _instance.useAuthCustomToken ?? false;

  /// Auth client backend, symmetric to the server's AUTH_BACKEND (ADR-0038).
  /// 'firebase' (default) keeps the existing Google/Apple flow untouched;
  /// 'oidc' enables the additive OIDC (Authorization Code + PKCE) login.
  static String get authBackend => _instance.authBackend ?? 'firebase';

  static bool get useOidc => authBackend == 'oidc';

  static String? get oidcIssuer => _instance.oidcIssuer;

  static String? get oidcClientId => _instance.oidcClientId;

  static String? get oidcRedirectScheme => _instance.oidcRedirectScheme;

  /// Client notification delivery backend, symmetric to the server's NOTIFICATIONS_BACKEND (ADR-0011).
  /// 'fcm' (default) keeps Firebase Cloud Messaging / APNs remote push untouched; 'local' uses
  /// local-only notifications (awesome_notifications) with no remote push and no FirebaseMessaging at
  /// runtime — for a Firebase-push-free on-prem deployment.
  static String get notificationsBackend => _instance.notificationsBackend ?? 'fcm';

  static bool get useFcmNotifications => notificationsBackend == 'fcm';
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get posthogApiKey;

  String? get apiBaseUrl;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get googleClientId;

  String? get googleClientSecret;

  bool? get useWebAuth;

  bool? get useAuthCustomToken;

  String? get authBackend;

  String? get oidcIssuer;

  String? get oidcClientId;

  String? get oidcRedirectScheme;

  String? get notificationsBackend;
}
