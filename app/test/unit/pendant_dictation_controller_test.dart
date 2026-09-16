import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/pendant_dictation_controller.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/hid_dictation_protocol.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

/// Status bytes the fake serves for the control characteristic.
Uint8List statusBytes({
  required int session,
  bool hidActive = true,
  int state = HidDictationProtocol.stateDone,
  int lastError = HidDictationProtocol.errNone,
  int charsTyped = 0,
}) {
  final s = Uint8List(10);
  s[0] = 1;
  s[1] = state;
  s[2] = hidActive ? 1 : 0;
  s[4] = lastError;
  s[6] = HidDictationProtocol.sessionNone;
  s[7] = session;
  ByteData.view(s.buffer).setUint16(8, charsTyped, Endian.little);
  return s;
}

class _FakeTransport implements DeviceTransport {
  final List<(String service, String characteristic, List<int> data)> writes = [];
  final StreamController<DeviceTransportState> _stateController = StreamController<DeviceTransportState>.broadcast();
  final List<int> controlCommands = [];
  List<int> featuresBytes = [0, 0, 0, 0];

  /// Session whose final frame was written last; poll reads answer with a
  /// terminal status for it once set (mirrors the firmware DONE transition).
  int? lastFinishedSession;
  int? lastSessionSeen;
  int sessionChars = 0;
  bool hidActiveInStatus = true;
  bool connected = true;
  bool neverTerminal = false;
  int? errorForSession;

  @override
  String get deviceId => 'pendant';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<bool> ping() async => true;

  @override
  Future<bool> requestBond() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return const Stream.empty();
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    if (characteristicUuid == OmiDeviceConnection.featuresCharacteristicUuid) {
      return featuresBytes;
    }
    if (characteristicUuid == OmiDeviceConnection.dictationControlCharacteristicUuid) {
      if (neverTerminal) {
        // Still mid-session: active session set, nothing finished yet.
        final pending = Uint8List(10);
        pending[0] = 1;
        pending[1] = HidDictationProtocol.stateTyping;
        pending[2] = hidActiveInStatus ? 1 : 0;
        pending[6] = lastFinishedSession ?? 1;
        pending[7] = HidDictationProtocol.sessionNone;
        return pending;
      }
      final session = lastFinishedSession;
      if (session == null) {
        return statusBytes(session: 0, hidActive: hidActiveInStatus, state: HidDictationProtocol.stateIdle);
      }
      return statusBytes(
        session: session,
        hidActive: hidActiveInStatus,
        state: errorForSession != null ? HidDictationProtocol.stateError : HidDictationProtocol.stateDone,
        lastError: errorForSession ?? HidDictationProtocol.errNone,
        charsTyped: sessionChars,
      );
    }
    return [0];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add((serviceUuid, characteristicUuid, data));
    if (characteristicUuid == OmiDeviceConnection.dictationControlCharacteristicUuid && data.length == 1) {
      controlCommands.add(data[0]);
    }
    if (characteristicUuid == OmiDeviceConnection.dictationTextCharacteristicUuid && data.length >= 3) {
      if (lastSessionSeen != data[0]) {
        lastSessionSeen = data[0];
        sessionChars = 0;
      }
      sessionChars += data.length - 3;
      if ((data[1] & HidDictationProtocol.flagFinal) != 0) {
        lastFinishedSession = data[0];
      }
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  /// Simulates the SAME transport dropping and auto-reconnecting: emits a
  /// disconnect event while staying logically connected afterwards.
  void emitDropAndReconnect() {
    _stateController.add(DeviceTransportState.disconnected);
    _stateController.add(DeviceTransportState.connecting);
    _stateController.add(DeviceTransportState.connected);
  }

  @override
  Future<void> dispose() async {
    await _stateController.close();
  }
}

OmiDeviceConnection _connection(_FakeTransport transport) {
  final device = BtDevice(name: 'Omi', id: 'pendant', type: DeviceType.omi, rssi: -60);
  return OmiDeviceConnection(device, transport);
}

void main() {
  late _FakeTransport transport;
  late OmiDeviceConnection connection;
  late List<String> transcribedPayloads;
  late List<(String, int)> haptics;
  Completer<String>? transcribeGate;
  String? transcriptToReturn;

  PendantDictationController buildController({bool gateAllows = true}) {
    return PendantDictationController(
      resolveConnection: (deviceId) async => transport.connected ? connection : null,
      getCodec: (deviceId) async => BleAudioCodec.opus,
      transcriber: (payloads, codec) async {
        transcribedPayloads.add('call:${payloads.length}');
        if (transcribeGate != null) {
          final gated = await transcribeGate!.future;
          return gated;
        }
        return transcriptToReturn ?? '';
      },
      hapticSender: (deviceId, level) async {
        haptics.add((deviceId, level));
      },
      captureGate: () => gateAllows,
      typingTimeout: const Duration(milliseconds: 400),
      statusPollInterval: const Duration(milliseconds: 20),
    );
  }

  Iterable<List<int>> textWrites() =>
      transport.writes.where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid).map((w) => w.$3);

