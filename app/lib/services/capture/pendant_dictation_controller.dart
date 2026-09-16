import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/hid_dictation_protocol.dart';
import 'package:omi/utils/logger.dart';

import 'dart:io';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:opus_dart/opus_dart.dart' show SimpleOpusDecoder;
import 'package:omi/utils/audio/wav_bytes.dart' show WavBytesUtil;

/// Strict transcriber for one utterance: [payloads] are the packet payloads
/// stripped from the BLE audio stream. Throws on any decode failure or empty
/// audio (never transcribes partial/silent audio). Injectable for tests.
typedef UtteranceTranscriber = Future<String> Function(List<List<int>> payloads, BleAudioCodec codec);

/// Resolves the connection for a device WITHOUT ever triggering a reconnect.
/// Returns null unless an OmiDeviceConnection is already live — stale text
/// must never be the reason a link comes back up.
typedef DictationConnectionResolver = Future<OmiDeviceConnection?> Function(String deviceId);

/// Resolves the audio codec negotiated with the pendant.
typedef DictationCodecGetter = Future<BleAudioCodec> Function(String deviceId);

/// Sends pendant haptic feedback. Injectable for tests.
typedef DictationHapticSender = Future<void> Function(String deviceId, int level);

/// Gate evaluated before a capture opens (e.g. batch/native-background modes
/// where the Dart audio stream does not flow). Injectable for tests.
typedef DictationCaptureGate = bool Function();

/// Drops the BLE link so the transport/native stack can reconnect fresh.
/// Used ONLY by the explicit opt-in/out activation flow, never to deliver
/// dictation text. Injectable for tests.
typedef DictationReconnector = Future<void> Function();

/// User-visible phases for the developer-settings status line.
enum PendantDictationPhase { idle, capturing, transcribing, sending, typing, done, error, activating }

class PendantDictationUiState {
  final PendantDictationPhase phase;
  final String message;

  const PendantDictationUiState(this.phase, [this.message = '']);

  static const idle = PendantDictationUiState(PendantDictationPhase.idle, '');
}

/// One in-flight dictation pipeline. Immutable snapshot of everything the
/// pipeline owns: a stale pipeline may cancel or clear ONLY its own session,
/// over its own connection — never a newer operation's globals.
class _DictationOp {
  final int generation;
  final int session;
  final OmiDeviceConnection connection;
  final int epoch;
  final int expectedChars;

  const _DictationOp({
    required this.generation,
    required this.session,
    required this.connection,
    required this.epoch,
    required this.expectedChars,
  });
}

/// Pendant-as-keyboard dictation prototype controller.
///
/// UX (one-click, tap toggle): tap the pendant button once to start an
/// utterance, tap again to finish. In HID mode the app consumes ALL pendant
/// button events (taps, double taps, long press, raw press/release) so no
/// assistant voice command can fire from a dictation click.
///
/// Lifecycle safety:
/// - Every cancellation path (new capture, cancel, disable, dispose, gate
///   failure) bumps a generation; the capture→transcribe→send→typed pipeline
///   checks the generation AND the BLE-link epoch after each await.
/// - The link epoch is pinned from the transport's connection-state stream at
///   utterance finish: if the SAME connection object dropped and reconnected
///   while the pipeline waited (native auto-reconnect), the epoch changed and
///   the utterance is voided — even though isConnected() is true again.
/// - Stale pipelines cancel only their own session id over their own captured
///   connection (never session 0, never a freshly resolved link); the firmware
///   additionally rejects wrong-owner cancels without touching the live one.
/// - Text is only ever delivered over the pinned link: the resolver is
///   strictly passive and never reconnects.
class PendantDictationController {
  final DictationConnectionResolver resolveConnection;
  final UtteranceTranscriber transcribe;
  final DictationCodecGetter getCodec;
  final DictationHapticSender sendHaptic;
  final DictationCaptureGate captureAllowed;

  /// Wall-clock cap for one utterance, mirroring the voice-command timeout.
  final Duration maxUtterance;

  /// Wall-clock cap for the pendant to finish typing once frames are sent.
  final Duration typingTimeout;

  /// Status poll cadence while waiting for the pendant to finish typing.
  final Duration statusPollInterval;

  /// Bounded wait for the transport to come back after an opt-in/out
  /// activation reconnect before verifying the resulting state.
  final Duration activationReconnectTimeout;

