import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_composition.dart';
import 'package:omi/services/capture/capture_ingress_health.dart';
import 'package:omi/services/capture/conversation_source_for_device.dart';
import 'package:omi/services/telemetry/client_telemetry.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';
import 'package:uuid/uuid.dart';

const String captureRecoveryFeatureFlag = 'mobile-capture-recovery-v1';

class CaptureWedgeEpisode {
  CaptureWedgeEpisode({required this.deviceId, required this.source, required this.trigger, required this.declaredAt});

  final String deviceId;
  final String source;
  final String trigger;
  final DateTime declaredAt;

  bool retryAttempted = false;
  bool promptVisible = false;
  bool promptShownEmitted = false;
  String? telemetryOperationId;
  DateTime? ingressRecoveryStartedAt;
  DateTime? lastRecoveryByteAt;
}

/// Phone-disk admission failures engaged: new recordings cannot be written until
/// space frees or retention changes. A slow-burn problem, so it lives in
/// Activity's Needs attention section, never in a banner.
class CaptureStorageAtRisk {
  const CaptureStorageAtRisk({
    required this.engagedAt,
    required this.blockedCount,
    required this.retainedCount,
    required this.reason,
  });

  final DateTime engagedAt;

  /// Recordings the disk could not admit.
  final int blockedCount;

  /// Recordings kept under the admission count cap.
  final int retainedCount;

  final String reason;
}

/// A WAL backlog with no upload progress for
/// [CaptureWedgeMonitor.uploadSilenceThreshold]: the recordings wait on the
/// phone, safe but not moving. Listed in Activity's Needs attention section.
class CaptureUploadStall {
  const CaptureUploadStall({required this.since, required this.pendingCount, required this.pendingSeconds});

  /// When the stall was first declared; counts refresh while it persists.
  final DateTime since;

  /// Recordings waiting to upload.
  final int pendingCount;

  /// Kept-audio length across the pending recordings, 0 when unknown.
  final int pendingSeconds;
}

typedef CaptureWedgeTrack = void Function(String event, Map<String, Object> properties);

class CaptureWedgeMonitor extends ChangeNotifier {
  CaptureWedgeMonitor({
    DateTime Function()? now,
    required Future<bool> Function() featureGate,
    required CaptureWedgeTrack track,
    required Future<void> Function(String deviceId) bleRetry,
    Future<void> Function()? transferRetry,
    required String Function() appBuild,
    required String Function() platform,
  })  : _now = now ?? DateTime.now,
        _featureGate = featureGate,
        _track = track,
        _bleRetry = bleRetry,
        _transferRetry = transferRetry,
        _appBuild = appBuild,
        _platform = platform;

  static CaptureWedgeMonitor? _instance;
  static CaptureWedgeMonitor get instance => _instance ??= composeCaptureWedgeMonitor();
  static set instance(CaptureWedgeMonitor monitor) => _instance = monitor;

  static const Duration zeroByteWindow = Duration(minutes: 10);
  static const int zeroByteThreshold = 3;
  static const Duration rapidDropWindow = Duration(minutes: 5);
  static const Duration rapidDropMaxDuration = Duration(seconds: 15);
  static const int rapidDropThreshold = 3;
  static const Duration resolveWindow = Duration(minutes: 30);
  static const Duration retryTimeout = Duration(seconds: 10);
  static const Duration uploadSilenceThreshold = Duration(hours: 2);
  static const Duration noTranscriptWindow = Duration(minutes: 10);
  static const int noTranscriptThreshold = 3;
  static const Duration connectedWatchdogInterval = Duration(seconds: 30);
  static const Duration connectedNoTranscriptWindow = Duration(minutes: 2);

  /// Longer than [connectedNoTranscriptWindow]: a quiet room still delivers
  /// audio packets, so only a multi-minute gap with no BLE notifications is a
  /// stalled link.
  static const Duration connectedNoBytesWindow = Duration(minutes: 5);
  static const Duration ingressRecoveryWindow = Duration(seconds: 5);
  static const Duration ingressRecoveryMaxGap = Duration(seconds: 2);

  static const String triggerZeroByteStreak = 'zero_byte_streak';
  static const String triggerRapidReconnects = 'rapid_reconnects';
  static const String triggerBytesSentNoTranscript = 'bytes_sent_no_transcript';
  static const String triggerConnectedNoBytes = 'connected_no_bytes';
  static const String triggerUploadSilence = 'upload_silence';
  static const String triggerStorageAtRisk = 'storage_at_risk';
  static const String triggerIngressRecoveryFailed = 'ingress_recovery_failed';
  static const String localWalDeviceId = 'local-wal';
  static const String localWalSource = 'local_wal';

  final DateTime Function() _now;
  final Future<bool> Function() _featureGate;
  final CaptureWedgeTrack _track;
  final Future<void> Function(String deviceId) _bleRetry;
  final Future<void> Function()? _transferRetry;
  final String Function() _appBuild;
  final String Function() _platform;

