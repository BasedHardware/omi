import 'dart:async';

import 'package:omi/services/telemetry/client_telemetry_flags.dart';
import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:uuid/uuid.dart';

/// One admitted upload attempt, mirrored into the frozen upload family.
class UploadMirror {
  const UploadMirror({
    required this.attemptId,
    required this.phase,
    required this.source,
    required this.occurredAt,
    this.latencyMs,
    this.httpStatus,
    this.failureClass,
    this.jobId,
  });

  final String attemptId;
  final String phase;
  final String source;
  final DateTime occurredAt;
  final int? latencyMs;
  final int? httpStatus;
  final String? failureClass;
  final String? jobId;
}

class _UploadAttempt {
  _UploadAttempt({
    required this.operationId,
    required this.source,
    required this.startedAt,
    required this.ownerId,
  });

  final String operationId;
  final String source;
  final DateTime startedAt;
  final String ownerId;
}

class _ProcessingAnchor {
  _ProcessingAnchor({
    required this.operationId,
    required this.startedAt,
    required this.ownerId,
    required this.elapsedMs,
  });

  final String operationId;
  final DateTime startedAt;
  final String ownerId;

  /// sol blocker: monotonic clock sample taken at anchor creation; latency is
  /// `monotonicElapsedMs() - elapsedMs`, immune to wall-clock steps.
  final int elapsedMs;
}

/// Flutter client telemetry. Migration and PostHog retirement stay off until
/// the parent enables them. Callers must not await this type on capture paths.
class ClientTelemetry {
  ClientTelemetry({
    ClientTelemetryOutbox? outbox,
    DateTime Function()? clock,
    int Function()? monotonicElapsedMs,
    String Function()? newId,
    this.armFlushTimer = true,
  })  : clock = clock ?? DateTime.now,
        monotonicElapsedMs = monotonicElapsedMs ?? (() => DateTime.now().millisecondsSinceEpoch),
        _newId = newId ?? _defaultId,
        outbox = outbox ??
            ClientTelemetryOutbox(
              store: MemoryTelemetryStore(),
              clock: clock ?? DateTime.now,
              newId: newId ?? _defaultId,
            );

  static final ClientTelemetry instance = ClientTelemetry();
  static const _uuid = Uuid();
  static String _defaultId() => _uuid.v4();

  final ClientTelemetryOutbox outbox;
  final DateTime Function() clock;

  /// Monotonic elapsed-milliseconds source for latency anchors. Production
  /// uses the system stopwatch clock; tests inject a controllable clock.
  final int Function() monotonicElapsedMs;
  final String Function() _newId;
  final bool armFlushTimer;

  String? Function()? ownerId;
  String? Function()? platform;
  String? Function()? channel;

  final Map<String, _UploadAttempt> _attempts = {};
  final Map<String, _ProcessingAnchor> _processing = {};
  final Map<String, String> _ingressOperationIds = {};
  final Map<String, String> _ingressTuples = {};
  int disappearedWithoutTerminal = 0;
  int ingressDuplicatesSuppressed = 0;
  Timer? _flushTimer;

  Future<void> get settled => outbox.settled;

  static String uploadSourceForWal({required String storage, String? originalStorage, required String device}) {
    if (storage == 'sdcard' || originalStorage == 'sdcard') return 'sdcard';
    if (storage == 'flashPage' || originalStorage == 'flashPage') return 'pendant';
    final normalized = device.toLowerCase();
    if (normalized == 'phone' || normalized.contains('phone')) return 'phone';
    return 'unknown';
  }

  static String uploadSourceForBatch(Iterable<({String storage, String? originalStorage, String device})> wals) {
    final sources = wals
        .map(
          (wal) => uploadSourceForWal(storage: wal.storage, originalStorage: wal.originalStorage, device: wal.device),
        )
        .toSet();
    if (sources.length == 1) return sources.single;
    return 'unknown';
  }

  void onOwnerChanged({String? previous, String? next}) {
    if (previous != null && previous.isNotEmpty && (next == null || next.isEmpty)) {
      outbox.purgeOwner(previous, reason: 'logout');
      _attempts.removeWhere((_, attempt) => attempt.ownerId == previous);
      _processing.clear();
    }
  }