  /// User-visible state for the developer toggle row.
  final ValueNotifier<PendantDictationUiState> state =
      ValueNotifier<PendantDictationUiState>(PendantDictationUiState.idle);

  int _generation = 0;
  bool _capturing = false;
  final List<List<int>> _payloads = [];
  Timer? _utteranceTimer;
  int _lastSession = 0;
  _DictationOp? _activeOp; // owned by the newest pipeline only

  // Link epoch: bumped on every transport disconnect event. Pinned per
  // utterance; a change means the BLE link the utterance started on is gone
  // (even if the same connection object auto-reconnected since).
  int _linkEpoch = 0;
  StreamSubscription<DeviceTransportState>? _epochSub;

  PendantDictationController({
    required this.resolveConnection,
    required this.getCodec,
    UtteranceTranscriber? transcriber,
    DictationHapticSender? hapticSender,
    DictationCaptureGate? captureGate,
    this.maxUtterance = const Duration(seconds: 20),
    this.typingTimeout = const Duration(seconds: 45),
    this.statusPollInterval = const Duration(milliseconds: 250),
    this.activationReconnectTimeout = const Duration(seconds: 12),
  })  : transcribe = transcriber ?? strictUtteranceTranscriber,
        sendHaptic = hapticSender ?? _defaultHaptic,
        captureAllowed = captureGate ?? _defaultCaptureGate;

  bool get isCapturing => _capturing;

  int get _nextSession {
    _lastSession = (_lastSession % 255) + 1;
    return _lastSession;
  }

  bool _stale(_DictationOp op) => op.generation != _generation;
  bool _epochChanged(_DictationOp op) => op.epoch != _linkEpoch;

  /// The pipeline may continue only while it still owns the turn AND the
  /// pinned link is still the live link.
  bool _opValid(_DictationOp op) => !_stale(op) && !_epochChanged(op);

  // --- Link epoch tracking ---

  void _watchTransport(OmiDeviceConnection connection) {
    _epochSub?.cancel();
    _linkEpoch++;
    _epochSub = connection.transport.connectionStateStream.listen((event) {
      if (event == DeviceTransportState.disconnected) {
        _linkEpoch++;
      }
    }, onError: (Object e) {
      Logger.debug('[hid-dictation] transport state stream error: $e');
    });
  }

  // --- Button entry point (consumes every event in HID mode) ---

  /// Handles a pendant button notification while the HID dictation toggle is
  /// on. Returns true when the event was consumed (the caller must not run
  /// any other button action for it).
  Future<bool> onButtonEvent(String deviceId, int buttonState) async {
    // Single tap toggles the utterance: first tap starts, second finishes.
    if (buttonState == 1) {
      if (_capturing) {
        await _finishUtterance(deviceId);
      } else {
        _startCapture(deviceId);
      }
      return true;
    }
    // Everything else (double tap 2, long press 3, raw press 4, release 5)
    // is deliberately consumed and ignored: dictation owns the button, and
    // no assistant voice command may fire from an HID-mode click.
    return true;
  }

  // --- Capture lifecycle ---

