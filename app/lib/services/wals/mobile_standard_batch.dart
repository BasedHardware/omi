import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';

/// Routing owner for pendant Standard capture. No server capability, model,
/// disk admission, or demand evidence means the existing streaming path.
class MobileStandardBatch {
  MobileStandardBatch({
    required this.buffer,
    required this.loadVad,
    required this.freeDiskBytes,
    required this.visibility,
    required this.ownerUid,
    required this.now,
  });

  final MobileBatchBuffer buffer;
  final Future<MobileBatchVad> Function() loadVad;
  final Future<int?> Function() freeDiskBytes;
  final ValueListenable<ListenClientStateSnapshot> visibility;
  final String Function() ownerUid;
  final DateTime Function() now;
  MobileBatchVad? _vad;
  bool _serverAllowed = false;
  String? _authorizedUid;
  bool _ready = false;
  bool _closed = false;
  int _queued = 0;
  bool _initializing = false;
  Future<void>? _closing;
  DateTime? _lastSpeech;
  DateTime? _lastSpaceCheck;
  DateTime? _authorizedAt;
  Future<void> _inference = Future.value();
  Future<void> _initialization = Future.value();
  Future<void> get pendingInitialization => _initialization;
  Future<void> get pendingInference => _inference;
  final Stopwatch inferenceTime = Stopwatch();
  int vadAudioSamples = 0;

  bool _localPreview = false;
  bool _bufferReady = false;

  /// The current authorization is a local-preview grant: the phone renders an
  /// on-device preview, so every pendant frame is journaled whether or not the
  /// transcript is on screen. Same expiry as the authorization it rides on.
  bool get localPreview => _localPreview;

  /// Authorized, but the journal is still loading its model/disk check. Frames
  /// arriving now are refused (today's WAL path) only until it is ready.
  bool get warmingUp => !_closed && _serverAllowed && !_ready && _initializing;

  /// Account change: frames the local-preview router kept off the socket and
  /// the safety WAL had not yet made durable are written to this journal for
  /// the current (old) owner, regardless of authorization, before the account
  /// cleanup clears the WAL's memory. Synchronous; the sealed file is
  /// recovered and uploaded through sync when that owner is back. Returns
  /// whether every frame was written.
  bool preserveForOwner(
    List<(List<int>, DateTime)> frames, {
    required BleAudioCodec codec,
    String? recordingSessionId,
  }) {
    // Only the journal files are needed, not the VAD: works during warm-up.
    if (_closed || !_bufferReady || buffer.failed || frames.isEmpty) return false;
    buffer.seal();
    var all = true;
    for (final (payload, capturedAt) in frames) {
      all = buffer.append(payload,
              uid: ownerUid(), codec: codec, now: capturedAt, recordingSessionId: recordingSessionId) &&
          all;
    }
    buffer.seal();
    return all;
  }

  /// The client stopped honouring a local-preview grant (a per-session gate
  /// flipped). Ordinary Standard batch rules, including visibility, apply
  /// again; the authorization and its expiry are unchanged.
  void dropLocalPreview() => _localPreview = false;

  /// Authorization is connection-scoped and expires. Reconnect obtains a
  /// fresh integration inventory and cohort decision from the server.
  void authorize(bool allowed, {bool localPreview = false}) {
    _serverAllowed = allowed;
    _localPreview = allowed && localPreview;
    _authorizedUid = ownerUid();
    _authorizedAt = now();
    if (!allowed) buffer.seal();
    if (allowed && !_ready && !_initializing && !_closed) _initialization = _initialize();
  }

  Future<void> _initialize() async {
    _initializing = true;
    try {
      await buffer.initialize();
      _bufferReady = true;
      final bytes = await freeDiskBytes();
      if (bytes == null || bytes < 512 * 1024 * 1024 || _closed) return;
      await _inference;
      await _vad?.close();
      _vad = null;
      final model = await loadVad();
      if (_closed) {
        await model.close();
        return;
      }
      _vad = model;
      _ready = true;
      _lastSpaceCheck = now();
    } catch (_) {
      // Initialization failure retains today's live/WAL path.
      _ready = false;
    } finally {
      _initializing = false;
    }
  }

  bool get eligible =>
      !_closed &&
      _ready &&
      _serverAllowed &&
      !buffer.failed &&
      ownerUid().isNotEmpty &&
      ownerUid() == _authorizedUid &&
      _authorizedAt != null &&
      now().difference(_authorizedAt!) < const Duration(minutes: 2) &&
      // Ordinary Standard batch hands visible audio back to live STT. A
      // local-preview session never does: the preview is on-device.
      (_localPreview || !visibility.value.transcriptVisible);

  /// Called at the actual packet routing boundary, before ordinary safety WAL
  /// and WS delivery. A true return suppresses BOTH for exactly this packet.
  bool route(
    List<int> payload, {
    required BleAudioCodec codec,
    required bool realtimeConsumer,
    Geolocation? geolocation,
    String? recordingSessionId,
  }) {
    if (!eligible || realtimeConsumer || !codec.isOpusSupported()) {
      buffer.seal();
      return false;
    }
    final clock = now();
    if (_lastSpaceCheck == null || clock.difference(_lastSpaceCheck!) >= const Duration(seconds: 10)) {
      _lastSpaceCheck = clock;
      unawaited(_checkSpace());
    }
    final accepted = buffer.append(payload,
        uid: ownerUid(), codec: codec, now: clock, geolocation: geolocation, recordingSessionId: recordingSessionId);
    if (!accepted) {
      buffer.seal();
      return false;
    }
    // Bound the inference queue. Overload is treated as speech/unknown; its
    // original frames are already safe, and max chunk latency stays 60s.
    if (_queued < 32) {
      _queued++;
      final vad = _vad!;
      final samples = codec.getFrameSize();
      _inference = _inference.then((_) async {
        inferenceTime.start();
        try {
          final probability = await vad.probability(payload);
          vadAudioSamples += samples;
          if (probability >= 0.35) _lastSpeech = clock;
          if (_lastSpeech != null && clock.difference(_lastSpeech!) >= const Duration(seconds: 2)) {
            buffer.seal();
            _lastSpeech = null;
          }
        } catch (_) {
          _ready = false;
          buffer.seal();
        } finally {
          inferenceTime.stop();
          _queued--;
        }
      });
    } else {
      // A VAD unable to keep pace returns subsequent packets to live capture.
      _ready = false;
      buffer.seal();
    }
    return true;
  }

  Future<void> _checkSpace() async {
    try {
      final bytes = await freeDiskBytes();
      if (bytes == null || bytes < 512 * 1024 * 1024) {
        _ready = false;
        buffer.seal();
      }
    } catch (_) {
      _ready = false;
      buffer.seal();
    }
  }

  void visibilityChanged() {
    if (visibility.value.transcriptVisible && !_localPreview) buffer.seal();
  }

  Future<void> close() => _closing ??= _close();

  Future<void> _close() async {
    _closed = true;
    _serverAllowed = false;
    await _inference;
    await buffer.close();
    await _vad?.close();
    _vad = null;
  }
}
