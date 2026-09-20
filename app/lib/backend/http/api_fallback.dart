/// Mobile emitter for the shared fallback contract. Never accept payloads,
/// URLs, record ids, exception messages, or arbitrary labels.
import 'package:omi/utils/analytics/analytics_manager.dart';

enum ApiFallbackReason { partialDecode, staleData }

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
        'reason': 'other',
        'outcome': outcome.name,
      };
}

/// Default sink is AnalyticsManager's existing track method; injected sink is
/// the test seam. Event name: fallback_triggered, shared closed field names.
void recordFallback(ApiFallbackEvent event, {void Function(String, Map<String, String>)? emit}) {
  final sink = emit ?? (name, fields) => AnalyticsManager().track(name, properties: fields);
  sink('fallback_triggered', event.toFields());
}