  void onBackground() {
    if (!ClientTelemetryFlags.migrationEnabled) return;
    outbox.flush(onlyOwner: ownerId?.call());
  }

  void observeUpload(UploadMirror mirror) {
    if (!ClientTelemetryFlags.migrationEnabled) return;
    final owner = ownerId?.call();
    final host = platform?.call();
    final release = channel?.call();
    final occurredAt = mirror.occurredAt.toUtc();
    outbox.schedule(() async {
      if (owner == null || owner.isEmpty) return;
      if (host == null || release == null) {
        _drop(owner, 'context_unavailable');
        return;
      }
      if (!ClientTelemetrySchema.isUuid(mirror.attemptId) ||
          !ClientTelemetrySchema.uploadPhases.contains(mirror.phase)) {
        _drop(owner, 'invalid_observation');
        return;
      }
      final attempt = _attempts.putIfAbsent(
        mirror.attemptId,
        () => _UploadAttempt(
          operationId: _newId(),
          source: mirror.source,
          startedAt: occurredAt,
          ownerId: owner,
        ),
      );
      if (attempt.ownerId != owner) return;
      final failureClass = mirror.phase == 'failed'
          ? ClientTelemetrySchema.mapLegacyUploadFailure(mirror.failureClass, httpStatus: mirror.httpStatus)
          : null;
      final operationId = attempt.operationId;
      if (!ClientTelemetrySchema.isUuid(operationId)) {
        await outbox.recordDrop(owner, 'invalid_observation');
        return;
      }
      await outbox.add(
        ClientTelemetryObservation(
          ownerId: owner,
          eventId: _newId(),
          occurredAt: occurredAt,
          platform: host,
          channel: release,
          family: 'upload',
          attributes: ClientTelemetrySchema.uploadAttributes(
            attemptId: mirror.attemptId,
            phase: mirror.phase,
            source: mirror.source,
            httpStatus: mirror.httpStatus,
            failureClass: failureClass,
            latencyMs: mirror.phase == 'started' ? null : mirror.latencyMs,
            operationId: operationId,
          ),
          enqueuedAt: clock().toUtc(),
        ),
      );
      if (mirror.phase == 'accepted' && mirror.jobId != null && mirror.jobId!.isNotEmpty) {
        await outbox.saveAcceptedJob(
          mirror.jobId!,
          AcceptedUploadJob(
            ownerId: owner,
            attemptId: mirror.attemptId,
            operationId: operationId,
            source: ClientTelemetrySchema.uploadSources.contains(mirror.source) ? mirror.source : 'unknown',
            startedAt: attempt.startedAt,
          ),
        );
      }
      _armTimer();
    });
  }

  void observeUploadDurableCompleted({required String? jobId, required DateTime confirmedAt}) {
    if (!ClientTelemetryFlags.migrationEnabled || jobId == null || jobId.isEmpty) return;
    final host = platform?.call();
    final release = channel?.call();
    if (host == null || host.isEmpty || release == null || release.isEmpty) return;
    outbox.completeAcceptedJob(
      jobId: jobId,
      build: (job) {
        // sol blocker: the accepted job may have been persisted by a previous
        // process; a wall-clock delta across restart fabricates latency, so
        // omit latency whenever the anchor is older than the max credible
        // window instead of reporting it.
        final wallLatency = confirmedAt.toUtc().difference(job.startedAt).inMilliseconds;
        final latency = wallLatency >= 0 && wallLatency <= ClientTelemetrySchema.maxLatencyMs ? wallLatency : null;
        return ClientTelemetryObservation(
          ownerId: job.ownerId,
          eventId: _newId(),
          occurredAt: confirmedAt.toUtc(),
          platform: host,
          channel: release,
          family: 'upload',
          attributes: ClientTelemetrySchema.uploadAttributes(
            attemptId: job.attemptId,
            phase: 'completed',
            source: job.source,
            latencyMs: latency,
            operationId: job.operationId,
          ),
          enqueuedAt: clock().toUtc(),
        );
      },
    );
  }

  void noteProcessingVisible(String id, {bool freshAttempt = false}) {
    if (!ClientTelemetryFlags.migrationEnabled || id.isEmpty || id == '0') return;
    final owner = ownerId?.call();
    if (owner == null || owner.isEmpty) return;
    if (freshAttempt) _processing.remove(id);
    _processing.putIfAbsent(
      id,
      () => _ProcessingAnchor(
        operationId: _newId(),
        startedAt: clock().toUtc(),
        ownerId: owner,
        elapsedMs: monotonicElapsedMs(),
      ),
    );
  }

