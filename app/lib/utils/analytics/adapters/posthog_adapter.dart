import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/platform/platform_service.dart';

class PostHogAnalyticsAdapter
    implements
        AnalyticsResolvedFlagAdapter,
        AnalyticsAdapter,
        AnalyticsDeliveryAdapter,
        AnalyticsIdentityAdapter,
        AnalyticsFeatureFlagAdapter,
        AnalyticsBooleanFlagAdapter {
  PostHogAnalyticsAdapter({
    required this.apiKey,
    this.host = 'https://us.i.posthog.com',
    // SDK default is `true`; we track lifecycle ourselves at meaningful boundaries.
    this.captureLifecycleEvents = false,
    this.debug = false,
    http.Client? client,
    Future<String?> Function()? distinctIdReader,
    this.personPropertiesForFlags,
    DateTime Function()? clock,
  })  : _client = client,
        _distinctIdReader = distinctIdReader,
        _clock = clock ?? DateTime.now;

  final http.Client? _client;
  final Future<String?> Function()? _distinctIdReader;

  /// Person properties sent with a verified fetch so property-targeted flags match a just-created
  /// identity before PostHog has ingested its `\$set` (a fresh account's email, for one).
  final Map<String, Object?> Function()? personPropertiesForFlags;
  final DateTime Function() _clock;

  /// How long a verified fetch outranks the SDK cache. Long enough for the read that asked for it
  /// (the onboarding gate reads within milliseconds), short enough that the SDK's own refreshes
  /// decide every other flag for the rest of the session.
  static const verifiedFlagsTtl = Duration(seconds: 10);

  /// Flags confirmed by a successful fetch for the identity in force at the time; cleared whenever
  /// the identity changes. Reads prefer this over the SDK cache, which the SDK keeps (stale, and
  /// possibly another person's) when its own refresh fails.
  ({String distinctId, Map<String, Object?> flags, Map<String, Object?> payloads, DateTime at})? _verified;

  /// The verified snapshot while it is still fresh; expired ones are dropped so the SDK cache rules.
  ({String distinctId, Map<String, Object?> flags, Map<String, Object?> payloads, DateTime at})? get _fresh {
    final verified = _verified;
    if (verified == null) return null;
    if (_clock().difference(verified.at) > verifiedFlagsTtl) {
      _verified = null;
      return null;
    }
    return verified;
  }

  /// Bumped on every identity change; a reload commits its answer only if the generation it started
  /// in is still current, so a slow response for account A cannot land after B took over.
  int _identityGeneration = 0;

  @visibleForTesting
  bool get hasVerifiedFlags => _fresh != null;

  void _identityChanged() {
    _identityGeneration++;
    _verified = null;
  }

  final String apiKey;
  final String host;
  final bool captureLifecycleEvents;
  final bool debug;

  bool _initialized = false;
  Timer? _targetExpiry;
  Future<void> _operations = Future<void>.value();

  Future<void> _serialize(Future<void> Function() operation) {
    final next = _operations.then((_) => operation());
    _operations = next.catchError((Object _) {});
    return next;
  }

  void _background(Future<void> Function() operation) {
    unawaited(_serialize(operation).catchError((Object _) {}));
  }

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    if (_initialized) return;
    final config = PostHogConfig(apiKey);
    config.host = host;
    final preferences = await SharedPreferences.getInstance();
    config.optOut = !(preferences.getBool('product_analytics_enabled') ?? true);
    config.captureApplicationLifecycleEvents = captureLifecycleEvents;
    config.debug = debug;
    config.sendFeatureFlagEvents = false;
    config.preloadFeatureFlags = false;
    await Posthog().setup(config);
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {
    _identityChanged();
    if (!_initialized) return;
    if (userProperties == null) {
      _background(() => Posthog().identify(userId: userId));
    } else {
      _background(() => Posthog().identify(userId: userId, userProperties: userProperties));
    }
  }

  @override
  void alias({required String newUserId}) {
    if (!_initialized) return;
    _background(() => Posthog().alias(alias: newUserId));
  }

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    if (!_initialized) return;
    final masked = _captureProperties(properties);
    _background(() => Posthog().capture(eventName: eventName, properties: _stampAttribution(eventName, masked)));
  }

  @override
  Future<void> deliver({required String eventName, required Map<String, Object> properties}) {
    if (!_initialized) return Future.error(StateError('Analytics SDK not ready'));
    final masked = _captureProperties(properties);
    return _serialize(() => Posthog().capture(eventName: eventName, properties: _stampAttribution(eventName, masked)));
  }

  /// SDK-boundary attribution stamping. Churn/retention analysis needs a
  /// `platform` field and a `trigger` classification (user/background/system)
  /// on every event reaching PostHog. These carry no user content, so they are
  /// attached here — after the manager's privacy masking — rather than inside
  /// the governed typed-emission boundary (C7 pins that payload exactly).
  Map<String, Object> _stampAttribution(String eventName, Map<String, Object> properties) {
    final stamped = {...properties};
    stamped['platform'] ??= _platformName;
    final explicit = stamped['trigger'];
    if (explicit is String && explicit.isNotEmpty) return stamped;
    stamped['trigger'] = _nonUserTriggerByEvent[eventName] ?? 'user';
    return stamped;
  }

  static const Map<String, String> _nonUserTriggerByEvent = {
    'Mobile Background Resource Session': 'background',
    'Mobile Background Observation Interrupted': 'background',
    'Mobile Telemetry Health': 'background',
    'Mobile Render Observation': 'background',
    'App Startup Timing': 'system',
    'desktop_health_event': 'system',
    'fallback_triggered': 'system',
    'authenticated_request_401': 'system',
    'auth_token_refresh_failed': 'system',
    'Notification Sent': 'system',
    'Notification Dismissed': 'system',
    'Notification Settings Checked': 'system',
    'Update Available': 'system',
    'Update Check Started': 'system',
    'Update Check Completed': 'system',
    'Update Check Failed': 'system',
    'Update Install Started': 'system',
    'Update Installed': 'system',
  };

  static String get _platformName {
    if (PlatformService.isIOS) return 'ios';
    if (PlatformService.isAndroid) return 'android';
    return 'unknown';
  }

  Map<String, Object> _captureProperties(Map<String, Object>? properties) => {...?properties};

  @override
  bool isBooleanFeatureEnabledCached(String key) => _fresh?.flags[key] == true;

  @override
  Future<bool> isBooleanFeatureEnabled(String key) async {
    final verified = _fresh;
    if (verified != null) return verified.flags[key] == true;
    final result = await Posthog().getFeatureFlagResult(key);
    return result?.enabled == true && result?.variant == null;
  }

  @override
  Future<bool?> resolvedFeatureEnabled(String key) async {
    final verified = _fresh;
    if (verified != null) {
      final value = verified.flags[key];
      return value is bool ? value : null;
    }
    final result = await Posthog().getFeatureFlagResult(key);
    return result?.enabled;
  }

  @override
  Future<bool> isFeatureEnabled(String key) {
    final verified = _fresh;
    if (verified != null) {
      final value = verified.flags[key];
      return Future.value(value == true || (value is String && value.isNotEmpty));
    }
    return Posthog().isFeatureEnabled(key);
  }

  @override
  Future<String?> getFeatureFlagVariant(String key) async {
    final verified = _fresh;
    if (verified != null) {
      final value = verified.flags[key];
      return value is String && value.isNotEmpty ? value : null;
    }
    final result = await Posthog().getFeatureFlagResult(key);
    return result?.enabled == true ? result?.variant : null;
  }

  /// Fetches the flags for the current distinct id straight from PostHog and keeps them as the
  /// verified snapshot. True only when the fetch succeeded for that identity: the SDK's own reload
  /// cannot say whether it refreshed (the plugin swallows failures and the native callback fires
  /// either way), so its cache is never taken as fresh here.
  @override
  Future<bool> reloadFeatureFlags() async {
    final generation = _identityGeneration;
    final owned = _client == null ? http.Client() : null; // injected clients stay caller-owned
    final client = _client ?? owned!;
    try {
      final distinctId = await (_distinctIdReader ?? Posthog().getDistinctId)();
      if (distinctId == null || distinctId.isEmpty) return false;
      final personProperties = {...?personPropertiesForFlags?.call()}..removeWhere((_, v) => v == null || v == '');
      final response = await client
          .post(
            Uri.parse('$host/decide/?v=3'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({
              'api_key': apiKey,
              'distinct_id': distinctId,
              if (personProperties.isNotEmpty) 'person_properties': personProperties,
            }),
          )
          .timeout(const Duration(seconds: 4));
      if (response.statusCode != 200) return false;
      final decoded = jsonDecode(response.body);
      final flags = decoded is Map ? decoded['featureFlags'] : null;
      if (flags is! Map) return false;
      final payloads = decoded['featureFlagPayloads'];
      if (generation != _identityGeneration) return false; // another identity took over mid-flight
      _verified = (
        distinctId: distinctId,
        flags: Map<String, Object?>.from(flags),
        payloads: payloads is Map ? Map<String, Object?>.from(payloads) : const {},
        at: _clock(),
      );
      // Keep the SDK's cache moving too; its outcome is not what the answer depends on.
      if (_initialized) _background(Posthog().reloadFeatureFlags);
      return true;
    } catch (_) {
      return false;
    } finally {
      owned?.close();
    }
  }

  @override
  Future<Object?> getFeatureFlagPayload(String key) async {
    final verified = _fresh;
    if (verified != null) {
      if (!await isFeatureEnabled(key)) return null;
      final raw = verified.payloads[key];
      if (raw is! String) return raw;
      try {
        return jsonDecode(raw);
      } on FormatException {
        return raw;
      }
    }
    final result = await Posthog().getFeatureFlagResult(key);
    return result?.enabled == true ? result?.payload : null;
  }

  @override
  Future<String> settleIdentity(String? identity, {required bool reset}) async {
    _identityChanged();
    String? distinctId;
    await _serialize(() async {
      if (reset) await Posthog().reset();
      if (identity != null) await Posthog().identify(userId: identity);
      distinctId = await Posthog().getDistinctId();
    });
    if (distinctId == null || distinctId!.isEmpty) throw StateError('Analytics identity unavailable');
    return distinctId!;
  }

  @override
  void registerSuperProperties(Map<String, Object> properties) {
    if (!_initialized) return;
    for (final entry in properties.entries) {
      _background(() => Posthog().register(entry.key, entry.value));
    }
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {
    if (!_initialized) return;

    // Native iOS rage-click capture runs before Flutter receives the current
    // pointer. Registering every pointer's context means a qualifying third
    // tap inherits the matching context recorded by the first two taps.
    if (screenName != null && screenName.isNotEmpty) {
      _background(() => Posthog().register(r'$screen_name', screenName));
      _background(() => Posthog().register('screen', screenName));
    }
    _background(() => Posthog().register('target', target));
    _targetExpiry?.cancel();
    _targetExpiry = Timer(const Duration(seconds: 2), () {
      if (_initialized) _background(() => Posthog().unregister('target'));
    });
  }

  @override
  void enable() {
    if (!_initialized) return;
    _background(() => Posthog().enable());
  }

  @override
  void disable() {
    if (!_initialized) return;
    _background(() => Posthog().disable());
  }

  @override
  void reset() {
    _identityChanged();
    if (!_initialized) return;
    _targetExpiry?.cancel();
    _targetExpiry = null;
    _background(() => Posthog().reset());
  }
}