  void _startCapture(String deviceId) {
    if (!captureAllowed()) {
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'dictation unavailable in this capture mode'));
      return;
    }
    _cancelOwnedOp(); // supersede any in-flight pipeline from a previous utterance
    _generation++;
    _capturing = true;
    _payloads.clear();
    _utteranceTimer?.cancel();
    _utteranceTimer = Timer(maxUtterance, () {
      debugPrint('[hid-dictation] utterance timed out, dropping capture');
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'utterance timed out'));
      _cancel(deviceId);
    });
    _report(const PendantDictationUiState(PendantDictationPhase.capturing, 'listening…'));
    unawaited(sendHaptic(deviceId, 1));
  }

  /// Feed one stripped opus payload while capturing (no-op otherwise).
  void onAudioPayload(List<int> payload) {
    if (_capturing && payload.isNotEmpty) {
      _payloads.add(payload);
    }
  }

  /// Cancel any open capture or in-flight pipeline. User-visible cancel.
  Future<void> cancelCapture(String deviceId) async {
    await _cancel(deviceId);
    _report(const PendantDictationUiState(PendantDictationPhase.error, 'cancelled'));
  }

  Future<void> _cancel(String deviceId) async {
    _generation++;
    _capturing = false;
    _utteranceTimer?.cancel();
    _utteranceTimer = null;
    _cancelOwnedOp();
    _payloads.clear();
  }

  /// Drop everything: capture stop / device disconnect / dispose path.
  Future<void> invalidate(String deviceId) => _cancel(deviceId);

  void dispose() {
    _generation++;
    _capturing = false;
    _utteranceTimer?.cancel();
    _utteranceTimer = null;
    _epochSub?.cancel();
    _epochSub = null;
    _activeOp = null;
    _payloads.clear();
    state.dispose();
  }

  /// Cancels the op owned by the CURRENT generation, if any. A stale pipeline
  /// never calls this — it cancels only its own op via [_cancelOp].
  void _cancelOwnedOp() {
    final op = _activeOp;
    _activeOp = null;
    if (op != null) {
      unawaited(_cancelOp(op));
    }
  }

  /// Scoped cancellation of exactly [op]: its own session id, over its own
  /// captured connection, only while that link is still live. Never resolves
  /// a fresh connection (no reconnect), never session 0.
  Future<void> _cancelOp(_DictationOp op) async {
    try {
      if (await op.connection.isConnected()) {
        await op.connection.performSendHidDictationFrame(HidDictationProtocol.buildCancelFrame(op.session));
      }
    } catch (e) {
      Logger.debug('[hid-dictation] scoped cancel for session ${op.session} failed: $e');
    }
  }

  // --- Utterance pipeline ---

  Future<void> _finishUtterance(String deviceId) async {
    if (!_capturing) return;
    final generation = _generation;
    final payloads = List<List<int>>.from(_payloads);
    _capturing = false;
    _utteranceTimer?.cancel();
    _utteranceTimer = null;
    _payloads.clear();

    if (payloads.isEmpty) {
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'no audio captured'));
      return;
    }

    // Deliver only over the link that exists right now; never reconnect.
    final connection = await resolveConnection(deviceId);
    if (generation != _generation) return;
    if (connection == null) {
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'pendant not connected; utterance dropped'));
      return;
    }
    _watchTransport(connection);
    final op = _DictationOp(
      generation: generation,
      session: 0, // assigned when frames are sent
      connection: connection,
      epoch: _linkEpoch,
      expectedChars: 0,
    );

    // Capability + activation gates before spending a transcription call.
    final features = await connection.getFeatures();
    if (generation != _generation) return;
    if ((features & OmiFeatures.hidDictation) == 0) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'pendant firmware does not include the dictation prototype'));
      return;
    }
    final initialStatus = await connection.performGetHidDictationStatus();
    if (generation != _generation) return;
    if (initialStatus == null) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'cannot read dictation status (protocol mismatch?)'));
      return;
    }
    if (!initialStatus.hidActive) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'HID prototype not active on the pendant (enable + reconnect)'));
      return;
    }

    _report(const PendantDictationUiState(PendantDictationPhase.transcribing, 'transcribing…'));
    final codec = await getCodec(deviceId);
    if (generation != _generation) return;

    String transcript;
    try {
      transcript = await transcribe(payloads, codec);
    } catch (e) {
      if (generation != _generation) return;
      debugPrint('[hid-dictation] transcription failed: $e');
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'transcription failed'));
      await sendHaptic(deviceId, 3);
      return;
    }
    if (!_opValid(op)) return; // stale, or the link dropped and came back

    transcript = transcript.trim();
    if (transcript.isEmpty) {
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'empty transcript'));
      return;
    }
    if (transcript.length > HidDictationProtocol.maxTextLength) {
      _report(PendantDictationUiState(PendantDictationPhase.error,
          'transcript ${transcript.length} chars exceeds ${HidDictationProtocol.maxTextLength}; refusing to truncate'));
      return;
    }
    final badIndex = HidDictationProtocol.firstUnsupportedIndex(transcript);
    if (badIndex != null) {
      // Explicit rejection: no transliteration, no partial typing.
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'unsupported character in transcript; nothing typed'));
      await sendHaptic(deviceId, 3);
      return;
    }

    final session = _nextSession;
    final sendOp = _DictationOp(
      generation: generation,
      session: session,
      connection: connection,
      epoch: op.epoch,
      expectedChars: transcript.length,
    );
    _activeOp = sendOp;
    await _sendText(sendOp, transcript, deviceId);
  }

  Future<void> _sendText(_DictationOp op, String text, String deviceId) async {
    final frames = HidDictationProtocol.buildFrames(op.session, text);
    if (frames.isEmpty) return;

    _report(const PendantDictationUiState(PendantDictationPhase.sending, 'typing…'));

    Future<void> bail(String message, {bool scopedCancel = true}) async {
      if (scopedCancel) {
        await _cancelOp(op); // exactly this session, over exactly this link
      }
      if (_activeOp == op) _activeOp = null;
      if (!_stale(op)) {
        _report(PendantDictationUiState(PendantDictationPhase.error, message));
        await sendHaptic(deviceId, 3);
      }
    }

    try {
      for (final frame in frames) {
        if (!_opValid(op)) {
          await _cancelOp(op);
          if (_activeOp == op) _activeOp = null;
          return;
        }
        if (!await op.connection.isConnected()) {
          if (_activeOp == op) _activeOp = null;
          if (!_stale(op)) {
            _report(const PendantDictationUiState(
                PendantDictationPhase.error, 'link dropped; utterance dropped (never re-delivered)'));
          }
          return;
        }
        final ok = await op.connection.performSendHidDictationFrame(frame);
        if (!_opValid(op)) {
          await _cancelOp(op);
          if (_activeOp == op) _activeOp = null;
          return;
        }
        if (!ok) {
          await bail('write failed; session cancelled');
          return;
        }
      }

      // Poll the status characteristic until the session reaches a terminal
      // state. Polling (not CCC) on purpose: no subscription setup race, and
      // a missed notification can never hang the wait.
      final deadline = DateTime.now().add(typingTimeout);
      while (true) {
        await Future.delayed(statusPollInterval);
        if (!_opValid(op)) {
          await _cancelOp(op);
          if (_activeOp == op) _activeOp = null;
          return;
        }
        final status = await op.connection.performGetHidDictationStatus();
        if (!_opValid(op)) {
          await _cancelOp(op);
          if (_activeOp == op) _activeOp = null;
          return;
        }
        if (status != null &&
            status.lastFinishedSession == op.session &&
            status.activeSession == HidDictationProtocol.sessionNone) {
          if (_activeOp == op) _activeOp = null;
          // Strict success: DONE state, no error, and every char accounted
          // for. Anything less is reported as a failure.
          final success = !status.isError &&
              !status.wasCancelled &&
              status.state == HidDictationProtocol.stateDone &&
              status.lastError == HidDictationProtocol.errNone &&
              status.charsTyped == op.expectedChars;
          if (success) {
            _report(PendantDictationUiState(PendantDictationPhase.done, 'typed ${status.charsTyped} chars'));
            await sendHaptic(deviceId, 2);
          } else if (status.wasCancelled) {
            _report(const PendantDictationUiState(PendantDictationPhase.error, 'cancelled on device'));
          } else {
            _report(PendantDictationUiState(PendantDictationPhase.error,
                'incomplete typing (${status.charsTyped}/${op.expectedChars}: ${status.describe()})'));
            await sendHaptic(deviceId, 3);
          }
          return;
        }
        if (DateTime.now().isAfter(deadline)) {
          await bail('typing timed out; cancelled');
          return;
        }
      }
    } catch (e) {
      debugPrint('[hid-dictation] send failed: $e — cancelling session ${op.session}');
      await bail('send failed; session cancelled');
    }
  }

  void _report(PendantDictationUiState s) {
    state.value = s;
    debugPrint('[hid-dictation] ${s.phase.name}: ${s.message}');
  }

  // --- Opt-in activation (the real enable/disable path) ---

  /// Whether the connected pendant advertises the dictation feature bit.
  Future<bool> isDeviceSupported(String deviceId) async {
    final connection = await resolveConnection(deviceId);
    if (connection == null) return false;
    final features = await connection.getFeatures();
    return (features & OmiFeatures.hidDictation) != 0;
  }

  /// Opt the pendant into the HID prototype: cancel in-flight dictation,
  /// write ENABLE, [reconnect] (the only code path allowed to cycle the
  /// link), then wait for the transport to return and VERIFY the resulting
  /// state. Reports progress and the outcome through [state].
  Future<bool> enableHid(String deviceId, {required DictationReconnector reconnect}) async {
    return _activate(
      deviceId,
      cmd: HidDictationProtocol.cmdEnable,
      reconnect: reconnect,
      wantActive: true,
      pending: 'enable queued; reconnecting…',
      ok: 'HID active on the pendant',
      failed: 'HID did not activate (accept the iOS pairing prompt and retry)',
    );
  }

  Future<bool> disableHid(String deviceId, {required DictationReconnector reconnect}) async {
    return _activate(
      deviceId,
      cmd: HidDictationProtocol.cmdDisable,
      reconnect: reconnect,
      wantActive: false,
      pending: 'disable queued; reconnecting…',
      ok: 'HID removed (stock behavior)',
      failed: 'HID did not deactivate; power-cycle the pendant to recover',
    );
  }

  Future<bool> _activate(
    String deviceId, {
    required int cmd,
    required DictationReconnector reconnect,
    required bool wantActive,
    required String pending,
    required String ok,
    required String failed,
  }) async {
    await _cancel(deviceId);

    final connection = await resolveConnection(deviceId);
    if (connection == null) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'pendant not connected — toggle it on with the pendant connected'));
      return false;
    }

    final wrote = await connection.performSendHidDictationCommand(cmd);
    if (!wrote) {
      _report(
          const PendantDictationUiState(PendantDictationPhase.error, 'activation write failed (pairing declined?)'));
      return false;
    }

    _report(PendantDictationUiState(PendantDictationPhase.activating, pending));
    await reconnect();

    // Bounded wait for the transport to come back, then verify the result.
    final deadline = DateTime.now().add(activationReconnectTimeout);
    OmiDeviceConnection? fresh;
    while (DateTime.now().isBefore(deadline)) {
      await Future.delayed(const Duration(milliseconds: 500));
      fresh = await resolveConnection(deviceId);
      if (fresh != null) break;
    }
    final status = fresh == null ? null : await fresh.performGetHidDictationStatus();
    final active = status?.hidActive == wantActive && status?.hidPending != true;
    if (active) {
      _report(PendantDictationUiState(PendantDictationPhase.idle, ok));
      return true;
    }
    _report(PendantDictationUiState(PendantDictationPhase.error, failed));
    return false;
  }

  static bool _defaultCaptureGate() {
    // Batch (Transcribe Later) mode hands audio to the native layer; the
    // Dart opus stream does not flow, so a dictation capture would collect
    // nothing and silently produce garbage.
    return true;
  }

  static Future<void> _defaultHaptic(String deviceId, int level) async {
    try {
      final connection = ServiceManager.instance().device.connectionFor(deviceId);
      if (connection is OmiDeviceConnection) {
        await connection.performPlayToSpeakerHaptic(level);
      }
    } catch (e) {
      Logger.debug('[hid-dictation] haptic failed: $e');
    }
  }
}

