import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/platform/platform_service.dart';

class PostHogAnalyticsAdapter
    implements AnalyticsAdapter, AnalyticsDeliveryAdapter, AnalyticsIdentityAdapter, AnalyticsFeatureFlagAdapter {
  PostHogAnalyticsAdapter({
    required this.apiKey,
    this.host = 'https://us.i.posthog.com',
    // SDK default is `true`; we track lifecycle ourselves at meaningful boundaries.
    this.captureLifecycleEvents = false,
    this.debug = false,
    http.Client? client,
    Future<String?> Function()? distinctIdReader,
  })  : _client = client,
        _distinctIdReader = distinctIdReader;

  final http.Client? _client;
  final Future<String?> Function()? _distinctIdReader;

  /// Flags confirmed by a successful fetch for the identity in force at the time; cleared whenever
  /// the identity changes. Reads prefer this over the SDK cache, which the SDK keeps (stale, and
  /// possibly another person's) when its own refresh fails.
  ({String distinctId, Map<String, Object?> flags, Map<String, Object?> payloads})? _verified;

  @visibleForTesting
  bool get hasVerifiedFlags => _verified != null;

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
    _verified = null;
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
  Future<bool> isFeatureEnabled(String key) {
    final verified = _verified;
    if (verified != null) {
      final value = verified.flags[key];
      return Future.value(value == true || (value is String && value.isNotEmpty));
    }
    return Posthog().isFeatureEnabled(key);
  }

  @override
  Future<String?> getFeatureFlagVariant(String key) async {
    final verified = _verified;
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
    try {
      final distinctId = await (_distinctIdReader ?? Posthog().getDistinctId)();
      if (distinctId == null || distinctId.isEmpty) return false;
      final client = _client ?? http.Client();
      final response = await client
          .post(
            Uri.parse('$host/decide/?v=3'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({'api_key': apiKey, 'distinct_id': distinctId}),
          )
          .timeout(const Duration(seconds: 4));
      if (response.statusCode != 200) return false;
      final decoded = jsonDecode(response.body);
      final flags = decoded is Map ? decoded['featureFlags'] : null;
      if (flags is! Map) return false;
      final payloads = decoded['featureFlagPayloads'];
      _verified = (
        distinctId: distinctId,
        flags: Map<String, Object?>.from(flags),
        payloads: payloads is Map ? Map<String, Object?>.from(payloads) : const {},
      );
      // Keep the SDK's cache moving too; its outcome is not what the answer depends on.
      if (_initialized) _background(Posthog().reloadFeatureFlags);
      return true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<Object?> getFeatureFlagPayload(String key) async {
    final verified = _verified;
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
    _verified = null;
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
    if (!_initialized) return;
    _targetExpiry?.cancel();
    _targetExpiry = null;
    _background(() => Posthog().reset());
  }
}
