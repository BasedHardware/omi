import 'package:posthog_flutter/posthog_flutter.dart';

import 'package:omi/utils/analytics/analytics_adapter.dart';

class PostHogAnalyticsAdapter implements AnalyticsAdapter {
  PostHogAnalyticsAdapter({
    required this.apiKey,
    this.host = 'https://us.i.posthog.com',
    // PostHog's built-in lifecycle capture fires `Application Opened`,
    // `Application Backgrounded`, `Application Installed`, `Application Updated`
    // (and on iOS the active/resigned-active pair) on every state change.
    // For our usage that's pure event-volume noise — we already track the
    // meaningful boundary (sign-in/launch) via explicit events — and it was the
    // single biggest contributor to monthly PostHog spend. Keep this default
    // off; opt back in explicitly if a future flow needs the raw cadence.
    this.captureLifecycleEvents = false,
    this.debug = false,
  });

  final String apiKey;
  final String host;
  final bool captureLifecycleEvents;
  final bool debug;

  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    if (_initialized) return;
    final config = PostHogConfig(apiKey);
    config.host = host;
    config.captureApplicationLifecycleEvents = captureLifecycleEvents;
    config.debug = debug;
    await Posthog().setup(config);
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {
    if (!_initialized) return;
    if (userProperties == null) {
      Posthog().identify(userId: userId);
    } else {
      Posthog().identify(userId: userId, userProperties: userProperties);
    }
  }

  @override
  void alias({required String newUserId}) {
    if (!_initialized) return;
    Posthog().alias(alias: newUserId);
  }

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    if (!_initialized) return;
    Posthog().capture(eventName: eventName, properties: properties);
  }

  @override
  void enable() {
    if (!_initialized) return;
    Posthog().enable();
  }

  @override
  void disable() {
    if (!_initialized) return;
    Posthog().disable();
  }

  @override
  void reset() {
    if (!_initialized) return;
    Posthog().reset();
  }
}