/// Production transcriber: strict per-packet opus decode → WAV → one-shot
/// /v2/voice-message/transcribe → plain transcript.
///
/// - validates the codec is an opus wire format (rejects pcm/lc3/unknown);
/// - decodes each stripped packet on its own (packet boundaries preserved —
///   no flatten-and-rechunk);
/// - any decode failure or empty PCM rejects the whole utterance;
/// - the native decoder is destroyed on every exit path.
Future<String> strictUtteranceTranscriber(List<List<int>> payloads, BleAudioCodec codec) async {
  if (!codec.isOpusSupported()) {
    throw UnsupportedError('dictation requires an opus wire format, got ${codec.name}');
  }
  final decoder = SimpleOpusDecoder(sampleRate: 16000, channels: 1);
  try {
    final allPcm = <int>[];
    for (final payload in payloads) {
      // Throws on a malformed frame — rejecting the utterance instead of
      // silently skipping audio and transcribing a hole.
      final pcm = decoder.decode(input: Uint8List.fromList(payload));
      allPcm.addAll(pcm);
    }
    if (allPcm.isEmpty) {
      throw StateError('utterance decoded to empty audio');
    }
    final wav = WavBytesUtil.getUInt8ListBytes(allPcm, 16000);
    if (wav.isEmpty) {
      throw StateError('utterance produced empty WAV');
    }
    final file = File('${Directory.systemTemp.path}/hid_dictation_${DateTime.now().millisecondsSinceEpoch}.wav');
    await file.writeAsBytes(wav, flush: true);
    try {
      return await transcribeVoiceMessage([file]);
    } finally {
      try {
        await file.delete();
      } catch (_) {}
    }
  } finally {
    decoder.destroy();
  }
}
