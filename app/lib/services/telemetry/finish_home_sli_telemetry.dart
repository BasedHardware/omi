import 'dart:async';

import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:uuid/uuid.dart';

/// Durable, content-free Finish cuts used by the v3 TestFlight Home SLI.
class FinishHomeSliTelemetry {
  FinishHomeSliTelemetry({
    ClientTelemetryOutbox? outbox,
    DateTime Function()? clock,
    String Function()? newId,
    this.armFlushTimer = true,
  })  : clock = clock ?? DateTime.now,
        _newId = newId ?? _defaultId,
        outbox = outbox ??
            ClientTelemetryOutbox(
              store: MemoryTelemetryStore(),
              clock: clock ?? DateTime.now,
              newId: newId ?? _defaultId,
            );

  static final FinishHomeSliTelemetry instance = FinishHomeSliTelemetry();
  static const _uuid = Uuid();
  static String _defaultId() => _uuid.v4();

  final ClientTelemetryOutbox outbox;
  final DateTime Function() clock;
  final String Function() _newId;
  final bool armFlushTimer;

  bool Function()? testFlightEnabled;
  String? Function()? ownerId;
  String? Function()? platform;
  Timer? _flushTimer;

  Future<void> recordCut({
    required String operationId,
    required String source,
    required DateTime occurredAt,
  }) async {
    if (testFlightEnabled?.call() != true) return;
    final owner = ownerId?.call();
    final host = platform?.call();
    if (owner == null || owner.isEmpty || host == null || !ClientTelemetrySchema.isUuid(operationId)) {
      return;
    }
    if (source != 'app' && source != 'pendant') return;

    try {
      await outbox.add(
        ClientTelemetryObservation(
          ownerId: owner,
          eventId: _newId(),
          occurredAt: occurredAt.toUtc(),
          platform: host,
          channel: 'beta',
          family: 'finish_cut',
          attributes: {'operation_id': operationId, 'source': source},
          enqueuedAt: clock().toUtc(),
        ),
      );
      outbox.flush(onlyOwner: owner);
      _armTimer();
    } catch (_) {
      // A failed telemetry write must never prevent the user from finishing.
    }
  }

  void onOwnerChanged({String? previous, String? next}) {
    if (previous != null && previous.isNotEmpty && previous != next) {
      outbox.purgeOwner(previous, reason: 'owner_changed');
    }
    if (next != null && next.isNotEmpty) {
      outbox.flush(onlyOwner: next);
      _armTimer();
    }
  }

  void onBackground() {
    if (testFlightEnabled?.call() == true) {
      outbox.flush(onlyOwner: ownerId?.call());
    }
  }

  void start() {
    if (testFlightEnabled?.call() != true) return;
    outbox.flush(onlyOwner: ownerId?.call());
    _armTimer();
  }

  void _armTimer() {
    if (!armFlushTimer || _flushTimer?.isActive == true) return;
    _flushTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (testFlightEnabled?.call() == true) {
        outbox.flush(onlyOwner: ownerId?.call());
      }
    });
  }
}
