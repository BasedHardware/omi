// Durable, content-free client observations for deliberate TestFlight Finishes.
// These cuts are persisted before capture drains and retried independently.
import 'dart:async';

import 'package:omi/services/telemetry/client_telemetry_outbox.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:uuid/uuid.dart';

/// What the user acted on to ask for a Finish. A cut's `source` comes from this, never from
/// whether the request names a live conversation.
enum FinishCutSource {
  /// The phone: the live page, Home Wrap Up, record stop, the live conversation's End button, or
  /// a Live Activity.
  app('app'),

  /// The pendant's own button (double tap).
  pendant('pendant');

  const FinishCutSource(this.wire);

  /// The value sent as the cut's `source` and in `X-Omi-Finish-Cut`.
  final String wire;
}

/// Durable, content-free Finish cuts used by the v3 TestFlight Home SLI.
class FinishHomeSliTelemetry {
  FinishHomeSliTelemetry({
    ClientTelemetryOutbox? outbox,
    DateTime Function()? clock,
    String Function()? newId,
    this.armFlushTimer = true,
    bool deferUntilInstalled = false,
  })  : clock = clock ?? DateTime.now,
        _newId = newId ?? _defaultId,
        _installed = !deferUntilInstalled,
        outbox = outbox ??
            ClientTelemetryOutbox(
              store: MemoryTelemetryStore(),
              clock: clock ?? DateTime.now,
              newId: newId ?? _defaultId,
            );

  /// The app's instance starts on an in-memory store and gets its file store from [install]. Until then it
  /// must not load the outbox: a load binds the outbox to its current store, so a flush from the first
  /// identity bind (which runs before the transport is installed) would pin it to memory and every cut
  /// recorded afterwards would be lost on restart.
  static final FinishHomeSliTelemetry instance = FinishHomeSliTelemetry(deferUntilInstalled: true);
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
  bool _installed;

  /// Owners whose queued cuts an owner change before [install] retired; purged once the store is attached.
  final Set<String> _purgeOnInstall = {};

  /// Whether [install] attached persistence (always true for an instance built without deferral).
  bool get installed => _installed;

  /// Attaches the durable store and transport, then applies owner changes seen before installation and
  /// flushes the current owner. The store is attached before anything loads the outbox.
  void install({
    required ClientTelemetryStore store,
    required bool Function() testFlightEnabled,
    required String? Function() ownerId,
    required String? Function() platform,
    required TelemetryToken tokenFor,
    required TelemetryPost post,
  }) {
    this.testFlightEnabled = testFlightEnabled;
    this.ownerId = ownerId;
    this.platform = platform;
    outbox.attachStore(store);
    outbox.tokenFor = tokenFor;
    outbox.post = post;
    _installed = true;
    for (final owner in _purgeOnInstall) {
      outbox.purgeOwner(owner, reason: 'owner_changed');
    }
    _purgeOnInstall.clear();
    start();
  }

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
    if (!_installed) {
      // Remember the change without loading the outbox; [install] applies it once the store is attached.
      if (previous != null && previous.isNotEmpty && previous != next) _purgeOnInstall.add(previous);
      if (next != null && next.isNotEmpty) _purgeOnInstall.remove(next);
      return;
    }
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
