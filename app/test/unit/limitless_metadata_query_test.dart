import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/discovery/device_locator.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeLimitlessTransport extends DeviceTransport {
  _FakeLimitlessTransport({this.deviceId = 'limitless-1'});

  @override
  final String deviceId;

  final Map<String, StreamController<List<int>>> _rxControllers = {};
  final Map<String, int> streamListenCounts = {};
  final StreamController<DeviceTransportState> _stateController =
      StreamController<DeviceTransportState>.broadcast();
  final List<List<int>> writes = [];
  bool physicallyConnected = true;
  bool throwOnNextWrite = false;
  int connectCalls = 0;
  int disconnectCalls = 0;

  StreamController<List<int>> _controllerFor(String characteristicUuid) {
    return _rxControllers.putIfAbsent(
      characteristicUuid,
      () => StreamController<List<int>>.broadcast(
        onListen: () {
          streamListenCounts[characteristicUuid] =
              (streamListenCounts[characteristicUuid] ?? 0) + 1;
        },
      ),
    );
  }

  void emitRx(List<int> data) {
    _controllerFor(limitlessRxCharUuid).add(data);
  }

  void emitState(DeviceTransportState state) {
    physicallyConnected = state == DeviceTransportState.connected;
    _stateController.add(state);
  }

  @override
  Future<void> connect() async {
    connectCalls++;
    emitState(DeviceTransportState.connected);
  }

  @override
  Future<void> disconnect() async {
    disconnectCalls++;
    emitState(DeviceTransportState.disconnected);
  }

  @override
  Future<bool> isConnected() async => physicallyConnected;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return _controllerFor(characteristicUuid).stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(
    String serviceUuid,
    String characteristicUuid,
    List<int> data,
  ) async {
    if (throwOnNextWrite) {
      throwOnNextWrite = false;
      throw StateError('Simulated BLE write error');
    }
    writes.add(List<int>.from(data));
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  @override
  Future<void> dispose() async {}
}

List<int> _varint(int value) {
  final out = <int>[];
  var v = value;
  while (v > 0x7f) {
    out.add((v & 0x7f) | 0x80);
    v >>= 7;
  }
  out.add(v & 0x7f);
  return out;
}

List<dynamic> _decodeVarint(List<int> data, int pos) {
  var result = 0;
  var shift = 0;
  var p = pos;
  while (p < data.length) {
    final byte = data[p];
    p++;
    result |= (byte & 0x7f) << shift;
    if ((byte & 0x80) == 0) break;
    shift += 7;
  }
  return [result, p];
}

List<int> _protoField(int fieldNum, int wireType, List<int> value) => [
      ..._varint((fieldNum << 3) | wireType),
      ...value,
    ];

List<int> _intField(int fieldNum, int value) => _protoField(fieldNum, 0, _varint(value));

List<int> _bytesField(int fieldNum, List<int> data) =>
    _protoField(fieldNum, 2, [..._varint(data.length), ...data]);

List<int> _stringField(int fieldNum, String value) => _bytesField(fieldNum, utf8.encode(value));

List<int> _bleWrapper(int index, int seq, int numFrags, List<int> payload) => [
      ..._intField(1, index),
      ..._intField(2, seq),
      ..._intField(3, numFrags),
      ..._bytesField(4, payload),
    ];

List<int> _requestDataField(int requestId, {int status = 0}) => _bytesField(30, [
      ..._intField(1, requestId),
      ..._intField(2, status),
    ]);

List<int> _deviceInfoPayload({
  required int? requestId,
  String? firmware,
  String? hardware,
  String? model,
  String? manufacturer,
  int? protocolVersion,
  String? secretSerial,
  String? secretKey,
  int requestStatus = 0,
}) {
  final infoBody = <int>[
    if (firmware != null) ..._stringField(1, firmware),
    if (hardware != null) ..._stringField(2, hardware),
    if (model != null) ..._stringField(3, model),
    if (manufacturer != null) ..._stringField(4, manufacturer),
    if (protocolVersion != null) ..._intField(5, protocolVersion),
    if (secretSerial != null) ..._stringField(5, secretSerial),
    if (secretKey != null) ..._stringField(6, secretKey),
  ];
  return [
    ..._bytesField(14, infoBody),
    if (requestId != null) ..._requestDataField(requestId, status: requestStatus),
  ];
}

Map<String, dynamic> _decodeWrapperCommand(List<int> data) {
  var pos = 0;
  int? index;
  var seq = 0;
  int? numFrags;
  List<int>? payload;
  while (pos < data.length) {
    final tag = data[pos];
    final fieldNum = tag >> 3;
    final wireType = tag & 0x07;
    pos++;
    if (wireType == 0) {
      final result = _decodeVarint(data, pos);
      pos = result[1] as int;
      if (fieldNum == 1) index = result[0] as int;
      if (fieldNum == 2) seq = result[0] as int;
      if (fieldNum == 3) numFrags = result[0] as int;
    } else if (wireType == 2) {
      final lengthResult = _decodeVarint(data, pos);
      final length = lengthResult[0] as int;
      pos = lengthResult[1] as int;
      if (fieldNum == 4) payload = data.sublist(pos, pos + length);
      pos += length;
    } else {
      break;
    }
  }
  int? messageNumber;
  List<int>? messageBytes;
  int? requestId;
  var p = 0;
  final body = payload ?? const <int>[];
  while (p < body.length) {
    final tagResult = _decodeVarint(body, p);
    final tag = tagResult[0] as int;
    p = tagResult[1] as int;
    final fieldNum = tag >> 3;
    final wireType = tag & 0x07;
    if (wireType != 2) break;
    final lengthResult = _decodeVarint(body, p);
    final length = lengthResult[0] as int;
    p = lengthResult[1] as int;
    final content = body.sublist(p, p + length);
    p += length;
    if (fieldNum == 30) {
      if (content.isNotEmpty && content[0] == 0x08) {
        requestId = _decodeVarint(content, 1)[0] as int;
      }
    } else {
      messageNumber = fieldNum;
      messageBytes = content;
    }
  }
  return {
    'index': index,
    'seq': seq,
    'numFrags': numFrags,
    'messageNumber': messageNumber,
    'messageBytes': messageBytes,
    'requestId': requestId,
  };
}

List<int> _opusFrame(int toc, int seed, int length) {
  final frame = <int>[toc];
  for (var i = 1; i < length; i++) {
    frame.add(0x80 | ((seed * 31 + i * 7) % 48));
  }
  return frame;
}

BtDevice _limitlessDevice({String id = 'limitless-1', String name = 'Limitless Pendant'}) =>
    BtDevice(
      id: id,
      name: name,
      type: DeviceType.limitless,
      rssi: -45,
      locator: DeviceLocator.bluetooth(deviceId: id),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final mockedChannels = <String>{};

  void mockBleHostApi(String method) {
    final channel = 'dev.flutter.pigeon.omi_pigeon.BleHostApi.$method';
    mockedChannels.add(channel);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      channel,
      (ByteData? message) async => BleHostApi.pigeonChannelCodec.encodeMessage(<Object?>[null]),
    );
  }

  setUp(() async {
    mockBleHostApi('stopScan');
    mockBleHostApi('startScan');
    mockBleHostApi('configureSavedReconnect');
    mockBleHostApi('unmanageDevice');
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() {
    for (final channel in mockedChannels) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMessageHandler(channel, null);
    }
    mockedChannels.clear();
  });

  test('rejects disconnected, uninitialized, wrong-device, busy, and overlapping states without BLE writes',
      () async {
    final transport = _FakeLimitlessTransport();
    final device = _limitlessDevice();
    final connection = LimitlessDeviceConnection(
      device,
      transport,
      streamHealthWindow: const Duration(minutes: 1),
      metadataQueryTimeout: const Duration(milliseconds: 50),
    );

    // 1. Disconnected before connect() -> no BLE write.
    final beforeConnect = await connection.queryCompatibilityMetadata();
    expect(beforeConnect.status, LimitlessMetadataQueryStatus.disconnected);
    expect(beforeConnect.didWriteToDevice, isFalse);
    expect(transport.writes, isEmpty);

    // 2. Wrong device type -> no BLE write.
    final wrongTypeConn = LimitlessDeviceConnection(
      BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -40),
      transport,
      streamHealthWindow: const Duration(minutes: 1),
    );
    final wrongTypeResult = await wrongTypeConn.queryCompatibilityMetadata();
    expect(wrongTypeResult.status, LimitlessMetadataQueryStatus.wrongDevice);
    expect(transport.writes, isEmpty);

    // 3. During connect() before initialization completes -> rejected without extra write.
    final connectFuture = connection.connect();
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(connection.isInitialized, isFalse);
    final duringSetup = await connection.queryCompatibilityMetadata();
    expect(duringSetup.status, LimitlessMetadataQueryStatus.disconnected);
    expect(transport.writes, isEmpty);

    await connectFuture;
    expect(connection.isInitialized, isTrue);
    expect(transport.writes.length, 2); // msg 6 (time sync) + msg 8 (enable stream)

    // 4. Batch/sync-busy state -> rejected without device info write.
    await connection.enableBatchMode();
    expect(transport.writes.length, 3);
    final whileBusy = await connection.queryCompatibilityMetadata();
    expect(whileBusy.status, LimitlessMetadataQueryStatus.busy);
    expect(whileBusy.didWriteToDevice, isFalse);
    expect(transport.writes.length, 3);

    await connection.disableBatchMode();
    expect(transport.writes.length, 4);

    // 5. Overlapping query while one is in flight -> second rejected with no extra BLE write.
    final firstQuery = connection.queryCompatibilityMetadata(
      timeout: const Duration(milliseconds: 60),
    );
    final overlappingQuery = await connection.queryCompatibilityMetadata(
      timeout: const Duration(milliseconds: 60),
    );
    expect(overlappingQuery.status, LimitlessMetadataQueryStatus.overlappingQuery);
    expect(overlappingQuery.didWriteToDevice, isFalse);
    expect(transport.writes.length, 5, reason: 'only the first query may write to the pendant');

    final firstResult = await firstQuery;
    expect(firstResult.status, LimitlessMetadataQueryStatus.timeout);

    await connection.disconnect();
  });

  test('DeviceService routes only to the selected, already-connected Limitless session without connecting',
      () async {
    final transport = _FakeLimitlessTransport();
    final limitless = _limitlessDevice();
    await SharedPreferencesUtil().btDeviceSet(limitless);

    var builderCalls = 0;
    late LimitlessDeviceConnection createdConnection;
    final service = DeviceService(
      connectionBuilder: (device) {
        builderCalls++;
        createdConnection = LimitlessDeviceConnection(
          device,
          transport,
          streamHealthWindow: const Duration(minutes: 1),
          metadataQueryTimeout: const Duration(milliseconds: 100),
        );
        return createdConnection;
      },
      reconnectKilled: () => true,
    );

    // No active connection yet -> must reject as disconnected and NOT build or connect.
    final coldResult = await service.queryLimitlessCompatibilityMetadata();
    expect(coldResult.status, LimitlessMetadataQueryStatus.disconnected);
    expect(builderCalls, 0);
    expect(transport.connectCalls, 0);
    expect(transport.writes, isEmpty);

    // Establish the normal session once.
    final conn = await service.ensureConnection(limitless.id, force: true);
    expect(conn, same(createdConnection));
    expect(transport.writes.length, 2);

    // Requesting a different deviceId must reject as wrongDevice with zero writes.
    final wrongIdResult = await service.queryLimitlessCompatibilityMetadata(deviceId: 'other-id');
    expect(wrongIdResult.status, LimitlessMetadataQueryStatus.wrongDevice);
    expect(transport.writes.length, 2);

    // Changing selected paired device to a non-Limitless device rejects as wrongDevice.
    final omiDevice = BtDevice(id: 'omi-2', name: 'Omi', type: DeviceType.omi, rssi: -40);
    await SharedPreferencesUtil().btDeviceSet(omiDevice);
    final mismatchedPrefResult = await service.queryLimitlessCompatibilityMetadata();
    expect(mismatchedPrefResult.status, LimitlessMetadataQueryStatus.wrongDevice);
    expect(transport.writes.length, 2);

    // Restore selected Limitless device and run a matched query through DeviceService.
    await SharedPreferencesUtil().btDeviceSet(limitless);
    final queryFuture = service.queryLimitlessCompatibilityMetadata();
    await Future<void>.delayed(const Duration(milliseconds: 10));

    expect(transport.writes.length, 3);
    final decodedCmd = _decodeWrapperCommand(transport.writes.last);
    expect(decodedCmd['messageNumber'], 14);
    expect(decodedCmd['messageBytes'], isEmpty);
    expect(decodedCmd['requestId'], 3);

    // Respond across two BLE fragments and include non-allowlisted secret fields (5, 6).
    final fullPayload = _deviceInfoPayload(
      requestId: 3,
      firmware: '2.3.1',
      hardware: 'rev-b2',
      model: 'Limitless Pendant',
      manufacturer: 'Limitless',
      secretSerial: 'SN-DO-NOT-EXPORT-12345',
      secretKey: 'PRIVATE-KEY-BYTES',
    );
    final mid = fullPayload.length ~/ 2;
    transport.emitRx(_bleWrapper(10, 0, 2, fullPayload.sublist(0, mid)));
    transport.emitRx(_bleWrapper(10, 1, 2, fullPayload.sublist(mid)));

    final result = await queryFuture;
    expect(result.status, LimitlessMetadataQueryStatus.ok);
    expect(result.isSuccess, isTrue);
    expect(result.requestId, 3);
    expect(result.metadata?.firmwareRevision, '2.3.1');
    expect(result.metadata?.hardwareRevision, 'rev-b2');
    expect(result.metadata?.modelNumber, 'Limitless Pendant');
    expect(result.metadata?.manufacturerName, 'Limitless');
    expect(result.metadata?.isPlaceholder, isFalse);

    final allowlisted = result.metadata!.toAllowlistedMap();
    expect(allowlisted.keys, everyElement(isIn(LimitlessCompatibilityMetadata.allowlistedKeys)));
    expect(allowlisted.values.join(' '), isNot(contains('SN-DO-NOT-EXPORT-12345')));
    expect(allowlisted.values.join(' '), isNot(contains('PRIVATE-KEY-BYTES')));

    // Paired device selection and preferences remain untouched (transient result).
    expect(SharedPreferencesUtil().btDevice.id, limitless.id);
    expect(SharedPreferencesUtil().btDevice.firmwareRevision, isNull);
    expect(
      transport.streamListenCounts[limitlessRxCharUuid],
      1,
      reason: 'metadata query must reuse the existing RX subscription',
    );

    await service.stop();
  });

  test('distinguishes placeholders/unsupported fields and retires malformed, unmatched, error, and cancelled queries',
      () async {
    final transport = _FakeLimitlessTransport();
    final connection = LimitlessDeviceConnection(
      _limitlessDevice(),
      transport,
      streamHealthWindow: const Duration(minutes: 1),
      metadataQueryTimeout: const Duration(milliseconds: 40),
    );
    await connection.connect();
    expect(transport.writes.length, 2);

    // 1. Placeholder-only response ('1.0.0' + 'Unknown') is rejected as malformedResponse.
    final placeholderQuery = connection.queryCompatibilityMetadata();
    await Future<void>.delayed(const Duration(milliseconds: 5));
    final req1 = _decodeWrapperCommand(transport.writes.last)['requestId'] as int;
    transport.emitRx(
      _bleWrapper(
        1,
        0,
        1,
        _deviceInfoPayload(
          requestId: req1,
          firmware: '1.0.0',
          hardware: 'Unknown',
          model: 'Limitless Pendant',
          manufacturer: 'Limitless',
        ),
      ),
    );
    final placeholderResult = await placeholderQuery;
    expect(placeholderResult.status, LimitlessMetadataQueryStatus.malformedResponse);
    expect(placeholderResult.metadata, isNull);

    // 2. Partial support: real firmware with 'Unknown' hardware normalizes hardwareRevision to null.
    final partialQuery = connection.queryCompatibilityMetadata();
    await Future<void>.delayed(const Duration(milliseconds: 5));
    final req2 = _decodeWrapperCommand(transport.writes.last)['requestId'] as int;
    transport.emitRx(
      _bleWrapper(
        2,
        0,
        1,
        _deviceInfoPayload(
          requestId: req2,
          firmware: '1.8.4',
          hardware: 'Unknown',
        ),
      ),
    );
    final partialResult = await partialQuery;
    expect(partialResult.status, LimitlessMetadataQueryStatus.ok);
    expect(partialResult.metadata?.firmwareRevision, '1.8.4');
    expect(partialResult.metadata?.hardwareRevision, isNull);

    // 3. Unmatched requestId response -> retires with unmatchedResponse.
    final unmatchedQuery = connection.queryCompatibilityMetadata(
      timeout: const Duration(milliseconds: 35),
    );
    await Future<void>.delayed(const Duration(milliseconds: 5));
    transport.emitRx(
      _bleWrapper(
        3,
        0,
        1,
        _deviceInfoPayload(requestId: 999, firmware: '2.0.0', hardware: 'rev-a'),
      ),
    );
    final unmatchedResult = await unmatchedQuery;
    expect(unmatchedResult.status, LimitlessMetadataQueryStatus.unmatchedResponse);

    // 4. Device error status in RequestData -> retires immediately with deviceError.
    final errorQuery = connection.queryCompatibilityMetadata();
    await Future<void>.delayed(const Duration(milliseconds: 5));
    final req4 = _decodeWrapperCommand(transport.writes.last)['requestId'] as int;
    transport.emitRx(
      _bleWrapper(
        4,
        0,
        1,
        _deviceInfoPayload(requestId: req4, firmware: '2.0.0', requestStatus: 1),
      ),
    );
    final errorResult = await errorQuery;
    expect(errorResult.status, LimitlessMetadataQueryStatus.deviceError);

    // 5. Cancellation -> retires only this query.
    final cancelCompleter = Completer<void>();
    final cancelledQuery = connection.queryCompatibilityMetadata(
      timeout: const Duration(seconds: 5),
      cancelTrigger: cancelCompleter.future,
    );
    await Future<void>.delayed(const Duration(milliseconds: 5));
    cancelCompleter.complete();
    final cancelledResult = await cancelledQuery;
    expect(cancelledResult.status, LimitlessMetadataQueryStatus.cancelled);
    expect(connection.status, DeviceConnectionState.connected);

    await connection.disconnect();
  });

  test('preserves ongoing audio capture, button/status consumers, and ignores late notifications',
      () async {
    final transport = _FakeLimitlessTransport();
    final connection = LimitlessDeviceConnection(
      _limitlessDevice(),
      transport,
      streamHealthWindow: const Duration(minutes: 1),
      metadataQueryTimeout: const Duration(milliseconds: 40),
    );
    await connection.connect();

    final receivedAudio = <List<int>>[];
    final receivedButtons = <List<int>>[];
    final audioSub = await connection.getBleAudioBytesListener(
      onAudioBytesReceived: receivedAudio.add,
    );
    final buttonSub = await connection.getBleButtonListener(
      onButtonReceived: receivedButtons.add,
    );

    // Start a metadata query that times out, then emit a late response for that timed-out request.
    final timedOutFuture = connection.queryCompatibilityMetadata(
      timeout: const Duration(milliseconds: 25),
    );
    await Future<void>.delayed(const Duration(milliseconds: 5));
    final timedOutReqId = _decodeWrapperCommand(transport.writes.last)['requestId'] as int;

    // Emit live audio and a double-press button event while the metadata query is waiting.
    final expectedFrame = _opusFrame(0xb8, 1, 40);
    final audioPayload = _bytesField(1, expectedFrame);
    transport.emitRx(_bleWrapper(20, 0, 1, audioPayload));

    final doublePressPayload = _bytesField(8, _intField(1, 3));
    transport.emitRx(_bleWrapper(21, 0, 1, doublePressPayload));

    final timedOutResult = await timedOutFuture;
    expect(timedOutResult.status, LimitlessMetadataQueryStatus.timeout);
    expect(receivedAudio, [expectedFrame]);
    expect(receivedButtons, [
      [2, 0, 0, 0],
    ]);

    // Late notification for the retired query arrives after timeout; must not emit audio or break next query.
    // Note: manufacturer starts with 'p' (0x70) and is 16 chars long to verify DeviceInfo is never
    // misclassified as a 0x22-prefixed Opus frame in real-time mode.
    transport.emitRx(
      _bleWrapper(
        22,
        0,
        1,
        _deviceInfoPayload(
          requestId: timedOutReqId,
          firmware: '2.5.0',
          hardware: 'rev-d',
          manufacturer: 'pendant-hardware',
        ),
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(receivedAudio.length, 1, reason: 'late DeviceInfo packet must never leak into audio stream');

    // Start a fresh query; inject an older unmatched notification before the matched one.
    final nextQueryFuture = connection.queryCompatibilityMetadata(
      timeout: const Duration(milliseconds: 80),
    );
    await Future<void>.delayed(const Duration(milliseconds: 5));
    final nextReqId = _decodeWrapperCommand(transport.writes.last)['requestId'] as int;
    expect(nextReqId, timedOutReqId + 1);

    transport.emitRx(
      _bleWrapper(
        23,
        0,
        1,
        _deviceInfoPayload(requestId: timedOutReqId, firmware: '0.9.0', hardware: 'old'),
      ),
    );
    transport.emitRx(
      _bleWrapper(
        24,
        0,
        1,
        _deviceInfoPayload(
          requestId: nextReqId,
          firmware: '2.6.0',
          hardware: 'rev-e',
          manufacturer: 'pendant-hardware',
        ),
      ),
    );

    final nextResult = await nextQueryFuture;
    expect(nextResult.status, LimitlessMetadataQueryStatus.ok);
    expect(nextResult.metadata?.firmwareRevision, '2.6.0');
    expect(nextResult.metadata?.hardwareRevision, 'rev-e');
    expect(receivedAudio.length, 1);

    await audioSub?.cancel();
    await buttonSub?.cancel();
    await connection.disconnect();
  });
}