  final Map<String, _DeviceWedgeState> _devices = {};
  final Map<String, String> _ingressEvents = {};
  final Set<String> _nativeIngressDevices = {};
  final Set<String> _cccdRecoveryDevices = {};

  CaptureStorageAtRisk? _storageAtRisk;
  CaptureUploadStall? _uploadStall;
  DateTime? _captureAttentionSeenAt;

  /// The latest slow-burn local capture state, for Activity's Needs attention rows.
  CaptureStorageAtRisk? get storageAtRisk => _storageAtRisk;

  CaptureUploadStall? get uploadStall => _uploadStall;

  /// The acute link episode the reader is being asked about (a stalled or
  /// silent pendant link, or an exhausted ingress recovery), if any. The
  /// storage episode shares the prompt slot but is slow-burn: it has its own
  /// [storageAtRisk] row, so it is not acute.
  CaptureWedgeEpisode? get acuteEpisode {
    // Every device, not just [visiblePrompt]'s first hit: an open storage episode on the local
    // WAL must not hide a pendant stall behind it.
    for (final state in _devices.values) {
      final episode = state.episode;
      if (episode != null && episode.promptVisible && episode.trigger != triggerStorageAtRisk) return episode;
    }
    return null;
  }

  /// Whether an acute link episode is open at all, prompt shown or not: it also holds while the
  /// reader's retry is in flight (the prompt steps aside until that retry settles), so the live
  /// header keeps saying "Reconnecting" instead of falling back to a live label while no audio
  /// reaches the app.
  bool get linkStalled {
    for (final state in _devices.values) {
      final episode = state.episode;
      if (episode != null && episode.trigger != triggerStorageAtRisk) return true;
    }
    return false;
  }

  bool get hasCaptureAttention => _storageAtRisk != null || _uploadStall != null || acuteEpisode != null;

  /// True while a capture attention row is newer than the last Activity visit:
  /// lights the bell's warning dot. A new episode re-lights it. Acute link
  /// episodes count too: Home has no banner, so the dot is how a stall reaches
  /// a reader who is not on the live page.
  final ValueNotifier<bool> hasUnseenCaptureAttention = ValueNotifier(false);

  /// Records that Activity rendered its capture rows. With [through], marks
  /// seen only the episodes a build actually included: the timestamp of the
  /// newest row on screen at build time. An incident declared after that build
  /// stays unseen — the bell keeps warning — until a frame shows its row. The
  /// seen timestamp never rewinds.
  void markCaptureAttentionSeen({DateTime? through}) {
    final at = through ?? _now();
    final seen = _captureAttentionSeenAt;
    _captureAttentionSeenAt = seen == null || seen.isBefore(at) ? at : seen;
    _updateUnseenCaptureAttention();
  }

  /// Activity showed its capture attention rows: the bell goes dark until a new
  /// episode arrives. In memory only — after a restart the live observations
  /// re-declare any condition that still holds.
  void _updateUnseenCaptureAttention() {
    final seen = _captureAttentionSeenAt;
    final storage = _storageAtRisk;
    final upload = _uploadStall;
    final acute = acuteEpisode;
    hasUnseenCaptureAttention.value = (storage != null && (seen == null || storage.engagedAt.isAfter(seen))) ||
        (upload != null && (seen == null || upload.since.isAfter(seen))) ||
        (acute != null && (seen == null || acute.declaredAt.isAfter(seen)));
  }

  /// Every episode change (declared, retried, resolved, dismissed) passes through
  /// here, so the bell's acute half stays in step without each path recomputing it.
  @override
  void notifyListeners() {
    _updateUnseenCaptureAttention();
    super.notifyListeners();
  }

