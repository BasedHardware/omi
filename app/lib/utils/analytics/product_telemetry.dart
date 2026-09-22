import 'dart:math' as math;

import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

export 'package:omi/utils/analytics/registry/event_context.dart';

enum ProductJourney {
  search,
  chatText,
  chatVoice,
  subscriptionCancel,
  summaryFeedback,
  recordingFeedback,
  notificationOpen,
  integrationConnect,
  integrationSync,
  onboarding,
  permission,
  taskMutation,
  conversationLoad,
  capture,
}

enum ProductSurface {
  home,
  conversations,
  conversationDetail,
  chat,
  tasks,
  onboarding,
  settings,
  notification,
  integration,
  background,
  unknown
}

enum ProductOutcome { success, empty, failure, cancelled, superseded, unobserved }

enum ProductFailure {
  none,
  network,
  server,
  unauthorized,
  permissionDenied,
  quota,
  timeout,
  invalidResponse,
  incomplete,
  unknown
}

enum ProductValue {
  resultViewed,
  copied,
  shared,
  taskCompleted,
  memoryKept,
  feedbackHelpful,
  searchResultOpened,
  recordingRecovered
}

/// The application-facing typed boundary. Generated events own exact wire shapes;
/// this object owns attempt lifetime, deduplication and identity fencing.
class ProductTelemetry {
  ProductTelemetry({void Function(RegisteredEvent)? emit, DateTime Function()? now, int Function()? identityEpoch})
      : _emit = emit ?? const TypedEvents().emit,
        _now = now ?? DateTime.now,
        _identityEpoch = identityEpoch ?? (() => AnalyticsManager.identityEpoch);

  static ProductTelemetry instance = ProductTelemetry();
  final void Function(RegisteredEvent) _emit;
  final DateTime Function() _now;
  final int Function() _identityEpoch;

  void _send(RegisteredEvent event, [Map<String, Object>? attribution]) {
    try {
      AnalyticsManager.withExperimentContext(
          attribution ?? AnalyticsManager.captureExperimentContext(), () => _emit(event));
    } catch (_) {/* Observation never changes product behavior. */}
  }

  ProductAttempt start(ProductJourney journey,
      {ProductSurface surface = ProductSurface.unknown, RecordReference? objectId}) {
    final attempt =
        ProductAttempt._(this, journey, surface, objectId, EventCorrelation.mint(), _now(), _identityEpoch());
    _send(ProductJourneyStarted(
      correlationId: attempt._correlation,
      journey: ProductJourneyStartedJourney.values.byName(journey.name),
      surface: ProductJourneyStartedSurface.values.byName(surface.name),
      objectId: objectId,
    ));
    return attempt;
  }

  void value(ProductValue kind, {ProductSurface surface = ProductSurface.unknown, RecordReference? objectId}) {
    _send(ProductValueEvent(
      kind: ProductValueEventKind.values.byName(kind.name),
      surface: ProductValueEventSurface.values.byName(surface.name),
      objectId: objectId,
    ));
  }
}

class ProductAttempt {
  ProductAttempt._(
      this._owner, this.journey, this.surface, this._objectId, this._correlation, this._startedAt, this._epoch);
  final Map<String, Object> _attribution = AnalyticsManager.captureExperimentContext();
  final ProductTelemetry _owner;
  final ProductJourney journey;
  final ProductSurface surface;
  RecordReference? _objectId;
  final EventCorrelation _correlation;
  final DateTime _startedAt;
  final int _epoch;
  bool _terminal = false;
  bool _firstResult = false;

  String get correlationId => _correlation.value;
  bool get isComplete => _terminal;
  int get _elapsed => math.max(0, _owner._now().difference(_startedAt).inMilliseconds);
  bool get _current => _owner._identityEpoch() == _epoch;

  /// Bind the returned record only after its owner has supplied the real key.
  void bindObject(RecordReference? objectId) {
    if (!_terminal && _current) _objectId = objectId;
  }

  /// Call from a visible result/render boundary, not a transport callback alone.
  void firstResult() {
    if (_terminal || _firstResult || !_current) return;
    _firstResult = true;
    _owner._send(ProductJourneyFirstResult(
      correlationId: _correlation,
      journey: ProductJourneyFirstResultJourney.values.byName(journey.name),
      surface: ProductJourneyFirstResultSurface.values.byName(surface.name),
      objectId: _objectId,
      durationMs: _elapsed,
    ));
  }

  void complete(ProductOutcome outcome, {ProductFailure failure = ProductFailure.none, int? resultCount}) {
    if (_terminal) return;
    _terminal = true;
    if (!_current) return;
    final normalizedFailure = outcome == ProductOutcome.failure || outcome == ProductOutcome.unobserved
        ? (failure == ProductFailure.none ? ProductFailure.unknown : failure)
        : ProductFailure.none;
    _owner._send(
        ProductJourneyOutcome(
          correlationId: _correlation,
          journey: ProductJourneyOutcomeJourney.values.byName(journey.name),
          surface: ProductJourneyOutcomeSurface.values.byName(surface.name),
          objectId: _objectId,
          outcome: ProductJourneyOutcomeOutcome.values.byName(outcome.name),
          failure: ProductJourneyOutcomeFailure.values.byName(normalizedFailure.name),
          durationMs: _elapsed,
          resultCount: resultCount == null ? -1 : math.max(0, resultCount),
        ),
        _attribution);
  }
}
