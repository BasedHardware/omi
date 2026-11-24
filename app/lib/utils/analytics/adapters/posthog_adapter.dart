import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/session_replay.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// One flag answered by Omi's own flag store (`GET /v1/flags`).
typedef OmiFlag = ({bool enabled, String? variant, String? payloadJson});

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
    this.omiFlags,
  });

  /// Omi is the only flag authority. A failed refresh keeps this account's last
  /// answer; a missing key is unknown and each caller applies its own default.
  final Future<Map<String, OmiFlag>?> Function()? omiFlags;
  Map<String, OmiFlag> _omi = const {};

  /// Bumped on every identity change; a reload commits its answer only if the generation it started
  /// in is still current, so a slow response for account A cannot land after B took over.
  int _identityGeneration = 0;
  String? _flagIdentity;

  void _identityChanged(String? identity, {bool reset = false}) {
    if (!reset && identity == _flagIdentity) return;
    _flagIdentity = identity;
    _identityGeneration++;
    _omi = const {};
  }

  // Pinned by posthog_adapter_flags_test against pubspec.lock on dependency upgrades.
  static const flutterSdkVersion = '5.28.0';

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
    // Omi has no PosthogObserver / survey surface; keep native survey UI off too.
    config.surveys = false;
    SessionReplay.configure(config);
    // Own native transport before the Flutter bridge initializes. Native setup is
    // idempotent; the bridge still initializes Dart replay and event callbacks.
    // preloadFeatureFlags alone does not suppress identify/reset SDK requests.
    if (PlatformService.isMobile) {
      await const MethodChannel('com.omi/posthog_setup').invokeMethod<void>('setup', {
        'projectToken': apiKey,
        'sdkVersion': flutterSdkVersion,
        'host': host,
        'captureApplicationLifecycleEvents': captureLifecycleEvents,
        'optOut': config.optOut,
        'debug': debug,
      });
    }
    await Posthog().setup(config);
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {
    _identityChanged(userId);
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
  bool isBooleanFeatureEnabledCached(String key) {
    final omi = _omi[key];
    if (omi != null) return omi.enabled && omi.variant == null;
    return false;
  }

  @override
  Future<bool> isBooleanFeatureEnabled(String key) async {
    final omi = _omi[key];
    if (omi != null) return omi.enabled && omi.variant == null;
    return false;
  }

  @override
  Future<bool?> resolvedFeatureEnabled(String key) async => _omi[key]?.enabled;

  @override
  Future<bool> isFeatureEnabled(String key) async => _omi[key]?.enabled ?? false;

  @override
  Future<String?> getFeatureFlagVariant(String key) async {
    final omi = _omi[key];
    return omi?.enabled == true ? omi?.variant : null;
  }

  /// Refreshes only Omi's store. Analytics capture and identity stay in PostHog.
  @override
  Future<bool> reloadFeatureFlags() => _reloadOmiFlags();

  /// A failed or superseded fetch keeps the previous Omi answer for this identity.
  Future<bool> _reloadOmiFlags() async {
    final fetch = omiFlags;
    if (fetch == null) return false;
    final generation = _identityGeneration;
    try {
      final flags = await fetch();
      if (flags == null || generation != _identityGeneration) return false;
      _omi = Map.unmodifiable(flags);
      return true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<Object?> getFeatureFlagPayload(String key) async {
    final omi = _omi[key];
    if (omi != null) {
      final raw = omi.payloadJson;
      if (!omi.enabled || raw == null) return null;
      try {
        return jsonDecode(raw);
      } on FormatException {
        return raw;
      }
    }
    return null;
  }

  @override
  Future<String> settleIdentity(String? identity, {required bool reset}) async {
    _identityChanged(identity, reset: reset);
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
    _identityChanged(null, reset: true);
    if (!_initialized) return;
    _targetExpiry?.cancel();
    _targetExpiry = null;
    _background(() => Posthog().reset());
  }
}
