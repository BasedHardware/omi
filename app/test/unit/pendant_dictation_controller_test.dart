import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/pendant_dictation_controller.dart';
import 'package:omi/services/devices/connectors/omi_connection.dart';
import 'package:omi/services/devices/hid_dictation_protocol.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class _FakeTransport implements DeviceTransport {
  final List<(String service, String characteristic, List<int> data)> writes = [];
  final StreamController<List<int>> statusController = StreamController.broadcast();
  List<int> featuresBytes = [0, 0, 0, 0];
  bool emitErrorStatus = false;

  @override
  String get deviceId => 'pendant';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Future<bool> requestBond() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return statusController.stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    return featuresBytes;
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add((serviceUuid, characteristicUuid, data));
    if (characteristicUuid == OmiDeviceConnection.dictationTextCharacteristicUuid &&
        data.length >= 3 &&
        (data[1] & HidDictationProtocol.flagFinal) != 0) {
      // Mimic the firmware's terminal transition: active -> 0,
      // lastFinished -> session. Errors come back as stateError.
      final status = Uint8List(10);
      status[1] = emitErrorStatus ? HidDictationProtocol.stateError : HidDictationProtocol.stateDone;
      status[4] = emitErrorStatus ? HidDictationProtocol.errNotSubscribed : HidDictationProtocol.errNone;
      status[6] = HidDictationProtocol.sessionNone;
      status[7] = data[0];
      scheduleMicrotask(() => statusController.add(status));
    }
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  Future<void> dispose() async {}
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
  String? transcriptToReturn;

  PendantDictationController buildController() {
    return PendantDictationController(
      resolveConnection: (deviceId) async => connection,
      transcriber: (payloads, codec) async {
        transcribedPayloads.add('call:${payloads.length}');
        return transcriptToReturn;
      },
      hapticSender: (deviceId, level) async {
        haptics.add((deviceId, level));
      },
    );
  }

  setUp(() {
    transport = _FakeTransport();
    connection = _connection(transport);
    transcribedPayloads = [];
    haptics = [];
    transcriptToReturn = null;
  });

  test('press collects payloads, release transcribes and sends frames', () async {
    transcriptToReturn = 'Hello world';
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    expect(controller.isCapturing, isTrue);
    controller.onAudioPayload([1, 2, 3]);
    controller.onAudioPayload([4, 5]);
    await controller.finishCapture('pendant');

    expect(controller.isCapturing, isFalse);
    expect(transcribedPayloads, ['call:2']);

    final textWrites =
        transport.writes.where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid).toList();
    expect(textWrites, hasLength(1));
    final frame = textWrites.single.$3;
    expect(frame[0], 1); // first session id
    expect(frame[1], HidDictationProtocol.flagFinal);
    expect(String.fromCharCodes(frame.sublist(3)), 'Hello world');
    expect(haptics, [('pendant', 2)]); // success haptic
  });

  test('transcript with unsupported characters is rejected before any write', () async {
    transcriptToReturn = 'hi\nthere';
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    await controller.finishCapture('pendant');

    expect(transport.writes.where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid), isEmpty);
    expect(haptics, isEmpty);
  });

  test('empty transcript never writes', () async {
    transcriptToReturn = '   ';
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    await controller.finishCapture('pendant');

    expect(transport.writes.where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid), isEmpty);
  });

  test('overlong transcript is refused instead of truncated', () async {
    transcriptToReturn = 'a' * (HidDictationProtocol.maxTextLength + 1);
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    await controller.finishCapture('pendant');

    expect(transport.writes.where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid), isEmpty);
  });

  test('cancelCapture drops the utterance without transcribing', () async {
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    controller.cancelCapture();
    expect(controller.isCapturing, isFalse);

    await controller.finishCapture('pendant');
    expect(transcribedPayloads, isEmpty);
  });
  test('long transcript is chunked into ordered frames', () async {
    transcriptToReturn = 'b' * 250; // 200 + 50, under the 256-char firmware cap
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    await controller.finishCapture('pendant');

    final frames = transport.writes
        .where((w) => w.$2 == OmiDeviceConnection.dictationTextCharacteristicUuid)
        .map((w) => w.$3)
        .toList();
    expect(frames, hasLength(2));
    expect(frames[0][1], 0x00);
    expect(frames[0][2], 200);
    expect(frames.last[1], HidDictationProtocol.flagFinal);
    expect(frames.last[2], 50);
    expect(frames.map((f) => String.fromCharCodes(f.sublist(3))).join(), 'b' * 250);
  });

  test('failure haptic fires when the pendant reports an error status', () async {
    transcriptToReturn = 'nope';
    transport.emitErrorStatus = true;
    final controller = buildController();

    controller.startCapture(BleAudioCodec.opus);
    controller.onAudioPayload([1]);
    await controller.finishCapture('pendant');

    expect(haptics, [('pendant', 3)]); // error haptic
  });
}