  setUp(() {
    transport = _FakeTransport();
    connection = _connection(transport);
    transport.featuresBytes = Uint8List(4)..buffer.asByteData().setUint32(0, OmiFeatures.hidDictation, Endian.little);
    transcribedPayloads = [];
    haptics = [];
    transcribeGate = null;
    transcriptToReturn = null;
  });

  test('tap starts a capture, second tap transcribes and completes', () async {
    transcriptToReturn = 'Hello world';
    final controller = buildController();

    expect(await controller.onButtonEvent('pendant', 1), isTrue);
    expect(controller.isCapturing, isTrue);
    controller.onAudioPayload([1, 2, 3]);
    controller.onAudioPayload([4, 5]);
    await controller.onButtonEvent('pendant', 1);

    expect(controller.isCapturing, isFalse);
    expect(transcribedPayloads, ['call:2']);
    final frames = textWrites().toList();

    expect(frames, hasLength(1));
    expect(frames[0][0], 1); // first session id
    expect(frames[0][1], HidDictationProtocol.flagFinal);
    expect(String.fromCharCodes(frames[0].sublist(3)), 'Hello world');
    expect(haptics, contains(('pendant', 1))); // capture-start haptic
    expect(haptics, contains(('pendant', 2))); // typed haptic
    expect(controller.state.value.phase, PendantDictationPhase.done);
  });

  test('all other button events are consumed without side effects', () async {
    final controller = buildController();
    for (final event in [2, 3, 4, 5]) {
      expect(await controller.onButtonEvent('pendant', event), isTrue);
    }
    expect(controller.isCapturing, isFalse);
    expect(transcribedPayloads, isEmpty);
    expect(textWrites(), isEmpty);
  });

