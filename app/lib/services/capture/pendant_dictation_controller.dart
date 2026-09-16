import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/hid_dictation_protocol.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/utils/logger.dart';

import 'dart:io';
import 'dart:typed_data';

/// Transcribes the opus payloads collected during one utterance.
/// Injectable seam for tests (production: [defaultUtteranceTranscriber]).
typedef UtteranceTranscriber = Future<String?> Function(List<List<int>> opusPayloads, BleAudioCodec codec);

/// Resolves a live connection for a device, or null. Injectable for tests.
typedef DictationConnectionResolver = Future<OmiDeviceConnection?> Function(String deviceId);

/// Sends pendant haptic feedback (level semantics shared with the capture
/// controller's speaker haptics). Injectable for tests.
typedef DictationHapticSender = Future<void> Function(String deviceId, int level);

/// Pendant-as-keyboard dictation prototype controller.
///
/// Flow: pendant button press (BLE button value 4) starts collecting the opus
/// payloads already streaming over the audio characteristic; release (value 5)
/// stops collection, transcribes the utterance with the existing one-shot
/// voice-message transcription path, validates the transcript is printable US
/// ASCII (rejecting it explicitly otherwise), and ships it to the pendant as
/// bounded GATT frames. The pendant types it into the host's focused field via
/// BLE HID. No Enter is ever sent; the user reviews and sends manually.
///
/// This controller is deliberately dumb about audio plumbing — the capture
/// controller forwards it payloads — so it stays unit-testable without a
/// device.
class PendantDictationController {
  final DictationConnectionResolver resolveConnection;
  final UtteranceTranscriber transcribe;
  final DictationHapticSender sendHaptic;

  /// Wall-clock cap for one utterance, mirroring the voice-command timeout.
  final Duration maxUtterance = const Duration(seconds: 20);

  /// Wall-clock cap for the pendant to finish typing once frames are sent.
  final Duration typingTimeout = const Duration(seconds: 45);

  Timer? _utteranceTimer;
  DateTime? _captureStart;
  BleAudioCodec? _codec;
  final List<List<int>> _payloads = [];
  int _lastSession = 0;
  StreamSubscription<HidDictationStatus>? _statusSub;

  PendantDictationController({
    required this.resolveConnection,
    UtteranceTranscriber? transcriber,
    DictationHapticSender? hapticSender,
  })  : transcribe = transcriber ?? defaultUtteranceTranscriber,
        sendHaptic = hapticSender ?? _defaultHaptic;

  bool get isCapturing => _captureStart != null;

  /// Next session id: 1..255, never 0 (firmware reserves it), never reused
  /// before a firmware reset (firmware rejects duplicates explicitly).
  int get _nextSession {
    _lastSession = (_lastSession % 255) + 1;
    return _lastSession;
  }

  /// Button press (value 4): start a new utterance capture.
  void startCapture(BleAudioCodec codec) {
    _captureStart = DateTime.now();
    _codec = codec;
    _payloads.clear();
    _utteranceTimer?.cancel();
    _utteranceTimer = Timer(maxUtterance, () {
      debugPrint('[hid-dictation] utterance timed out, dropping capture');
      _resetCapture();
    });
  }

  /// Feed one stripped opus payload while capturing (no-op otherwise).
  void onAudioPayload(List<int> payload) {
    if (_captureStart != null && payload.isNotEmpty) {
      _payloads.add(payload);
    }
  }

  /// Button release (value 5): transcribe, validate, send to the pendant.
  Future<void> finishCapture(String deviceId) async {
    if (_captureStart == null) return;
    final codec = _codec;
    final payloads = List<List<int>>.from(_payloads);
    final duration = DateTime.now().difference(_captureStart!);
    _resetCapture();

    if (payloads.isEmpty || codec == null) {
      debugPrint('[hid-dictation] no audio captured; nothing to do');
      return;
    }
    debugPrint('[hid-dictation] utterance ${duration.inMilliseconds}ms, '
        '${payloads.length} packets, codec ${codec.name}');

    final connection = await resolveConnection(deviceId);
    if (connection == null) {
      debugPrint('[hid-dictation] no connection; utterance dropped');
      return;
    }

    String? transcript;
    try {
      transcript = await transcribe(payloads, codec);
    } catch (e) {
      debugPrint('[hid-dictation] transcription failed: $e');
    }
    transcript = transcript?.trim() ?? '';
    if (transcript.isEmpty) {
      debugPrint('[hid-dictation] empty transcript; nothing typed');
      return;
    }
    if (transcript.length > HidDictationProtocol.maxTextLength) {
      debugPrint('[hid-dictation] transcript ${transcript.length} chars exceeds '
          '${HidDictationProtocol.maxTextLength}; refusing to truncate silently');
      return;
    }
    final badIndex = HidDictationProtocol.firstUnsupportedIndex(transcript);
    if (badIndex != null) {
      // Explicit rejection: no transliteration, no partial typing.
      debugPrint('[hid-dictation] transcript has unsupported character at '
          '$badIndex (${transcript.codeUnitAt(badIndex)}); refusing to send');
      return;
    }

    await _sendText(connection, transcript, deviceId);
  }

