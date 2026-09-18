import '../analytics_manager.dart';
import 'events.g.dart';

/// Only this seam forwards generated events into AnalyticsManager.track.
/// The builder keeps the manager queue, consent, adapter and provenance behavior.
class TypedEvents {
  const TypedEvents();

  void emit(RegisteredEvent event) =>
      AnalyticsManager().track(event.wireName, properties: Map<String, dynamic>.from(event.properties));
}

/// Reserved for F1, not emitted by C7's legacy point events.
enum EventPhase { point, attempt, outcome }

/// Never a user/device/session identifier. Mint once for one intent attempt;
/// pass the same value to its terminal event. No arbitrary-string constructor.
final class EventCorrelation {
  EventCorrelation._(this.value);
  final String value;
  static EventCorrelation mint() => EventCorrelation._(throw UnimplementedError('F1: random attempt correlation'));
}