  test('non-ASCII transcript is rejected whole before any frame', () async {
    transcriptToReturn = 'hi\nthere';
    final controller = buildController();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    await controller.onButtonEvent('pendant', 1);

    expect(textWrites(), isEmpty);
    expect(haptics, contains(('pendant', 3)));
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('missing firmware feature bit refuses before transcribing', () async {
    transport.featuresBytes = [0, 0, 0, 0];
    final controller = buildController();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    await controller.onButtonEvent('pendant', 1);

    expect(transcribedPayloads, isEmpty);
    expect(textWrites(), isEmpty);
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('inactive HID on the pendant refuses before transcribing', () async {
    transport.hidActiveInStatus = false;
    final controller = buildController();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    await controller.onButtonEvent('pendant', 1);

    expect(transcribedPayloads, isEmpty);
    expect(textWrites(), isEmpty);
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('capture gate (e.g. batch mode) blocks capture start', () async {
    final controller = buildController(gateAllows: false);

    await controller.onButtonEvent('pendant', 1);
    expect(controller.isCapturing, isFalse);
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('cancel while transcribing drops the utterance and writes nothing', () async {
    final controller = buildController();
    transcribeGate = Completer<String>();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final finishing = controller.onButtonEvent('pendant', 1);
    await Future.delayed(const Duration(milliseconds: 10));
    await controller.cancelCapture('pendant');
    transcribeGate!.complete('stale text that must never be typed');
    await finishing;

    expect(textWrites(), isEmpty);
    expect(haptics, isNot(contains(('pendant', 2))));
  });

  test('link drop while transcribing drops the utterance', () async {
    final controller = buildController();
    transcribeGate = Completer<String>();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final finishing = controller.onButtonEvent('pendant', 1);
    await Future.delayed(const Duration(milliseconds: 10));
    transport.connected = false; // same-link epoch check fails afterwards
    transcribeGate!.complete('orphaned text');
    await finishing;

    expect(textWrites(), isEmpty);
  });

  test('device error status surfaces as error haptic and message', () async {
    transcriptToReturn = 'nope';
    final controller = buildController();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    transport.errorForSession = HidDictationProtocol.errNotSubscribed;
    await controller.onButtonEvent('pendant', 1);

    expect(haptics, contains(('pendant', 3)));
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('same-connection drop+reconnect during transcription voids the utterance', () async {
    final controller = buildController();
    transcribeGate = Completer<String>();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final finishing = controller.onButtonEvent('pendant', 1);
    await Future.delayed(const Duration(milliseconds: 10));
    // The SAME transport object drops and comes back while we wait.
    transport.emitDropAndReconnect();
    transcribeGate!.complete('stale text over a replacement link');
    await finishing;

    expect(textWrites(), isEmpty); // epoch changed: never delivered
    expect(transcribedPayloads, isNotEmpty); // transcription did run
  });

  test('drop during capture discards audio before transcription', () async {
    final controller = buildController();
    await controller.onButtonEvent('pendant', 1);
    await Future<void>.delayed(Duration.zero);
    controller.onAudioPayload([1]);
    transport.emitDropAndReconnect();
    await Future<void>.delayed(Duration.zero);
    expect(controller.isCapturing, isFalse);
    expect(transcribedPayloads, isEmpty);
    expect(textWrites(), isEmpty);
    controller.dispose();
  });

  test('drop during typing never sends a stale cancel over the replacement link', () async {
    transcriptToReturn = 'pending';
    transport.neverTerminal = true;
    final controller = buildController();
    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final finishing = controller.onButtonEvent('pendant', 1);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(textWrites(), isNotEmpty);
    transport.emitDropAndReconnect();
    await finishing;
    expect(textWrites().where((f) => (f[1] & HidDictationProtocol.flagCancel) != 0), isEmpty);
    expect(haptics, isNot(contains(('pendant', 2))));
    controller.dispose();
  });

  test('dispose while typing cancels only its owned session', () async {
    transcriptToReturn = 'pending';
    transport.neverTerminal = true;
    final controller = buildController();
    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final finishing = controller.onButtonEvent('pendant', 1);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    controller.dispose();
    await finishing;
    final cancels = textWrites().where((f) => (f[1] & HidDictationProtocol.flagCancel) != 0);
    expect(cancels, isNotEmpty);
    expect(cancels.every((f) => f[0] == 1), isTrue);
    expect(haptics, isNot(contains(('pendant', 2))));
  });

  test('enable flow writes the command, reconnects, and verifies activation', () async {
    final controller = buildController();
    bool reconnected = false;

    final ok = await controller.enableHid(
      'pendant',
      reconnect: () async {
        reconnected = true;
        transport.hidActiveInStatus = true; // the new GATT table after reconnect
      },
    );

    expect(ok, isTrue);
    expect(reconnected, isTrue);
    expect(transport.controlCommands, [HidDictationProtocol.cmdEnable]);
    expect(controller.state.value.phase, PendantDictationPhase.idle);
    expect(controller.state.value.message, contains('HID active'));
  });

  test('enable flow reports failure when HID never activates', () async {
    final controller = buildController();

    final ok = await controller.enableHid(
      'pendant',
      reconnect: () async {
        transport.hidActiveInStatus = false; // never comes up
      },
      // Short-circuit the bounded wait.
    );

    expect(ok, isFalse);
    expect(controller.state.value.phase, PendantDictationPhase.error);
  });

  test('disable refuses success while the pendant still reports HID active', () async {
    final controller = buildController();
    final ok = await controller.disableHid('pendant', reconnect: () async {});
    expect(ok, isFalse);
    expect(transport.controlCommands, [HidDictationProtocol.cmdDisable]);
    expect(controller.state.value.phase, PendantDictationPhase.error);
    controller.dispose();
  });

  test('disable succeeds only after HID is absent', () async {
    final controller = buildController();
    final ok = await controller.disableHid('pendant', reconnect: () async {
      transport.hidActiveInStatus = false;
    });
    expect(ok, isTrue);
    expect(controller.state.value.phase, PendantDictationPhase.idle);
    controller.dispose();
  });

  test('stale pipeline never cancels a newer session', () async {
    transcriptToReturn = 'first';
    final controller = buildController();
    transcribeGate = Completer<String>();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    final firstFinish = controller.onButtonEvent('pendant', 1);
    await Future.delayed(const Duration(milliseconds: 10));

    // User starts a NEW utterance while the first transcription is pending.
    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([2]);

    // First pipeline resumes stale: it must not send or cancel anything.
    transcribeGate!.complete('stale');
    await firstFinish;
    expect(textWrites(), isEmpty);
    expect(transport.writes.any((w) => w.$3.length == 3 && (w.$3[1] & HidDictationProtocol.flagCancel) != 0), isFalse);

    // The new utterance completes normally on session 2 (session 1 unused).
    transcriptToReturn = 'second';
    await controller.onButtonEvent('pendant', 1);
    final frames = textWrites().toList();
    expect(frames, isNotEmpty);
    expect(frames.first[0], 1); // the stale pipeline never consumed a session id
  });

  test('typing timeout cancels the session on device', () async {
    transcriptToReturn = 'slow';
    transport.neverTerminal = true; // polled status never reaches terminal
    final controller = buildController();

    await controller.onButtonEvent('pendant', 1);
    controller.onAudioPayload([1]);
    await controller.onButtonEvent('pendant', 1);

    expect(controller.state.value.phase, PendantDictationPhase.error);
    expect(
      transport.writes.any((w) => w.$3.length == 3 && (w.$3[1] & HidDictationProtocol.flagCancel) != 0),
      isTrue,
    );
    expect(haptics, contains(('pendant', 3)));
  });
}
