import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/logger.dart';
export 'package:omi/utils/analytics/registry/events.g.dart' show NativeCustodyObservedOutcome;

/// Bounded counters, without file names, paths, owners or audio metadata.
void nativeCustodyObserved(NativeCustodyObservedOutcome outcome) {
  Logger.debug('Native custody: ${outcome.wireName}');
  const TypedEvents().emit(NativeCustodyObserved(outcome: outcome));
}
