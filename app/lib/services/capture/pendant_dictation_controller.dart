import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:opus_dart/opus_dart.dart' show SimpleOpusDecoder;
import 'package:omi/utils/audio/wav_bytes.dart' show WavBytesUtil;

import 'package:omi/services/devices/hid_dictation_protocol.dart';
import 'package:omi/utils/logger.dart';

import 'dart:io';

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

/// User-visible phases for the developer-settings status line.
enum PendantDictationPhase { idle, capturing, transcribing, sending, typing, done, error }

class PendantDictationUiState {
  final PendantDictationPhase phase;
  final String message;

  const PendantDictationUiState(this.phase, [this.message = '']);

  static const idle = PendantDictationUiState(PendantDictationPhase.idle, '');
}

/// Pendant-as-keyboard dictation prototype controller.
///
/// UX (one-click, tap toggle): tap the pendant button once to start an
/// utterance, tap again to finish. In HID mode the app consumes ALL pendant
/// button events (taps, double taps, long press, raw press/release) so no
/// assistant voice command can fire from a dictation click.
///
/// Lifecycle safety: every cancellation path (new capture, cancel, disable,
/// dispose, gate failure) bumps a generation. The capture→transcribe→send→
/// typed pipeline checks the generation after each await and drops the
/// utterance silently-by-report (plus a scoped on-device session cancel when
/// frames were already sent and the link is still the same one). Text is
/// only ever delivered over the connection the utterance was finished on —
/// the resolver never reconnects, and a link that drops mid-flow voids the
/// utterance instead of being resurrected.
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

  /// User-visible state for the developer toggle row.
  final ValueNotifier<PendantDictationUiState> state =
      ValueNotifier<PendantDictationUiState>(PendantDictationUiState.idle);

  int _generation = 0;
  bool _capturing = false;
  final List<List<int>> _payloads = [];
  Timer? _utteranceTimer;
  int _lastSession = 0;
  int? _inFlightSession; // session whose frames were sent, not yet terminal

  PendantDictationController({
    required this.resolveConnection,
    required this.getCodec,
    UtteranceTranscriber? transcriber,
    DictationHapticSender? hapticSender,
    DictationCaptureGate? captureGate,
    this.maxUtterance = const Duration(seconds: 20),
    this.typingTimeout = const Duration(seconds: 45),
    this.statusPollInterval = const Duration(milliseconds: 250),
  })  : transcribe = transcriber ?? strictUtteranceTranscriber,
        sendHaptic = hapticSender ?? _defaultHaptic,
        captureAllowed = captureGate ?? _defaultCaptureGate;

  bool get isCapturing => _capturing;

  int get _nextSession {
    _lastSession = (_lastSession % 255) + 1;
    return _lastSession;
  }

  bool _stale(int generation) => generation != _generation;

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
    _generation++; // supersede any in-flight finish from a previous utterance
    _invalidateOwnedSession(deviceId);
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
    _invalidateOwnedSession(deviceId);
    _payloads.clear();
  }

  /// Sends a scoped cancel for a sent-but-not-terminal session, then forgets
  /// it. Safe to call repeatedly; only acts while a link is still live.
  void _invalidateOwnedSession(String deviceId) {
    final session = _inFlightSession;
    _inFlightSession = null;
    if (session == null) {
      return;
    }
    unawaited(() async {
      try {
        final connection = await resolveConnection(deviceId);
        // A fresh cancel frame for exactly this session; the firmware
        // releases all keys and closes the session on its side.
        await connection?.performSendHidDictationFrame(HidDictationProtocol.buildCancelFrame(session));
      } catch (e) {
        Logger.debug('[hid-dictation] scoped cancel failed: $e');
      }
    }());
  }

  /// Drop everything: used by dispose and disable paths.
  Future<void> invalidate(String deviceId) async {
    _cancel(deviceId);
  }

  void dispose() {
    _generation++;
    _capturing = false;
    _utteranceTimer?.cancel();
    _utteranceTimer = null;
    _inFlightSession = null;
    _payloads.clear();
    state.dispose();
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
    if (_stale(generation)) return;
    if (connection == null) {
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'pendant not connected; utterance dropped'));
      return;
    }
    if (!await _stillConnected(connection, generation)) return;

    // Capability + activation gates before spending a transcription call.
    final features = await connection.getFeatures();
    if (_stale(generation)) return;
    if ((features & OmiFeatures.hidDictation) == 0) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'pendant firmware does not include the dictation prototype'));
      return;
    }
    final initialStatus = await connection.performGetHidDictationStatus();
    if (_stale(generation)) return;
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
    if (_stale(generation)) return;

    String transcript;
    try {
      transcript = await transcribe(payloads, codec);
    } catch (e) {
      if (_stale(generation)) return;
      debugPrint('[hid-dictation] transcription failed: $e');
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'transcription failed'));
      await sendHaptic(deviceId, 3);
      return;
    }
    if (_stale(generation)) return;
    if (!await _stillConnected(connection, generation)) return;

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

    await _sendText(connection, transcript, deviceId, generation);
  }

  /// True when the pipeline may continue on [connection]; reports and returns
  /// false when the generation went stale or the link dropped.
  Future<bool> _stillConnected(OmiDeviceConnection connection, int generation) async {
    if (_stale(generation)) return false;
    if (!await connection.isConnected()) {
      _report(const PendantDictationUiState(
          PendantDictationPhase.error, 'link dropped; utterance dropped (never re-delivered)'));
      _inFlightSession = null;
      return false;
    }
    if (_stale(generation)) return false;
    return true;
  }

  Future<void> _sendText(OmiDeviceConnection connection, String text, String deviceId, int generation) async {
    final session = _nextSession;
    final frames = HidDictationProtocol.buildFrames(session, text);
    if (frames.isEmpty) return;

    _report(const PendantDictationUiState(PendantDictationPhase.sending, 'typing…'));
    _inFlightSession = session;

    try {
      for (final frame in frames) {
        if (_stale(generation)) {
          _invalidateOwnedSession(deviceId);
          return;
        }
        if (!await _stillConnected(connection, generation)) {
          return;
        }
        final ok = await connection.performSendHidDictationFrame(frame);
        if (_stale(generation)) {
          _invalidateOwnedSession(deviceId);
          return;
        }
        if (!ok) {
          debugPrint('[hid-dictation] frame write failed; aborting send');
          await _cancelOnDevice(connection);
          _inFlightSession = null;
          _report(const PendantDictationUiState(PendantDictationPhase.error, 'write failed; session cancelled'));
          await sendHaptic(deviceId, 3);
          return;
        }
      }

      // Poll the status characteristic until the session reaches a terminal
      // state. Polling (not CCC) on purpose: no subscription setup race, and
      // a missed notification can never hang the wait.
      final deadline = DateTime.now().add(typingTimeout);
      while (true) {
        await Future.delayed(statusPollInterval);
        if (_stale(generation)) {
          _invalidateOwnedSession(deviceId);
          return;
        }
        final status = await connection.performGetHidDictationStatus();
        if (_stale(generation)) {
          _invalidateOwnedSession(deviceId);
          return;
        }
        if (status != null &&
            status.lastFinishedSession == session &&
            status.activeSession == HidDictationProtocol.sessionNone) {
          _inFlightSession = null;
          if (status.wasCancelled) {
            _report(const PendantDictationUiState(PendantDictationPhase.error, 'cancelled on device'));
          } else if (status.isError) {
            _report(PendantDictationUiState(PendantDictationPhase.error, 'pendant: ${status.describe()}'));
            await sendHaptic(deviceId, 3);
          } else {
            _report(PendantDictationUiState(PendantDictationPhase.done, 'typed ${status.charsTyped} chars'));
            await sendHaptic(deviceId, 2);
          }
          return;
        }
        if (DateTime.now().isAfter(deadline)) {
          await _cancelOnDevice(connection);
          _inFlightSession = null;
          _report(const PendantDictationUiState(PendantDictationPhase.error, 'typing timed out; cancelled'));
          await sendHaptic(deviceId, 3);
          return;
        }
      }
    } catch (e) {
      debugPrint('[hid-dictation] send failed: $e — cancelling on device');
      await _cancelOnDevice(connection);
      _inFlightSession = null;
      _report(const PendantDictationUiState(PendantDictationPhase.error, 'send failed; session cancelled'));
      await sendHaptic(deviceId, 3);
    }
  }

  Future<void> _cancelOnDevice(OmiDeviceConnection connection) async {
    try {
      await connection.performSendHidDictationFrame(HidDictationProtocol.buildCancelFrame());
    } catch (e) {
      Logger.debug('[hid-dictation] cancel write failed: $e');
    }
  }

  void _report(PendantDictationUiState s) {
    state.value = s;
    debugPrint('[hid-dictation] ${s.phase.name}: ${s.message}');
  }
  // --- Opt-in control ---

  /// Whether the connected pendant advertises the dictation feature bit.
  Future<bool> isDeviceSupported(String deviceId) async {
    final connection = await resolveConnection(deviceId);
    if (connection == null) return false;
    final features = await connection.getFeatures();
    return (features & OmiFeatures.hidDictation) != 0;
  }

  /// Opt the pendant into the HID prototype. Cancels any in-flight dictation
  /// first; takes effect on the next reconnect, which [reconnect] performs.
  Future<HidDictationStatus?> enableHid(String deviceId, {required Future<void> Function() reconnect}) async {
    return _writeCommand(deviceId, HidDictationProtocol.cmdEnable, reconnect: reconnect);
  }

  Future<HidDictationStatus?> disableHid(String deviceId, {required Future<void> Function() reconnect}) async {
    await _cancel(deviceId);
    return _writeCommand(deviceId, HidDictationProtocol.cmdDisable, reconnect: reconnect);
  }

  Future<HidDictationStatus?> _writeCommand(String deviceId, int cmd,
      {required Future<void> Function() reconnect}) async {
    final connection = await resolveConnection(deviceId);
    if (connection == null) return null;
    final ok = await connection.performSendHidDictationCommand(cmd);
    if (!ok) return null;
    final status = await connection.performGetHidDictationStatus();
    if (status?.hidPending == true) {
      debugPrint('[hid-dictation] command queued; reconnecting to apply');
      await reconnect();
    }
    return status;
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
