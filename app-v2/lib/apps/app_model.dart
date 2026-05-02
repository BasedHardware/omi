/// Reduced view of a backend `App` from `/v2/apps`. We only model the fields
/// the v0 grid actually renders — id/name/description/image and the install
/// signal — so the wire schema can grow without churning this file.
class NooApp {
  const NooApp({
    required this.id,
    required this.name,
    required this.description,
    required this.imageUrl,
    required this.enabled,
    required this.installs,
    required this.capabilities,
    this.author,
    this.ratingAvg,
    this.ratingCount,
    this.externalIntegration,
  });

  final String id;
  final String name;
  final String description;
  final String imageUrl;
  final bool enabled;
  final int installs;
  final List<String> capabilities;
  final String? author;
  final double? ratingAvg;
  final int? ratingCount;

  /// Present for OAuth-style integrations (Jira, Linear, ClickUp, …). Null for
  /// plain prompt apps. The provider uses `externalIntegration?.primaryAuthUrl`
  /// to decide whether `/v1/apps/enable`'s 400 means "open the OAuth flow".
  final ExternalIntegration? externalIntegration;

  factory NooApp.fromJson(Map<String, dynamic> json) {
    final caps = json['capabilities'];
    final ext = json['external_integration'];
    return NooApp(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      description: (json['description'] ?? '').toString(),
      imageUrl: (json['image'] ?? '').toString(),
      enabled: json['enabled'] as bool? ?? false,
      installs: (json['installs'] as num?)?.toInt() ?? 0,
      capabilities: caps is List
          ? caps.map((e) => e.toString()).toList(growable: false)
          : const <String>[],
      author: json['author'] as String?,
      ratingAvg: (json['rating_avg'] as num?)?.toDouble(),
      ratingCount: (json['rating_count'] as num?)?.toInt(),
      externalIntegration: ext is Map
          ? ExternalIntegration.fromJson(Map<String, dynamic>.from(ext))
          : null,
    );
  }
}

/// One capability section in the Apps screen — e.g. "Popular", "Integrations".
/// `id` is the stable backend key; `title` is what we render.
class AppGroup {
  const AppGroup({required this.id, required this.title, required this.apps});

  final String id;
  final String title;
  final List<NooApp> apps;

  factory AppGroup.fromJson(Map<String, dynamic> json) {
    final cap = json['capability'] as Map?;
    final data = json['data'];
    return AppGroup(
      id: (cap?['id'] ?? '').toString(),
      title: (cap?['title'] ?? '').toString(),
      apps: data is List
          ? data
              .whereType<Map>()
              .map((m) => NooApp.fromJson(Map<String, dynamic>.from(m)))
              .toList(growable: false)
          : const <NooApp>[],
    );
  }
}

/// External-integration metadata for OAuth-style apps. Backend shape:
/// `external_integration: { auth_steps: [{name, url}], app_home_url, … }`.
///
/// Only the fields the install/OAuth flow needs are modelled — the manifest
/// has many more keys (webhook_url, mcp_oauth_tokens, …) that the client
/// never reads, so widening this model has no caller value.
class ExternalIntegration {
  const ExternalIntegration({
    this.authSteps = const [],
    this.appHomeUrl,
    this.setupCompletedUrl,
  });

  final List<AuthStep> authSteps;
  final String? appHomeUrl;
  final String? setupCompletedUrl;

  /// First-step URL (or `appHomeUrl` fallback). Null if neither is set.
  /// Mirrors desktop-v2's `auth_steps?.[0]?.url ?? app_home_url` pattern —
  /// `app_home_url` alone usually 404s in a browser, so the auth step is
  /// preferred when the manifest has one.
  String? get primaryAuthUrl =>
      authSteps.isNotEmpty ? authSteps.first.url : appHomeUrl;

  factory ExternalIntegration.fromJson(Map<String, dynamic> json) {
    final steps = json['auth_steps'];
    return ExternalIntegration(
      authSteps: steps is List
          ? steps
              .whereType<Map>()
              .map((m) => AuthStep.fromJson(Map<String, dynamic>.from(m)))
              .toList(growable: false)
          : const [],
      appHomeUrl: json['app_home_url'] as String?,
      setupCompletedUrl: json['setup_completed_url'] as String?,
    );
  }
}

/// One step in the plugin's OAuth flow. `name` is a human-readable label
/// (e.g. "Connect Jira"); `url` is what we open in the system browser.
class AuthStep {
  const AuthStep({required this.name, required this.url});

  final String name;
  final String url;

  factory AuthStep.fromJson(Map<String, dynamic> json) => AuthStep(
        name: json['name'] as String? ?? '',
        url: json['url'] as String? ?? '',
      );
}