  /// Cancel any in-flight capture without transcribing.
  void cancelCapture() {
    if (_captureStart == null) return;
    debugPrint('[hid-dictation] capture cancelled');
    _resetCapture();
  }

  Future<void> _sendText(OmiDeviceConnection connection, String text, String deviceId) async {
    final session = _nextSession;
    final frames = HidDictationProtocol.buildFrames(session, text);
    if (frames.isEmpty) return;

    final done = Completer<HidDictationStatus>();
    _statusSub?.cancel();
    _statusSub = connection.performSubscribeHidDictationStatus().listen((status) {
      // The firmware clears activeSession and stamps lastFinishedSession on
      // every terminal transition (done, error, cancel) — that is the only
      // reliable completion signal; intermediate RECEIVING notifies also
      // carry the session id.
      if (status.lastFinishedSession == session && status.activeSession == HidDictationProtocol.sessionNone) {
        done.complete(status);
      }
    });

    try {
      for (final frame in frames) {
        final ok = await connection.performSendHidDictationFrame(frame);
        if (!ok) {
          debugPrint('[hid-dictation] frame write failed; aborting send');
          await _cancelOnDevice(connection);
          return;
        }
      }
      debugPrint('[hid-dictation] sent $session (${frames.length} frames, '
          '${text.length} chars); typing…');

      final status = await done.future.timeout(typingTimeout);
      if (status.isError) {
        debugPrint('[hid-dictation] pendant reported error: ${status.describe()}');
        await sendHaptic(deviceId, 3);
      } else {
        debugPrint('[hid-dictation] typed ${status.charsTyped} chars');
        await sendHaptic(deviceId, 2);
      }
    } catch (e) {
      debugPrint('[hid-dictation] send failed: $e — cancelling on device');
      await _cancelOnDevice(connection);
    } finally {
      await _statusSub?.cancel();
      _statusSub = null;
    }
  }

  Future<void> _cancelOnDevice(OmiDeviceConnection connection) async {
    await connection.performSendHidDictationFrame(HidDictationProtocol.buildCancelFrame());
  }

  void _resetCapture() {
    _utteranceTimer?.cancel();
    _utteranceTimer = null;
    _captureStart = null;
    _codec = null;
    _payloads.clear();
  }

  /// Whether the connected pendant advertises the dictation feature bit.
  Future<bool> isDeviceSupported(String deviceId) async {
    final connection = await resolveConnection(deviceId);
    if (connection == null) return false;
    final features = await connection.getFeatures();
    return (features & OmiFeatures.hidDictation) != 0;
  }

  /// Opt the pendant into the HID prototype. Takes effect on the next
  /// reconnect; [reconnect] disconnects so the native stack can reconnect
  /// against the new GATT table.
  Future<HidDictationStatus?> enableHid(String deviceId, {required Future<void> Function() reconnect}) async {
    return _writeCommand(deviceId, HidDictationProtocol.cmdEnable, reconnect: reconnect);
  }

  Future<HidDictationStatus?> disableHid(String deviceId, {required Future<void> Function() reconnect}) async {
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

  static Future<void> _defaultHaptic(String deviceId, int level) async {
    try {
      final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
      if (connection is OmiDeviceConnection) {
        await connection.performPlayToSpeakerHaptic(level);
      }
    } catch (e) {
      Logger.debug('[hid-dictation] haptic failed: $e');
    }
  }
}

/// Production transcriber: packed opus frames → WAV → one-shot
/// /v2/voice-message/transcribe → plain transcript.
Future<String?> defaultUtteranceTranscriber(List<List<int>> opusPayloads, BleAudioCodec codec) async {
  final builder = BytesBuilder();
  for (final payload in opusPayloads) {
    builder.add(payload);
  }
  final opusBytes = builder.takeBytes();
  if (opusBytes.isEmpty) return null;

  final transcoder = OpusFramesToWavTranscoder(frameSizeBytes: codec.getFrameSize());
  final wav = transcoder.transcode(Uint8List.fromList(opusBytes));
  if (wav.isEmpty) return null;

  final file = File('${Directory.systemTemp.path}/hid_dictation_${DateTime.now().millisecondsSinceEpoch}.wav');
  await file.writeAsBytes(wav, flush: true);
  try {
    return await transcribeVoiceMessage([file]);
  } finally {
    try {
      await file.delete();
    } catch (_) {}
  }
}