  /// Ends the slow-burn rows the way their episodes end: resolved, dismissed, or reset.
  void _clearCaptureAttention() {
    if (_storageAtRisk == null && _uploadStall == null) return;
    _storageAtRisk = null;
    _uploadStall = null;
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  /// Ends the storage row the way its own condition ends: the disk admitted a
  /// write again (or the retention diagnostic stopped reporting a risk). Upload
  /// progress must not clear it — a full disk keeps refusing recordings while
  /// an unrelated backlog drains. The retention fingerprint resets so a risk
  /// that re-reports after a clear re-engages the row instead of being ignored.
  void clearStorageAtRisk() {
    if (_storageAtRisk == null) return;
    _storageAtRisk = null;
    _lastRetentionRiskFingerprint = null;
    _resolveStorageEpisodeIfAny();
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  /// Ends a storage row engaged by disk-admission failure without touching the
  /// retention fingerprint: the caller has a fresher observation whose telemetry
  /// dedupe must hold, and whose reason differs, so a returning disk failure
  /// re-engages the row on its own fingerprint.
  void _endStorageAtRiskRow() {
    if (_storageAtRisk == null) return;
    _storageAtRisk = null;
    _resolveStorageEpisodeIfAny();
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  /// A storage row ending with its own condition also ends the local-WAL
  /// episode that declared it: the capturing page's banner must stop reporting
  /// a recovered storage problem, and `_canDeclare` must let a later disk
  /// incident start a fresh recovery. The upload-silence telemetry episode is
  /// independent and stays for `onUploadCompleted` to later resolve on its own
  /// terms.
  void _resolveStorageEpisodeIfAny() {
    final state = _devices[localWalDeviceId];
    if (state?.episode?.trigger == triggerStorageAtRisk) {
      _safeTrack('Capture Recovery Resolved', {'source': state!.episode!.source, 'trigger': triggerStorageAtRisk});
      state.episode = null;
    }
  }

  void setNativeIngressOwner(String deviceId, bool active) {
    if (active) {
      _nativeIngressDevices.add(deviceId);
    } else {
      _nativeIngressDevices.remove(deviceId);
      _ingressEvents.remove(deviceId);
      observeIngressHealth(deviceId, null);
    }
  }

  /// Native owns this recovery. Never start a second BLE retry from the banner
  /// projection, or let a transcript resolve an ingress failure.
  void observeIngressHealth(String deviceId, CaptureIngressHealth? health) {
    final state = _stateFor(deviceId);
    final previousHealth = state.lastIngressHealth;
    state.lastIngressHealth = health;
    if (health?.reason == CaptureIngressHealth.cccdRecoveryReason) {
      _cccdRecoveryDevices.add(deviceId);
      _nativeIngressDevices.add(deviceId);
      if (state.episode?.trigger != triggerIngressRecoveryFailed) state.episode = null;
    } else if (_cccdRecoveryDevices.remove(deviceId)) {
      _nativeIngressDevices.remove(deviceId);
    }
    if (health != null) {
      final event = '${health.generation}:${health.phase}:${health.reason}:'
          '${health.subscriptionConfirmed}:${health.recoveryOutcome}:${health.recoverySpent}:${health.reconnectSpent}';
      if (_ingressEvents[deviceId] != event) {
        _ingressEvents[deviceId] = event;
        if (!ClientTelemetrySchema.ingressPhaseMapped(health.phase)) {
          DebugLogManager.logEvent('capture_ingress_unmapped_phase', {'phase': 'unmapped'});
        }
        try {
          ClientTelemetry.instance.observeIngress(
            generation: health.generation,
            phase: health.phase,
            reason: health.reason,
            subscriptionConfirmed: health.subscriptionConfirmed,
            recoveryOutcome: health.recoveryOutcome,
            recoverySpent: health.recoverySpent,
            reconnectSpent: health.reconnectSpent,
          );
        } catch (_) {}
        _safeTrack('Capture Ingress Health', {
          'phase': health.phase,
          'reason': health.reason,
          'connection_generation': health.generation,
          'subscription_confirmed': health.subscriptionConfirmed,
          'unverified_since_ms': health.unverifiedSinceMs,
          'recovery_outcome': health.recoveryOutcome,
          'recovery_spent': health.recoverySpent,
          'reconnect_spent': health.reconnectSpent,
        });
      }
    }
    if (health?.actionable == true) {
      final dismissedGeneration = state.dismissedIngressGeneration;
      final sameIncident = dismissedGeneration != null && health!.generation == dismissedGeneration;
      if (!sameIncident && state.episode?.trigger != triggerIngressRecoveryFailed) {
        state.episode = CaptureWedgeEpisode(
          deviceId: deviceId,
          source: 'omi',
          trigger: triggerIngressRecoveryFailed,
          declaredAt: _now(),
        )..retryAttempted = true;
      }
      if (!sameIncident) state.episode?.promptVisible = true;
    } else {
      if (state.episode?.trigger == triggerIngressRecoveryFailed) state.episode = null;
      // Health left actionRequired (or the owner went away): the incident is
      // over, so a later actionable snapshot of a *new* incident may alert.
      state.dismissedIngressGeneration = null;
    }
    // A new, valid native ingress lease proves recovery independently of STT.
    // Replaying the same cached lease must not resolve a later BLE episode.
    if (health != null &&
        health.verifiedAt(_now()) &&
        (previousHealth?.generation != health.generation ||
            health.validUntilMs > (previousHealth?.validUntilMs ?? 0))) {
      _resolveIfActive(deviceId, state, bleIngressOnly: true);
    }
    notifyListeners();
  }

  final Map<int, _OpenCaptureSession> _openSessions = {};
  final Set<String> _retryInFlightDevices = {};
  DateTime? _lastUploadAt;
  Timer? _connectedWatchdog;
  String? _lastRetentionRiskFingerprint;
  int _nextSessionHandle = 0;

  static bool isCaptureSourceInScope(String? source) => source == 'omi' || source == 'friend_com';

  _DeviceWedgeState _stateFor(String deviceId) => _devices.putIfAbsent(deviceId, _DeviceWedgeState.new);

  int onCaptureSessionConnected({required String deviceId, required String source}) {
    if (!isCaptureSourceInScope(source)) return -1;
    final handle = ++_nextSessionHandle;
    _openSessions[handle] = _OpenCaptureSession(deviceId: deviceId, source: source, connectedAt: _now());
    _connectedWatchdog ??= Timer.periodic(connectedWatchdogInterval, (_) => runConnectedWatchdog());
    return handle;
  }

  /// Accounts bytes accepted by an open transcription socket. A connected
  /// socket is not evidence of backend progress, so the periodic watchdog can
  /// declare a wedge even when the socket never closes.
  void onSocketBytesSent(int handle, int byteCount) {
    if (byteCount <= 0) return;
    final session = _openSessions[handle];
    if (session == null) return;
    session.bytesSinceTranscript += byteCount;
  }

  /// Counts BLE notification payloads for an open capture session. Socket
  /// sends are a different counter: a connected socket with nothing on the
  /// radio must not look like a quiet transcript.
  void onBleIngressBytes(String deviceId, int byteCount) {
    if (byteCount <= 0) return;
    final now = _now();
    for (final session in _openSessions.values) {
      if (session.deviceId != deviceId) continue;
      session.ingressBytes += byteCount;
      session.lastIngressByteAt = now;
      session.lastBleIngressAt = now;
    }
    final state = _devices[deviceId];
    final episode = state?.episode;
    if (state == null || episode == null || !_isBleIngressTrigger(episode.trigger)) return;
    final lastByte = episode.lastRecoveryByteAt;
    if (lastByte == null || now.difference(lastByte) > ingressRecoveryMaxGap) {
      episode.ingressRecoveryStartedAt = now;
    }
    episode.lastRecoveryByteAt = now;
    if (now.difference(episode.ingressRecoveryStartedAt!) >= ingressRecoveryWindow) {
      _resolveIfActive(deviceId, state, bleIngressOnly: true);
    }
  }

  /// Batch owns transcription while BLE ingress still needs liveness checks.
  /// A live handback starts a fresh transcript deadline without inventing text.
  void setTranscriptExpected(int handle, bool expected) {
    final session = _openSessions[handle];
    if (session == null || session.expectsTranscript == expected) return;
    session.expectsTranscript = expected;
    session.bytesSinceTranscript = 0;
    session.transcriptRequiredSince = expected ? _now() : null;
    session.watchdogDeclared = false;
  }

  /// Records an actual transcript outcome for every currently open socket for
  /// this device. Transport bytes alone are not proof that transcription is
  /// alive; this signal is deliberately separate from binary-byte accounting.
  void onTranscriptObserved(String deviceId) {
    for (final session in _openSessions.values) {
      if (session.deviceId == deviceId) {
        session.transcriptObserved = true;
        session.transcriptRequiredSince = null;
        session.bytesSinceTranscript = 0;
        session.lastTranscriptAt = _now();
        session.lastIngressByteAt = session.lastTranscriptAt;
        session.watchdogDeclared = false;
      }
    }
    final state = _devices[deviceId];
    if (state == null) return;
    state.noTranscriptSessionEnds.clear();
    _resolveIfActive(deviceId, state);
  }

  void onCaptureSessionEnded(int handle, {required int binaryBytesSent, bool intentional = false}) {
    final session = _openSessions.remove(handle);
    if (session == null) return;
    if (_openSessions.isEmpty) {
      _connectedWatchdog?.cancel();
      _connectedWatchdog = null;
    }
    final state = _stateFor(session.deviceId);
    if (binaryBytesSent > 0 && session.transcriptObserved) {
      state.zeroByteSessionEnds.clear();
      state.noTranscriptSessionEnds.clear();
      _resolveIfActive(session.deviceId, state);
      return;
    }
    if (intentional || !session.expectsTranscript) return;
    final now = _now();
    if (binaryBytesSent > 0) {
      final ends = state.noTranscriptSessionEnds;
      ends.add(now);
      ends.removeWhere((t) => now.difference(t) > noTranscriptWindow);
      if (ends.length >= noTranscriptThreshold &&
          ends.last.difference(ends[ends.length - noTranscriptThreshold]) <= noTranscriptWindow) {
        unawaited(
          _maybeDeclare(
            state,
            deviceId: session.deviceId,
            source: session.source,
            trigger: triggerBytesSentNoTranscript,
            requireFeatureGate: false,
            depthSession: session,
          ),
        );
      }
      return;
    }
    final ends = state.zeroByteSessionEnds;
    ends.add(now);
    ends.removeWhere((t) => now.difference(t) > zeroByteWindow);
    if (ends.length >= zeroByteThreshold &&
        ends.last.difference(ends[ends.length - zeroByteThreshold]) <= zeroByteWindow) {
      unawaited(
        _maybeDeclare(
          state,
          deviceId: session.deviceId,
          source: session.source,
          trigger: triggerZeroByteStreak,
          depthSession: session,
        ),
      );
    }
  }

  /// Surfaces durable recordings that have made no upload progress for long
  /// enough to require user attention. Callers pass the oldest retryable local
  /// WAL timestamp after every inventory refresh; [pendingSeconds] is the
  /// kept-audio length across the backlog, when the caller knows it.
  void observeWalBacklog({required int pendingCount, required DateTime? oldestPendingAt, int pendingSeconds = 0}) {
    final state = _stateFor(localWalDeviceId);
    if (pendingCount <= 0 || oldestPendingAt == null) {
      _resolveIfActive(localWalDeviceId, state);
      return;
    }
    final now = _now();
    if (now.difference(oldestPendingAt) < uploadSilenceThreshold) {
      // The stalled recordings left the backlog (deleted, or out of retries) and what waits now is young.
      _endUploadStall();
      return;
    }
    final lastUploadAt = _lastUploadAt;
    if (lastUploadAt != null && now.difference(lastUploadAt) < uploadSilenceThreshold) return;
    _updateUploadStall(since: _uploadStall?.since ?? now, pendingCount: pendingCount, pendingSeconds: pendingSeconds);
    unawaited(
      _maybeDeclare(
        state,
        deviceId: localWalDeviceId,
        source: localWalSource,
        trigger: triggerUploadSilence,
        requireFeatureGate: false,
        extraProperties: {
          'pending_wal_count': pendingCount,
          'oldest_pending_age_seconds': now.difference(oldestPendingAt).inSeconds,
        },
      ),
    );
  }

  void _endUploadStall() {
    if (_uploadStall == null) return;
    _uploadStall = null;
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  /// Refreshes the upload-stall row's counts without re-declaring the episode:
  /// the telemetry slot may already be held by this very stall.
  void _updateUploadStall({required DateTime since, required int pendingCount, required int pendingSeconds}) {
    final previous = _uploadStall;
    if (previous != null && previous.pendingCount == pendingCount && previous.pendingSeconds == pendingSeconds) {
      return;
    }
    _uploadStall = CaptureUploadStall(since: since, pendingCount: pendingCount, pendingSeconds: pendingSeconds);
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  void observeStorageAtRisk({
    required DateTime engagedAt,
    required int blockedCount,
    required int retainedCount,
    required String reason,
  }) {
    final fingerprint = '${engagedAt.microsecondsSinceEpoch}:$blockedCount:$retainedCount:$reason';
    if (_lastRetentionRiskFingerprint == fingerprint) return;
    _lastRetentionRiskFingerprint = fingerprint;
    final state = _stateFor(localWalDeviceId);
    final properties = <String, Object>{
      'blocked_wal_count': blockedCount,
      'retained_wal_count': retainedCount,
      'retention_policy': 'admission_count_cap',
      'block_reason': reason,
    };
    // Count-cap pressure is diagnostic only; storage prompts are reserved for disk admission failures.
    if (reason == 'count_cap') {
      // A count-cap reading proves the disk admitted a write again, so any storage
      // row a disk failure engaged has ended the way its own condition ends — the
      // risk now reported is count pressure, which never owns the row. The
      // fingerprint stays so this diagnostic observation keeps its telemetry
      // dedupe; a disk failure that returns re-engages the row on its own
      // (different reason, different fingerprint).
      _endStorageAtRiskRow();
      final depth = _silenceAge(localWalDeviceId);
      _safeTrack('Capture Wedge Detected', {
        'source': localWalSource,
        'consecutive_zero_byte_sessions': state.zeroByteSessionEnds.length,
        'trigger': triggerStorageAtRisk,
        'app_build': _appBuild(),
        'platform': _platform(),
        ...properties,
        'seconds_since_last_ingress_byte': depth.ingress,
        'seconds_since_last_transcript': depth.transcript,
      });
      return;
    }
    unawaited(
      _maybeDeclare(
        state,
        deviceId: localWalDeviceId,
        source: localWalSource,
        trigger: triggerStorageAtRisk,
        requireFeatureGate: false,
        extraProperties: properties,
      ),
    );
    // The row follows the observation, not the episode: counts refresh even
    // while the episode slot is held and no new alert is declared.
    _storageAtRisk = CaptureStorageAtRisk(
      engagedAt: engagedAt,
      blockedCount: blockedCount,
      retainedCount: retainedCount,
      reason: reason,
    );
    _updateUnseenCaptureAttention();
    notifyListeners();
  }

  @visibleForTesting
  void runConnectedWatchdog() {
    final now = _now();
    for (final session in _openSessions.values) {
      if (session.watchdogDeclared) continue;
      if (session.expectsTranscript && session.bytesSinceTranscript > 0) {
        final progressAt = session.transcriptRequiredSince ?? session.lastTranscriptAt ?? session.connectedAt;
        if (now.difference(progressAt) < connectedNoTranscriptWindow) continue;
        session.watchdogDeclared = true;
        final state = _stateFor(session.deviceId);
        unawaited(
          _maybeDeclare(
            state,
            deviceId: session.deviceId,
            source: session.source,
            trigger: triggerBytesSentNoTranscript,
            requireFeatureGate: false,
            extraProperties: {
              'bytes_since_last_transcript': session.bytesSinceTranscript,
              'socket_still_connected': true,
            },
            depthSession: session,
          ),
        );
        continue;
      }
      if (!isCaptureSourceInScope(session.source)) continue;
      // CCCD recovery is already driving this radio. A second declaration
      // would occupy the banner slot and then no-op inside _attemptRecovery.
      if (_cccdRecoveryDevices.contains(session.deviceId)) continue;
      final ingressAt = session.lastIngressByteAt ?? session.connectedAt;
      if (now.difference(ingressAt) < connectedNoBytesWindow) continue;
      session.watchdogDeclared = true;
      final state = _stateFor(session.deviceId);
      unawaited(
        _maybeDeclare(
          state,
          deviceId: session.deviceId,
          source: session.source,
          trigger: triggerConnectedNoBytes,
          requireFeatureGate: false,
          extraProperties: {'ingress_bytes': session.ingressBytes},
          depthSession: session,
        ),
      );
    }
  }

  void onUploadCompleted() {
    _lastUploadAt = _now();
    final state = _devices[localWalDeviceId];
    if (state != null) _resolveIfActive(localWalDeviceId, state);
  }

  void onBleSessionEnded({
    required String deviceId,
    required DeviceType deviceType,
    required Duration duration,
    bool intentional = false,
  }) {
    final source = conversationSourceForDeviceType(deviceType);
    if (!isCaptureSourceInScope(source)) return;
    if (_retryInFlightDevices.contains(deviceId)) return;
    final state = _stateFor(deviceId);
    if (intentional) {
      state.rapidDropEnds.clear();
      if (state.episode != null || state.telemetryEpisode != null) {
        state.episode = null;
        state.telemetryEpisode = null;
        notifyListeners();
      }
      return;
    }
    if (duration >= rapidDropMaxDuration) return;
    final now = _now();
    final drops = state.rapidDropEnds;
    drops.add(now);
    drops.removeWhere((t) => now.difference(t) > rapidDropWindow);
    if (drops.length >= rapidDropThreshold) {
      unawaited(_maybeDeclare(state, deviceId: deviceId, source: source!, trigger: triggerRapidReconnects));
    }
  }

  /// The episode the reader is asked about. An acute link episode outranks a storage episode:
  /// it is the one the live page's header and Reconnect speak for, and its retry must not land
  /// on the storage transfer instead. Map order alone would pick whichever device came first.
  CaptureWedgeEpisode? get visiblePrompt {
    final acute = acuteEpisode;
    if (acute != null) return acute;
    for (final state in _devices.values) {
      final episode = state.episode;
      if (episode != null && episode.promptVisible) return episode;
    }
    return null;
  }

  bool get promptVisible => visiblePrompt != null;

  void markPromptShown() {
    final episode = visiblePrompt;
    if (episode == null || episode.promptShownEmitted) return;
    episode.promptShownEmitted = true;
    _safeTrack('Capture Recovery Prompt Shown', {'source': episode.source, 'trigger': episode.trigger});
  }

  void onRecoveryActioned({required String surface}) {
    _safeTrack('Capture Recovery Actioned', {'surface': surface});
  }

  void retryVisibleEpisode() {
    final episode = visiblePrompt;
    if (episode == null ||
        episode.trigger == triggerIngressRecoveryFailed ||
        _retryInFlightDevices.contains(episode.deviceId)) {
      return;
    }
    episode.promptVisible = false;
    notifyListeners();
    unawaited(_attemptRecovery(episode));
  }

  void dismissDeviceEpisode(String deviceId) {
    final state = _devices[deviceId];
    if (state == null) return;
    state.rapidDropEnds.clear();
    if (deviceId == localWalDeviceId) _clearCaptureAttention();
    if (state.episode == null && state.telemetryEpisode == null) return;
    state.episode = null;
    state.telemetryEpisode = null;
    notifyListeners();
  }

  /// Dismisses only the episode the reader dismissed — the visible prompt. A
  /// telemetry-only episode for the same device (an upload-silence observation,
  /// say) is a separate recovery operation: erasing it would silently cancel
  /// its eventual resolved event and let later observations redeclare it as a
  /// new incident. [dismissDeviceEpisode] remains the full reset for an
  /// intentional disconnect.
  void dismissVisibleEpisode(String deviceId) {
    final state = _devices[deviceId];
    if (state == null || state.episode == null) return;
    state.rapidDropEnds.clear();
    final episode = state.episode!;
    if (episode.trigger == triggerIngressRecoveryFailed) {
      // The native side republishes the same actionable snapshot every few
      // seconds, and observeIngressHealth would recreate a nulled episode on
      // the next tick — resurrecting a dismissed banner. Remember the
      // dismissed incident (its connection generation) until health actually
      // changes; a new generation or a healthy/quiet snapshot re-allows it.
      state.dismissedIngressGeneration = state.lastIngressHealth?.generation;
    }
    state.episode = null;
    notifyListeners();
  }

  void reset() {
    _devices.clear();
    _ingressEvents.clear();
    _nativeIngressDevices.clear();
    _openSessions.clear();
    _retryInFlightDevices.clear();
    _lastUploadAt = null;
    _lastRetentionRiskFingerprint = null;
    _storageAtRisk = null;
    _uploadStall = null;
    _captureAttentionSeenAt = null;
    hasUnseenCaptureAttention.value = false;
    _connectedWatchdog?.cancel();
    _connectedWatchdog = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _devices.clear();
    _ingressEvents.clear();
    _nativeIngressDevices.clear();
    _openSessions.clear();
    _retryInFlightDevices.clear();
    _connectedWatchdog?.cancel();
    hasUnseenCaptureAttention.dispose();
    super.dispose();
  }

  Future<void> _maybeDeclare(
    _DeviceWedgeState state, {
    required String deviceId,
    required String source,
    required String trigger,
    bool requireFeatureGate = true,
    Map<String, Object> extraProperties = const {},
    _OpenCaptureSession? depthSession,
  }) async {
    // Snapshot before the feature-gate await. A later byte must not rewrite the
    // age that was true at detection.
    final depth = _silenceAge(deviceId, session: depthSession);
    if (_nativeIngressDevices.contains(deviceId) &&
        (trigger == triggerZeroByteStreak || trigger == triggerRapidReconnects)) {
      return;
    }
    if (!_canDeclare(state, trigger)) return;
    var allowed = true;
    if (requireFeatureGate) {
      try {
        allowed = await _featureGate();
      } catch (_) {
        allowed = false;
      }
    }
    // Ownership can arrive while the gate was pending (TOCTOU): recheck after
    // the await, or a legacy episode lands invisibly, blocks later declarations
    // via _canDeclare, and its recovery exits at the owner guard.
    if (!allowed ||
        !_canDeclare(state, trigger) ||
        (_nativeIngressDevices.contains(deviceId) &&
            (trigger == triggerZeroByteStreak || trigger == triggerRapidReconnects))) {
      return;
    }
    final episode = CaptureWedgeEpisode(deviceId: deviceId, source: source, trigger: trigger, declaredAt: _now())
      ..telemetryOperationId = const Uuid().v4();
    if (_isTelemetryOnlyTrigger(trigger)) {
      state.telemetryEpisode = episode;
    } else {
      state.episode = episode;
    }
    _safeTrack('Capture Wedge Detected', {
      'source': source,
      'consecutive_zero_byte_sessions': state.zeroByteSessionEnds.length,
      'trigger': trigger,
      'app_build': _appBuild(),
      'platform': _platform(),
      ...extraProperties,
      'seconds_since_last_ingress_byte': depth.ingress,
      'seconds_since_last_transcript': depth.transcript,
    });
    final operationId = episode.telemetryOperationId;
    if (operationId != null) {
      try {
        ClientTelemetry.instance.observeWedge(
          operationId: operationId,
          phase: 'detected',
          trigger: trigger,
          outcome: 'pending',
        );
      } catch (_) {}
    }
    notifyListeners();
    unawaited(_attemptRecovery(episode));
  }

  bool _isTelemetryOnlyTrigger(String trigger) =>
      trigger == triggerBytesSentNoTranscript || trigger == triggerUploadSilence;

  bool _isBleIngressTrigger(String trigger) =>
      trigger == triggerConnectedNoBytes || trigger == triggerZeroByteStreak || trigger == triggerRapidReconnects;

  bool _canDeclare(_DeviceWedgeState state, String trigger) {
    return _isTelemetryOnlyTrigger(trigger) ? state.telemetryEpisode == null : state.episode == null;
  }

  bool _defersBleRetryToNativeIngress(CaptureWedgeEpisode episode) {
    if (!_nativeIngressDevices.contains(episode.deviceId)) return false;
    if (episode.trigger == triggerUploadSilence ||
        episode.trigger == triggerStorageAtRisk ||
        episode.trigger == triggerBytesSentNoTranscript) {
      return false;
    }
    // Native ingress health treats a subscribed link with no audio
    // notifications as quiet, not actionRequired, so it never starts its own
    // recovery for this stall. Defer only while a CCCD recovery is already
    // in progress; otherwise the existing BLE retry is the recovery.
    if (episode.trigger == triggerConnectedNoBytes) {
      return _cccdRecoveryDevices.contains(episode.deviceId);
    }
    return true;
  }

  Future<void> _attemptRecovery(CaptureWedgeEpisode episode) async {
    if (_defersBleRetryToNativeIngress(episode)) return;
    episode.retryAttempted = true;
    final telemetryOnly = _isTelemetryOnlyTrigger(episode.trigger);
    if (!telemetryOnly) _retryInFlightDevices.add(episode.deviceId);
    try {
      final transferRetry = _transferRetry;
      if ((episode.trigger == triggerUploadSilence ||
              episode.trigger == triggerStorageAtRisk ||
              episode.trigger == triggerBytesSentNoTranscript) &&
          transferRetry != null) {
        await transferRetry().timeout(retryTimeout);
      } else {
        await _bleRetry(episode.deviceId).timeout(retryTimeout);
      }
    } catch (e) {
      Logger.debug('CaptureWedgeMonitor: recovery retry for ${episode.deviceId} failed: $e');
    } finally {
      if (!telemetryOnly) _retryInFlightDevices.remove(episode.deviceId);
    }
    if (_episodeFor(episode.deviceId, telemetryOnly: telemetryOnly) != episode || telemetryOnly) return;
    episode.promptVisible = true;
    notifyListeners();
  }

  /// Gates the BLE retry's reconnect, so only actionable episodes count;
  /// telemetry-only episodes never own a BLE retry.
  bool hasActiveEpisode(String deviceId) => _devices[deviceId]?.episode != null;

  CaptureWedgeEpisode? _episodeFor(String deviceId, {required bool telemetryOnly}) {
    final state = _devices[deviceId];
    return telemetryOnly ? state?.telemetryEpisode : state?.episode;
  }

  void _resolveIfActive(String deviceId, _DeviceWedgeState state, {bool bleIngressOnly = false}) {
    if (bleIngressOnly && !_isBleIngressTrigger(state.episode?.trigger ?? '')) return;
    if (deviceId == localWalDeviceId) {
      // A resolving local-WAL observation proves upload progress, not recovered
      // disk: the storage row ends only with its own retention observation.
      _endUploadStall();
    }
    if (state.episode?.trigger == triggerIngressRecoveryFailed) {
      // The ingress failure stays (native owns it), but a transcript during
      // the alert must still release the telemetry slot: native-owned devices
      // can hold bytes_sent_no_transcript episodes, and an occupied slot
      // blocks later declarations and transfer retries.
      state.telemetryEpisode = null;
      notifyListeners();
      return;
    }
    if (state.episode == null && state.telemetryEpisode == null) return;
    for (final episode in [state.episode, if (!bleIngressOnly) state.telemetryEpisode]) {
      if (episode != null && _now().difference(episode.declaredAt) <= resolveWindow) {
        _safeTrack('Capture Recovery Resolved', {'source': episode.source, 'trigger': episode.trigger});
        final operationId = episode.telemetryOperationId;
        if (operationId != null) {
          try {
            ClientTelemetry.instance.observeWedge(
              operationId: operationId,
              phase: 'resolved',
              trigger: episode.trigger,
              outcome: 'recovered',
              latencyMs: _now().difference(episode.declaredAt).inMilliseconds,
            );
          } catch (_) {}
        }
      }
    }
    state.episode = null;
    if (bleIngressOnly) {
      state.zeroByteSessionEnds.clear();
      state.rapidDropEnds.clear();
      for (final session in _openSessions.values) {
        if (session.deviceId == deviceId && session.bytesSinceTranscript == 0) session.watchdogDeclared = false;
      }
    } else {
      state.telemetryEpisode = null;
    }
    notifyListeners();
  }

  void _safeTrack(String event, Map<String, Object> properties) {
    try {
      _track(event, {...properties, 'build': _appBuild()});
    } catch (e) {
      Logger.debug('CaptureWedgeMonitor: track failed for $event: $e');
    }
  }

  /// Ingress age is only the BLE ingress-byte observation. The watchdog still
  /// decides `connected_no_bytes` from `lastIngressByteAt ?? connectedAt`; that
  /// clock is not the telemetry property. Transcript age is only the transcript
  /// observation. Either value is -1 when its observation was never seen.
  ({int ingress, int transcript}) _silenceAge(String deviceId, {_OpenCaptureSession? session}) {
    final resolved = session ?? _longestOpenSession(deviceId);
    if (resolved == null) return (ingress: -1, transcript: -1);
    return (
      ingress: _secondsSince(resolved.lastBleIngressAt),
      transcript: _secondsSince(resolved.lastTranscriptAt),
    );
  }

  _OpenCaptureSession? _longestOpenSession(String deviceId) {
    _OpenCaptureSession? chosen;
    DateTime? chosenAt;
    for (final session in _openSessions.values) {
      if (session.deviceId != deviceId) continue;
      final at = session.lastIngressByteAt ?? session.connectedAt;
      if (chosen == null || chosenAt == null || at.isBefore(chosenAt)) {
        chosen = session;
        chosenAt = at;
      }
    }
    return chosen;
  }

  int _secondsSince(DateTime? at) {
    if (at == null) return -1;
    final seconds = _now().difference(at).inSeconds;
    return seconds < 0 ? 0 : seconds;
  }
}

class _DeviceWedgeState {
  CaptureIngressHealth? lastIngressHealth;
  String? dismissedIngressGeneration;
  final List<DateTime> zeroByteSessionEnds = [];
  final List<DateTime> noTranscriptSessionEnds = [];
  final List<DateTime> rapidDropEnds = [];
  CaptureWedgeEpisode? episode;
  CaptureWedgeEpisode? telemetryEpisode;
}

class _OpenCaptureSession {
  _OpenCaptureSession({required this.deviceId, required this.source, required this.connectedAt});

  final String deviceId;
  final String source;
  final DateTime connectedAt;
  bool transcriptObserved = false;
  bool expectsTranscript = true;
  DateTime? transcriptRequiredSince;
  DateTime? lastTranscriptAt;
  int bytesSinceTranscript = 0;
  int ingressBytes = 0;
  DateTime? lastIngressByteAt;
  DateTime? lastBleIngressAt;
  bool watchdogDeclared = false;
}
