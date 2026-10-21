/// Mobile emitter for the shared fallback contract. Never accept payloads,
/// URLs, record ids, exception messages, or arbitrary labels.
library;

import 'package:omi/utils/analytics/analytics_manager.dart';

enum ApiFallbackReason { partialDecode, staleData, timeout, error, offline }

enum ApiFallbackOutcome { degraded, recovered, exhausted }

class ApiFallbackEvent {
  const ApiFallbackEvent({required this.reason, required this.outcome});
  final ApiFallbackReason reason;
  final ApiFallbackOutcome outcome;
  Map<String, String> toFields() => {
        'component': 'other',
        'area': 'other',
        'from': 'none',
        'to': 'none',
        'reason': switch (reason) {
          ApiFallbackReason.timeout => 'timeout',
          ApiFallbackReason.error => 'error',
          ApiFallbackReason.offline => 'offline',
          _ => 'other',
        },
        'outcome': outcome.name,
      };
}

/// Default sink is AnalyticsManager's existing track method; injected sink is
/// the test seam. Event name: fallback_triggered, shared closed field names.
void recordFallback(ApiFallbackEvent event, {void Function(String, Map<String, String>)? emit}) {
  final sink = emit ?? (name, fields) => AnalyticsManager().track(name, properties: fields);
  sink('fallback_triggered', event.toFields());
}