  void noteProcessingRowLeft({
    required String id,
    required bool lifecycleOk,
    String? lifecycleStatus,
    String? pageStatus,
  }) {
    if (!ClientTelemetryFlags.migrationEnabled) return;
    final anchor = _processing.remove(id);
    if (anchor == null) return;
    // sol blocker: owner fencing — a terminal under a different account than
    // the anchor's creator is dropped (never attributed across accounts).
    final currentOwner = ownerId?.call();
    if (currentOwner == null || currentOwner.isEmpty || currentOwner != anchor.ownerId) return;
    final outcome = ClientTelemetrySchema.processingOutcome(
      lifecycleOk: lifecycleOk,
      lifecycleStatus: lifecycleStatus,
      pageStatus: pageStatus,
    );
    if (outcome == null) {
      disappearedWithoutTerminal += 1;
      return;
    }
    final context = _emissionContext();
    if (context == null) return;
    // sol blocker: monotonic elapsed time only. A wall-clock delta across a
    // restart or NTP step fabricates latency; the anchor's stopwatch clock
    // dies with the process, so a lost anchor simply omits latency.
    final latency = monotonicElapsedMs() - anchor.elapsedMs;
    final basis = latency >= 0 && latency <= ClientTelemetrySchema.maxLatencyMs ? 'processing_observed' : null;
    _enqueue(
      ownerId: context.owner,
      occurredAt: clock().toUtc(),
      platform: context.platform,
      channel: context.channel,
      family: 'conversation_processing',
      attributes: {
        'operation_id': anchor.operationId,
        'outcome': outcome,
        if (basis != null) 'latency_ms': latency,
        if (basis != null) 'latency_basis': basis,
      },
    );
  }

  void observeIngress({
    required String generation,
    required String phase,
    required String reason,
    required bool subscriptionConfirmed,
    required String recoveryOutcome,
    required bool recoverySpent,
    required bool reconnectSpent,
  }) {
    if (!ClientTelemetryFlags.migrationEnabled || generation.isEmpty) return;
    final mappedPhase = ClientTelemetrySchema.mapIngressPhase(phase);
    final mappedReason = ClientTelemetrySchema.mapIngressReason(reason);
    final mappedRecovery = ClientTelemetrySchema.mapRecoveryOutcome(recoveryOutcome);
    final tuple = '$generation|$mappedPhase|$mappedReason|$subscriptionConfirmed|$mappedRecovery|'
        '$recoverySpent|$reconnectSpent';
    if (_ingressTuples[generation] == tuple) {
      ingressDuplicatesSuppressed += 1;
      return;
    }
    final context = _emissionContext();
    if (context == null) return;
    if (!_ingressOperationIds.containsKey(generation) &&
        _ingressOperationIds.length >= ClientTelemetrySchema.maxOutboxObservations) {
      final oldest = _ingressOperationIds.keys.first;
      _ingressOperationIds.remove(oldest);
      _ingressTuples.remove(oldest);
    }
    _ingressTuples[generation] = tuple;
    final operationId = _ingressOperationIds.putIfAbsent(generation, _newId);
    _enqueue(
      ownerId: context.owner,
      occurredAt: clock().toUtc(),
      platform: context.platform,
      channel: context.channel,
      family: 'capture_ingress',
      attributes: {
        'operation_id': operationId,
        'phase': mappedPhase,
        'reason': mappedReason,
        'subscription_confirmed': subscriptionConfirmed,
        'recovery_outcome': mappedRecovery,
        'recovery_spent': recoverySpent,
        'reconnect_spent': reconnectSpent,
      },
    );
  }

