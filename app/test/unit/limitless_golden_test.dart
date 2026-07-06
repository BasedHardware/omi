import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';

class FakeDeviceTransport extends DeviceTransport {
  final Map<String, StreamController<List<int>>> _rxControllers = {};
  final StreamController<DeviceTransportState> _stateController = StreamController<DeviceTransportState>.broadcast();
  final List<List<int>> writes = [];

  StreamController<List<int>> _controllerFor(String characteristicUuid) {
    return _rxControllers.putIfAbsent(characteristicUuid, () => StreamController<List<int>>.broadcast());
  }

  void emit(String characteristicUuid, List<int> data) {
    _controllerFor(characteristicUuid).add(data);
  }

  @override
  String get deviceId => 'fake-limitless';

  @override
  Future<void> connect() async {}

  @override
  Future<void> disconnect() async {}

  @override
  Future<bool> isConnected() async => true;

  @override
  Future<bool> ping() async => true;

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    return _controllerFor(characteristicUuid).stream;
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async => [];

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    writes.add(List<int>.from(data));
  }

  @override
  Stream<DeviceTransportState> get connectionStateStream => _stateController.stream;

  @override
  Future<void> dispose() async {}
}

List<int> varint(int value) {
  final out = <int>[];
  var v = value;
  while (v > 0x7f) {
    out.add((v & 0x7f) | 0x80);
    v >>= 7;
  }
  out.add(v & 0x7f);
  return out;
}

