import 'dart:async';

import 'package:posthog_flutter/posthog_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/services/experiments/experiment_registry.dart';

class PostHogAnalyticsAdapter implements AnalyticsAdapter, AnalyticsDeliveryAdapter, AnalyticsIdentityAdapter {
  PostHogAnalyticsAdapter({
    required this.apiKey,
    this.host = 'https://us.i.posthog.com',
    // SDK default is `true`; we track lifecycle ourselves at meaningful boundaries.
    this.captureLifecycleEvents = false,
    this.debug = false,
  });

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
    // ExperimentService records exposure only when a variant is used/rendered.
    config.sendFeatureFlagEvents = false;
    config.preloadFeatureFlags = false;
    await Posthog().setup(config);
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {
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
    _background(() => Posthog().capture(eventName: eventName, properties: masked));
  }

  @override
  Future<void> deliver({required String eventName, required Map<String, Object> properties}) {
    if (!_initialized) return Future.error(StateError('Analytics SDK not ready'));
    final masked = _captureProperties(properties);
    return _serialize(() => Posthog().capture(eventName: eventName, properties: masked));
  }

  /// Native identify() reloads flags even with preloadFeatureFlags disabled.
  /// Both native SDKs merge caller feature properties over cached flag values;
  /// explicit false prevents their cache from inventing assignment attribution.
  /// Snapshot here, before queueing, so later caller mutations cannot relabel an
  /// event. True exposure/outcome properties supplied by our service win.
  Map<String, Object> _captureProperties(Map<String, Object>? properties) => {
        for (final definition in MobileExperiments.all) '\$feature/${definition.key}': false,
        ...?properties,
      };

  @override
  Future<String> settleIdentity(String? identity, {required bool reset}) async {
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