  void observeWedge({
    required String operationId,
    required String phase,
    required String trigger,
    required String outcome,
    int? latencyMs,
  }) {
    if (!ClientTelemetryFlags.migrationEnabled) return;
    if (!ClientTelemetrySchema.isUuid(operationId)) return;
    final context = _emissionContext();
    if (context == null) return;
    final mappedPhase = ClientTelemetrySchema.wedgePhases.contains(phase) ? phase : 'detected';
    final mappedOutcome = ClientTelemetrySchema.wedgeOutcomes.contains(outcome) ? outcome : 'unknown';
    _enqueue(
      ownerId: context.owner,
      occurredAt: clock().toUtc(),
      platform: context.platform,
      channel: context.channel,
      family: 'capture_wedge',
      attributes: {
        'operation_id': operationId,
        'phase': mappedPhase,
        'trigger': ClientTelemetrySchema.mapWedgeTrigger(trigger),
        'outcome': mappedOutcome,
        if (latencyMs != null && latencyMs >= 0 && latencyMs <= ClientTelemetrySchema.maxLatencyMs)
          'latency_ms': latencyMs,
      },
    );
  }

  void observeDeviceSession({
    required String operationId,
    required String analyticsVendor,
    required Duration duration,
    String? reason,
    int? hciReasonCode,
    bool intentional = false,
    String recoveryOutcome = 'unknown',
  }) {
    if (!ClientTelemetryFlags.migrationEnabled) return;
    if (!ClientTelemetrySchema.isUuid(operationId)) return;
    final context = _emissionContext();
    if (context == null) return;
    final durationMs = duration.inMilliseconds;
    if (durationMs < 0 || durationMs > ClientTelemetrySchema.maxSessionDurationMs) {
      _drop(context.owner, 'schema_bounds');
      return;
    }
    final hci = hciReasonCode != null && hciReasonCode >= 0 && hciReasonCode <= 255 ? hciReasonCode : null;
    _enqueue(
      ownerId: context.owner,
      occurredAt: clock().toUtc(),
      platform: context.platform,
      channel: context.channel,
      family: 'device_session',
      attributes: {
        'operation_id': operationId,
        'vendor': ClientTelemetrySchema.mapVendor(analyticsVendor),
        'disconnect_class': ClientTelemetrySchema.mapDisconnectClass(reason, intentional: intentional),
        'recovery_outcome': ClientTelemetrySchema.mapRecoveryOutcome(
          intentional ? 'none' : recoveryOutcome,
        ),
        'duration_ms': durationMs,
        if (hci != null) 'hci_reason_code': hci,
        'intentional': intentional,
      },
    );
  }

  ({String owner, String platform, String channel})? _emissionContext() {
    final owner = ownerId?.call();
    final host = platform?.call();
    final release = channel?.call();
    if (owner == null || owner.isEmpty) return null;
    if (host == null ||
        release == null ||
        !ClientTelemetrySchema.platforms.contains(host) ||
        !ClientTelemetrySchema.channels.contains(release)) {
      _drop(owner, 'context_unavailable');
      return null;
    }
    return (owner: owner, platform: host, channel: release);
  }

  void _enqueue({
    required String ownerId,
    required DateTime occurredAt,
    required String platform,
    required String channel,
    required String family,
    required Map<String, Object?> attributes,
  }) {
    final operationId = attributes['operation_id'];
    if (operationId is! String || !ClientTelemetrySchema.isUuid(operationId)) {
      _drop(ownerId, 'invalid_observation');
      return;
    }
    outbox.enqueue(
      ClientTelemetryObservation(
        ownerId: ownerId,
        eventId: _newId(),
        occurredAt: occurredAt,
        platform: platform,
        channel: channel,
        family: family,
        attributes: attributes,
        enqueuedAt: clock().toUtc(),
      ),
    );
    _armTimer();
  }

  void _drop(String ownerId, String reason) {
    outbox.schedule(() => outbox.recordDrop(ownerId, reason));
  }

  void _armTimer() {
    if (!armFlushTimer || _flushTimer != null) return;
    _flushTimer = Timer(ClientTelemetrySchema.flushInterval, () async {
      _flushTimer = null;
      // flush() schedules onto the outbox's serial queue (void return); the
      // awaited hasPending below is ordered behind it on the same queue.
      outbox.flush(onlyOwner: ownerId?.call());
      // sol blocker: one-shot timer never rearmed after flushing, so a
      // non-empty outbox could sit idle until the *next* enqueue. Keep
      // draining until the outbox is empty, then go quiet.
      if (await outbox.hasPending(onlyOwner: ownerId?.call())) {
        _armTimer();
      }
    });
  }
}
