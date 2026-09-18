/// Mobile emitter for the shared fallback contract. Never accept payloads,
/// URLs, record ids, exception messages, or arbitrary labels.
enum ApiFallbackReason { partialDecode, staleData }

enum ApiFallbackOutcome { degraded, recovered, exhausted }

class ApiFallbackEvent {
  const ApiFallbackEvent({required this.reason, required this.outcome});
  final ApiFallbackReason reason;
  final ApiFallbackOutcome outcome;
  Map<String, String> toFields() => throw UnimplementedError('C3 bounded shared fallback fields');
}

/// Default sink is AnalyticsManager's existing track method; injected sink is
/// the test seam. Event name: fallback_triggered, shared closed field names.
void recordFallback(ApiFallbackEvent event, {void Function(String, Map<String, String>)? emit}) =>
    throw UnimplementedError('C3 shared fallback emitter');
