import '../analytics_manager.dart';
import 'events.g.dart';
export 'event_context.dart';

/// Only this seam forwards generated events into AnalyticsManager.track.
/// The builder keeps the manager queue, consent, adapter and provenance behavior.
class TypedEvents {
  const TypedEvents();

  void emit(RegisteredEvent event) =>
      AnalyticsManager().track(event.wireName, properties: Map<String, dynamic>.from(event.properties));
}

enum EventPhase { point, attempt, progress, outcome }