List<dynamic> decodeVarint(List<int> data, int pos) {
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

List<int> protoField(int fieldNum, int wireType, List<int> value) => [...varint((fieldNum << 3) | wireType), ...value];

List<int> intField(int fieldNum, int value) => protoField(fieldNum, 0, varint(value));

List<int> bytesField(int fieldNum, List<int> data) => protoField(fieldNum, 2, [...varint(data.length), ...data]);

List<int> bleWrapper(int index, int seq, int numFrags, List<int> payload) =>
    [...intField(1, index), ...intField(2, seq), ...intField(3, numFrags), ...bytesField(4, payload)];

List<int> mirrorRequestData(int requestId) => bytesField(30, [
      ...intField(1, requestId),
      ...protoField(2, 0, [0x00]),
    ]);

List<int> mirrorSetCurrentTime(int messageIndex, int requestId, int timestampMs) =>
    bleWrapper(messageIndex, 0, 1, [...bytesField(6, intField(1, timestampMs)), ...mirrorRequestData(requestId)]);

List<int> mirrorDownloadFlashPages(int messageIndex, int requestId, bool batchMode, bool realTime) =>
    bleWrapper(messageIndex, 0, 1, [
      ...bytesField(8, [
        ...protoField(1, 0, [batchMode ? 0x01 : 0x00]),
        ...protoField(2, 0, [realTime ? 0x01 : 0x00]),
      ]),
      ...mirrorRequestData(requestId),
    ]);

List<int> mirrorAcknowledgeProcessedData(int messageIndex, int requestId, int upToIndex) =>
    bleWrapper(messageIndex, 0, 1, [...bytesField(7, intField(1, upToIndex)), ...mirrorRequestData(requestId)]);

List<int> mirrorGetDeviceStatus(int messageIndex, int requestId) =>
    bleWrapper(messageIndex, 0, 1, [...bytesField(21, []), ...mirrorRequestData(requestId)]);

Map<String, int>? mirrorParseStorageState(List<int> data, int start, int end) {
  if (start < 0 || end > data.length || start >= end) return null;
  var pos = start;
  while (pos < end - 1 && pos < data.length) {
    if (data[pos] == 0x2a) {
      pos++;
      if (pos >= data.length) break;
      final lengthResult = decodeVarint(data, pos);
      final storageLength = lengthResult[0] as int;
      pos = lengthResult[1] as int;
      if (storageLength < 0 || storageLength > 200 || pos + storageLength > data.length) break;
      final storageEnd = pos + storageLength;
      final state = <String, int>{};
      while (pos < storageEnd - 1 && pos < data.length) {
        final marker = data[pos];
        pos++;
        if (pos >= data.length) break;
        if (marker == 0x08 || marker == 0x10 || marker == 0x18 || marker == 0x20 || marker == 0x28) {
          final valueResult = decodeVarint(data, pos);
          final value = valueResult[0] as int;
          pos = valueResult[1] as int;
          switch (marker) {
            case 0x08:
              state['oldest_flash_page'] = value;
              break;
            case 0x10:
              state['newest_flash_page'] = value;
              break;
            case 0x18:
              state['current_storage_session'] = value;
              break;
            case 0x20:
              state['free_capture_pages'] = value;
              break;
            case 0x28:
              state['total_capture_pages'] = value;
              break;
          }
        }
      }
      return state.isNotEmpty ? state : null;
    }
    pos++;
  }
  return null;
}

Map<String, int>? mirrorParseDeviceStatus(List<int> data) {
  if (data.length < 20) return null;
  var pos = 0;
  while (pos < data.length - 5) {
    if (data[pos] == 0x22) {
      pos++;
      if (pos >= data.length) return null;
      final lengthResult = decodeVarint(data, pos);
      final payloadLength = lengthResult[0] as int;
      pos = lengthResult[1] as int;
      if (payloadLength < 10 || payloadLength > data.length - pos) return null;
      final payloadEnd = pos + payloadLength;
      var innerPos = pos;
      while (innerPos < payloadEnd - 5) {
        if (data[innerPos] == 0x2a) {
          innerPos++;
          if (innerPos >= data.length) return null;
          final statusLengthResult = decodeVarint(data, innerPos);
          final statusLength = statusLengthResult[0] as int;
          innerPos = statusLengthResult[1] as int;
          if (statusLength < 5 || statusLength > 500 || innerPos + statusLength > data.length) return null;
          return mirrorParseStorageState(data, innerPos, innerPos + statusLength);
        }
        innerPos++;
      }
      return null;
    }
    pos++;
  }
  return null;
}

Map<String, dynamic> decodeWrapperCommand(List<int> data) {
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
      final result = decodeVarint(data, pos);
      pos = result[1] as int;
      if (fieldNum == 1) index = result[0] as int;
      if (fieldNum == 2) seq = result[0] as int;
      if (fieldNum == 3) numFrags = result[0] as int;
    } else if (wireType == 2) {
      final lengthResult = decodeVarint(data, pos);
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
    final tagResult = decodeVarint(body, p);
    final tag = tagResult[0] as int;
    p = tagResult[1] as int;
    final fieldNum = tag >> 3;
    final wireType = tag & 0x07;
    if (wireType != 2) break;
    final lengthResult = decodeVarint(body, p);
    final length = lengthResult[0] as int;
    p = lengthResult[1] as int;
    final content = body.sublist(p, p + length);
    p += length;
    if (fieldNum == 30) {
      if (content.isNotEmpty && content[0] == 0x08) {
        requestId = decodeVarint(content, 1)[0] as int;
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

List<int> opusFrame(int toc, int seed, int length) {
  final frame = <int>[toc];
  for (var i = 1; i < length; i++) {
    frame.add(0x80 | ((seed * 31 + i * 7) % 48));
  }
  return frame;
}

List<int> audioBlobOfFrames(List<List<int>> frames) => [for (final f in frames) ...bytesField(1, f)];

List<int> audioWrapper(List<int> audioBlob, {int offset = 0}) =>
    bytesField(3, [...intField(1, offset), ...bytesField(2, audioBlob)]);

List<int> flashPageBytes(int timestampMs, List<List<int>> wrappers) =>
    [...intField(1, timestampMs), for (final w in wrappers) ...w];

List<int> storageBufferBytes({required int session, required int seq, required int index, required List<int> page}) =>
    [...intField(2, session), ...intField(4, seq), ...intField(5, index), ...bytesField(6, page)];

List<int> pendantMessage(List<int> storageBuffer) => bytesField(2, storageBuffer);

String toHex(List<int> data) => data.map((b) => b.toRadixString(16).padLeft(2, '0')).join();

Directory fixtureDirectory() {
  var dir = Directory.current.absolute;
  while (true) {
    if (File('${dir.path}/pubspec.yaml').existsSync()) {
      return Directory('${dir.path}/test/fixtures/limitless_golden');
    }
    final parent = dir.parent;
    if (parent.path == dir.path) {
      throw StateError('Could not locate pubspec.yaml above ${Directory.current.path}');
    }
    dir = parent;
  }
}

void checkGolden(Directory dir, String fileName, Map<String, dynamic> actual) {
  final file = File('${dir.path}/$fileName');
  final normalizedActual = jsonDecode(jsonEncode(actual));
  if (!file.existsSync()) {
    dir.createSync(recursive: true);
    file.writeAsStringSync('${const JsonEncoder.withIndent('  ').convert(actual)}\n');
    return;
  }
  final expected = jsonDecode(file.readAsStringSync());
  expect(
    normalizedActual,
    equals(expected),
    reason: 'Golden fixture drift in $fileName: the Dart Limitless implementation no longer matches the pinned '
        'behavior. If the protocol change is intentional, delete the fixture, re-run this test to regenerate it, '
        'and update the Kotlin port (LimitlessProtocol.kt) to match.',
  );
}

Map<String, dynamic> pageToJson(Map<String, dynamic> page) => {
      'index': page['index'],
      'session': page['session'],
      'timestampMs': page['timestamp_ms'],
      'frames': (page['opus_frames'] as List<List<int>>).map(toHex).toList(),
    };

Map<String, dynamic> caseFixture(
  String name,
  List<List<int>> packets,
  List<Map<String, dynamic>> pages,
  Map<String, int>? storageState,
) =>
    {
      'name': name,
      'packets': packets.map(toHex).toList(),
      'expectedPages': pages.map(pageToJson).toList(),
      'expectedStorageState': storageState,
    };

Map<String, int>? mirrorStorageStateForPackets(List<List<int>> packets) {
  for (final packet in packets) {
    final state = mirrorParseDeviceStatus(packet);
    if (state != null) return state;
  }
  return null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('limitless flash-page protocol golden vectors', () async {
    const timestampMs = 1750000000000;
    const encoderTimestampMs = 1750000000000;
    final fixtures = fixtureDirectory();
    final transport = FakeDeviceTransport();
    final device = BtDevice(name: 'Limitless Pendant', id: 'fake-limitless', type: DeviceType.limitless, rssi: -50);
    final connection = LimitlessDeviceConnection(device, transport);
    final emittedPages = <Map<String, dynamic>>[];
    final pageSubscription = connection.getFlashPageStream().listen(emittedPages.add);

    final beforeConnectMs = DateTime.now().millisecondsSinceEpoch;
    await connection.connect();
    final afterConnectMs = DateTime.now().millisecondsSinceEpoch;
    expect(transport.writes.length, 2, reason: 'connect() must write msg6 then msg8 realtime');

    final msg6Write = transport.writes[0];
    final msg6Decoded = decodeWrapperCommand(msg6Write);
    expect(msg6Decoded['index'], 0);
    expect(msg6Decoded['seq'], 0);
    expect(msg6Decoded['numFrags'], 1);
    expect(msg6Decoded['messageNumber'], 6);
    expect(msg6Decoded['requestId'], 1);
    final msg6Body = msg6Decoded['messageBytes'] as List<int>;
    expect(msg6Body[0], 0x08);
    final liveTimestamp = decodeVarint(msg6Body, 1)[0] as int;
    expect(liveTimestamp, inInclusiveRange(beforeConnectMs, afterConnectMs));
    expect(msg6Write, equals(mirrorSetCurrentTime(0, 1, liveTimestamp)),
        reason: 'local msg6 mirror encoder must reproduce the real _encodeSetCurrentTime bytes');

    expect(transport.writes[1], equals(mirrorDownloadFlashPages(1, 2, false, true)),
        reason: 'connect() enable-data-stream write must match msg8{batch=0,realTime=1} layout');

    await connection.enableBatchMode();
    expect(transport.writes.length, 3);
    expect(transport.writes[2], equals(mirrorDownloadFlashPages(2, 3, true, false)));
    expect(connection.isBatchMode, isTrue);

    final framesA = [for (var i = 0; i < 8; i++) opusFrame(0xb8, i, 40)];
    final packetsA = [
      bleWrapper(
        10,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 1,
          index: 100,
          page: flashPageBytes(timestampMs, [audioWrapper(audioBlobOfFrames(framesA))]),
        )),
      ),
    ];

    final framesB = [for (var i = 0; i < 24; i++) opusFrame(0x78, i + 8, 40)];
    final payloadB = pendantMessage(storageBufferBytes(
      session: 7,
      seq: 2,
      index: 101,
      page: flashPageBytes(timestampMs + 1600, [audioWrapper(audioBlobOfFrames(framesB))]),
    ));
    final packetsB = [
      bleWrapper(11, 1, 3, payloadB.sublist(400, 800)),
      bleWrapper(11, 0, 3, payloadB.sublist(0, 400)),
      bleWrapper(11, 2, 3, payloadB.sublist(800)),
    ];

    final packetsC = [
      bleWrapper(
        12,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 3,
          index: 102,
          page: flashPageBytes(timestampMs + 3200, [
            bytesField(3, bytesField(12, [0x08, 0x01, 0x10, 0x00])),
          ]),
        )),
      ),
    ];

    final directFrameD = opusFrame(0xf8, 40, 40);
    final nestedFramesD = [for (var i = 0; i < 5; i++) opusFrame(0xb0, i + 41, 40)];
    final packetsD = [
      bleWrapper(
        13,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 4,
          index: 103,
          page: flashPageBytes(timestampMs + 4800, [
            audioWrapper([...bytesField(1, directFrameD), ...bytesField(2, audioBlobOfFrames(nestedFramesD))]),
          ]),
        )),
      ),
    ];

    final validFramesE = [opusFrame(0xb8, 50, 40), opusFrame(0x78, 51, 40), opusFrame(0xf0, 52, 40)];
    final invalidZeroFrame = List<int>.filled(40, 0x00);
    final invalidRuntFrame = List<int>.filled(8, 0x11);
    final packetsE = [
      bleWrapper(
        14,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 5,
          index: 104,
          page: flashPageBytes(timestampMs + 6400, [
            audioWrapper([
              ...bytesField(1, validFramesE[0]),
              ...bytesField(1, invalidZeroFrame),
              ...bytesField(1, validFramesE[1]),
              ...bytesField(1, invalidRuntFrame),
              ...bytesField(1, validFramesE[2]),
            ]),
          ]),
        )),
      ),
    ];

    final framesG = [for (var i = 0; i < 8; i++) opusFrame(0xb8, i + 60, 40)];
    final packetsG = [
      [
        ...bleWrapper(
          16,
          0,
          1,
          pendantMessage(storageBufferBytes(
            session: 7,
            seq: 6,
            index: 105,
            page: flashPageBytes(timestampMs + 8000, [audioWrapper(audioBlobOfFrames(framesG))]),
          )),
        ),
        0x3a,
        0xff,
        0x07,
      ],
    ];

    final packetsH = [
      bleWrapper(
        17,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 7,
          index: 106,
          page: flashPageBytes(timestampMs + 9600, [
            audioWrapper([...bytesField(1, invalidZeroFrame), ...bytesField(1, invalidRuntFrame)]),
          ]),
        )),
      ),
    ];

    final statusStorage = [
      ...intField(1, 100),
      ...intField(2, 2500),
      ...intField(3, 3),
      ...intField(4, 120000),
      ...intField(5, 170000),
    ];
    final statusStruct = [...intField(1, 85), ...bytesField(5, statusStorage)];
    final packetsF = [
      bleWrapper(15, 0, 1, [...intField(1, 85), ...bytesField(5, statusStruct)]),
    ];

    final packetsI = [
      bleWrapper(
        18,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 8,
          index: 107,
          page: [
            ...intField(1, timestampMs + 11200),
            0x1a, 0xfa, 0xff, 0xff, 0xff, 0x1f, // wrapper length varint 2^33-6: truncating to Int32 goes negative
            0x00, 0x00, 0x00, 0x00,
          ],
        )),
      ),
    ];

    final packetsJ = [
      bleWrapper(
        19,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 9,
          index: 108,
          page: flashPageBytes(timestampMs + 12800, [
            bytesField(3, [
              0x09, 0x0a, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // fixed64 field before the audio subfield
              ...bytesField(2, bytesField(1, invalidRuntFrame)),
            ]),
          ]),
        )),
      ),
    ];

    final packetsK = [
      bleWrapper(
        20,
        0,
        1,
        pendantMessage(storageBufferBytes(
          session: 7,
          seq: 10,
          index: 109,
          page: flashPageBytes(timestampMs + 14400, [
            bytesField(3, [
              0x0b, 0x0a, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // unknown wire type (3) before the audio subfield
              ...bytesField(2, bytesField(1, invalidRuntFrame)),
            ]),
          ]),
        )),
      ),
    ];

    Future<List<Map<String, dynamic>>> drive(List<List<int>> packets) async {
      final start = emittedPages.length;
      for (final packet in packets) {
        transport.emit(limitlessRxCharUuid, packet);
        await pumpEventQueue();
      }
      return emittedPages.sublist(start);
    }

    final pagesA = await drive(packetsA);
    expect(pagesA.length, 1);
    expect(pagesA[0]['index'], 100);
    expect(pagesA[0]['session'], 7);
    expect(pagesA[0]['timestamp_ms'], timestampMs);
    expect(pagesA[0]['opus_frames'], equals(framesA));

    final beforeB = emittedPages.length;
    transport.emit(limitlessRxCharUuid, packetsB[0]);
    transport.emit(limitlessRxCharUuid, packetsB[1]);
    await pumpEventQueue();
    expect(emittedPages.length, beforeB, reason: 'page must not emit before all 3 fragments arrive');
    transport.emit(limitlessRxCharUuid, packetsB[2]);
    await pumpEventQueue();
    final pagesB = emittedPages.sublist(beforeB);
    expect(pagesB.length, 1);
    expect(pagesB[0]['index'], 101);
    expect(pagesB[0]['opus_frames'], equals(framesB));

    final pagesC = await drive(packetsC);
    expect(pagesC.length, 1);
    expect(pagesC[0]['index'], 102);
    expect(pagesC[0]['opus_frames'], isEmpty);
    expect(pagesC[0]['timestamp_ms'], timestampMs + 3200);

    final pagesD = await drive(packetsD);
    expect(pagesD.length, 1);
    expect(pagesD[0]['opus_frames'], equals([directFrameD, ...nestedFramesD]));

    final pagesE = await drive(packetsE);
    expect(pagesE.length, 1);
    expect(pagesE[0]['opus_frames'], equals(validFramesE));

    final pagesG = await drive(packetsG);
    expect(pagesG.length, 1, reason: 'a truncated trailing wrapper field must not drop the whole packet');
    expect(pagesG[0]['index'], 105);
    expect(pagesG[0]['opus_frames'], equals(framesG));

    final pagesH = await drive(packetsH);
    expect(pagesH, isEmpty, reason: 'an audio page yielding zero valid frames must never surface (no ACK past it)');

    final pagesI = await drive(packetsI);
    expect(pagesI.length, 1, reason: 'an oversized wrapper length must exit the walk and surface as diagnostic');
    expect(pagesI[0]['index'], 107);
    expect(pagesI[0]['opus_frames'], isEmpty);

    final pagesJ = await drive(packetsJ);
    expect(pagesJ, isEmpty, reason: 'fixed64 fields must be skipped when classifying — this page has audio subfields');

    final pagesK = await drive(packetsK);
    expect(pagesK, isEmpty, reason: 'unknown wire types classify as audio — never ACK a page we cannot parse');

    await connection.acknowledgeProcessedData(12345);
    expect(transport.writes.length, 4);
    expect(transport.writes[3], equals(mirrorAcknowledgeProcessedData(3, 4, 12345)));

    final beforeF = emittedPages.length;
    final statusFuture = connection.getStorageStatus();
    await pumpEventQueue();
    expect(transport.writes.length, 5);
    expect(transport.writes[4], equals(mirrorGetDeviceStatus(4, 5)));
    transport.emit(limitlessRxCharUuid, packetsF[0]);
    final storageStatus = await statusFuture;
    await pumpEventQueue();
    expect(emittedPages.length, beforeF, reason: 'device-status packet must not emit a flash page');
    expect(storageStatus, isNotNull);
    expect(
      storageStatus,
      equals({
        'oldest_flash_page': 100,
        'newest_flash_page': 2500,
        'current_storage_session': 3,
        'free_capture_pages': 120000,
        'total_capture_pages': 170000,
      }),
    );
    expect(mirrorParseDeviceStatus(packetsF[0]), equals(storageStatus),
        reason: 'local device-status mirror must agree with the real _tryParseDeviceStatus path');

    await connection.disableBatchMode();
    expect(transport.writes.length, 6);
    expect(transport.writes[5], equals(mirrorDownloadFlashPages(5, 6, false, true)));

    await connection.setRealtimeAudioSuppressed(true);
    expect(transport.writes.length, 7);
    expect(transport.writes[6], equals(mirrorDownloadFlashPages(6, 7, false, false)));

    final cases = <String, Map<String, dynamic>>{
      'single_fragment_audio_page.json': caseFixture(
        'single_fragment_audio_page',
        packetsA,
        pagesA,
        mirrorStorageStateForPackets(packetsA),
      ),
      'three_fragments_out_of_order.json': caseFixture(
        'three_fragments_out_of_order',
        packetsB,
        pagesB,
        mirrorStorageStateForPackets(packetsB),
      ),
      'diagnostic_page_no_audio.json': caseFixture(
        'diagnostic_page_no_audio',
        packetsC,
        pagesC,
        mirrorStorageStateForPackets(packetsC),
      ),
      'nested_audio_containers.json': caseFixture(
        'nested_audio_containers',
        packetsD,
        pagesD,
        mirrorStorageStateForPackets(packetsD),
      ),
      'invalid_toc_interleaved.json': caseFixture(
        'invalid_toc_interleaved',
        packetsE,
        pagesE,
        mirrorStorageStateForPackets(packetsE),
      ),
      'device_status.json': caseFixture('device_status', packetsF, [], storageStatus),
      'truncated_trailing_field.json': caseFixture(
        'truncated_trailing_field',
        packetsG,
        pagesG,
        mirrorStorageStateForPackets(packetsG),
      ),
      'audio_page_zero_frames.json': caseFixture(
        'audio_page_zero_frames',
        packetsH,
        pagesH,
        mirrorStorageStateForPackets(packetsH),
      ),
      'overflow_varint_length.json': caseFixture(
        'overflow_varint_length',
        packetsI,
        pagesI,
        mirrorStorageStateForPackets(packetsI),
      ),
      'fixed64_fields_page.json': caseFixture(
        'fixed64_fields_page',
        packetsJ,
        pagesJ,
        mirrorStorageStateForPackets(packetsJ),
      ),
      'unknown_wiretype_page.json': caseFixture(
        'unknown_wiretype_page',
        packetsK,
        pagesK,
        mirrorStorageStateForPackets(packetsK),
      ),
    };

    for (final name in [
      'single_fragment_audio_page.json',
      'three_fragments_out_of_order.json',
      'diagnostic_page_no_audio.json',
      'nested_audio_containers.json',
      'invalid_toc_interleaved.json',
      'truncated_trailing_field.json',
      'audio_page_zero_frames.json',
      'overflow_varint_length.json',
      'fixed64_fields_page.json',
      'unknown_wiretype_page.json',
    ]) {
      expect(cases[name]!['expectedStorageState'], isNull,
          reason: '$name must not accidentally parse as a device-status packet');
    }

    for (final entry in cases.entries) {
      checkGolden(fixtures, entry.key, entry.value);
    }

    final encoderVectors = {
      'note': 'Byte-exact TX vectors observed from a fresh LimitlessDeviceConnection driving connect(), '
          'enableBatchMode(), acknowledgeProcessedData(12345), getStorageStatus(), disableBatchMode(), '
          'setRealtimeAudioSuppressed(true) in order. messageIndex starts at 0 and increments per write; '
          'requestId starts at 1 and increments per write. msg6 is pinned at a fixed timestamp after '
          'byte-verifying the mirror encoder against the live write.',
      'vectors': [
        {
          'name': 'msg6_set_current_time',
          'messageIndex': 0,
          'requestId': 1,
          'timestampMs': encoderTimestampMs,
          'hex': toHex(mirrorSetCurrentTime(0, 1, encoderTimestampMs)),
        },
        {
          'name': 'msg8_realtime_connect',
          'messageIndex': 1,
          'requestId': 2,
          'batchMode': false,
          'realTime': true,
          'hex': toHex(transport.writes[1]),
        },
        {
          'name': 'msg8_batch_on',
          'messageIndex': 2,
          'requestId': 3,
          'batchMode': true,
          'realTime': false,
          'hex': toHex(transport.writes[2]),
        },
        {
          'name': 'msg7_ack_12345',
          'messageIndex': 3,
          'requestId': 4,
          'upToIndex': 12345,
          'hex': toHex(transport.writes[3]),
        },
        {
          'name': 'msg21_get_device_status',
          'messageIndex': 4,
          'requestId': 5,
          'hex': toHex(transport.writes[4]),
        },
        {
          'name': 'msg8_realtime_batch_off',
          'messageIndex': 5,
          'requestId': 6,
          'batchMode': false,
          'realTime': true,
          'hex': toHex(transport.writes[5]),
        },
        {
          'name': 'msg8_record_to_flash',
          'messageIndex': 6,
          'requestId': 7,
          'batchMode': false,
          'realTime': false,
          'hex': toHex(transport.writes[6]),
        },
      ],
    };
    checkGolden(fixtures, 'encoders.json', encoderVectors);

    await pageSubscription.cancel();
    await connection.disconnect();
  }, timeout: const Timeout(Duration(minutes: 2)));
}
