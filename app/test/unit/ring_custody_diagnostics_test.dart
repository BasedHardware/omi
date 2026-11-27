import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/devices.dart' show DeviceConnectionState;
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/wals/ring_custody_diagnostics.dart';
import 'package:omi/services/wals/ring_custody_export.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';

class _ReadOnlyTransport implements DeviceTransport {
  final reads = <String>[];
  final bytes = (ByteData(4)..setUint32(0, 1967677294, Endian.little)).buffer.asUint8List();
  void Function()? afterRead;
  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    reads.add(characteristicUuid);
    afterRead?.call();
    return bytes;
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async =>
      fail('Export must never write a characteristic');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Connection implements DeviceConnection {
  @override
  final _ReadOnlyTransport transport = _ReadOnlyTransport();
  int epoch = 4;
  int statusReads = 0, infoReads = 0;
  @override
  DeviceConnectionState get status => DeviceConnectionState.connected;
  @override
  int get ringCustodyEpoch => epoch;
  @override
  bool get ringLivePersistEnabled => true;
  @override
  Future<RingStatus?> getRingStatus() async {
    statusReads++;
    return RingStatus(usedBytes: 4440, unreadPackets: 10, freeBytes: 100, rtcValid: 1);
  }

  @override
  Future<RingInfo?> getRingInfo() async {
    infoReads++;
    return RingInfo(readSeq: 20, writeSeq: 30, capacityPackets: 1000, droppedPackets: 99, packetSize: 444, ringId: 42);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  var now = DateTime.utc(2026, 11, 15, 12);
  late RingCustodyDiagnostics recorder;
  int phone() => now.millisecondsSinceEpoch ~/ 1000;
  List<int> record(int timestamp) => [
        ...(ByteData(4)..setUint32(0, timestamp, Endian.big)).buffer.asUint8List(),
        107,
        17,
        18,
        19,
        ...List.filled(436, 0xab),
      ];
  setUp(() {
    now = DateTime.utc(2026, 11, 15, 12);
    recorder = RingCustodyDiagnostics(now: () => now);
  });
  Map<String, Object?> build([String id = 'pendant']) => recorder.build(id, device: {'connection_epoch': 1});
  void observe(int ordinal, int ts) => recorder.record('pendant',
      epoch: 1, ringId: 42, ordinal: ordinal, record: record(ts), timestamp: ts, frames: 4, phoneSeconds: phone());

  test('buffers retain only 20 events, first 16 prefixes, latest 64 invalid records', () {
    recorder.beginRead('pendant', epoch: 1, ringId: 42, start: 10, records: 100);
    for (var i = 0; i < 100; i++) {
      recorder.event('pendant', RingDiagnosticEvent.advanceAttempt, end: i);
      observe(i + 10, 1967677294);
    }
    final section = build();
    expect((section['events'] as List).length, 20);
    final first = section['latest_read_first_records'] as List;
    final invalid = section['implausible_records_last_24h'] as List;
    expect(first.length, 16);
    expect(invalid.length, 64);
    expect(invalid.first['ordinal'], 46);
    expect(first.first['prefix_8_hex'], '75485f6e6b111213');
    expect((first.first['prefix_8_hex'] as String).length, 16);
    expect(first.first['next_plausible'], false);
    expect(invalid.last['next_plausible'], null);
    expect(jsonEncode(section), isNot(contains('abababab')));
  });
  test('ring activity and a successful retry preserve the last unconfirmed mute readback', () {
    recorder.event('pendant', RingDiagnosticEvent.captureMuteReadback,
        epoch: 1, requestedMuted: true, observedMuted: false, reason: RingDiagnosticReason.commandFailed);
    final mismatchAt = now.millisecondsSinceEpoch;
    now = now.add(const Duration(hours: 6));
    recorder.event('pendant', RingDiagnosticEvent.captureMuteReadback,
        epoch: 2, requestedMuted: true, observedMuted: true);
    for (var i = 0; i < RingCustodyDiagnostics.maxEvents; i++) {
      recorder.event('pendant', RingDiagnosticEvent.readBegin);
    }

    final section = build();
    expect((section['events'] as List).every((event) => event['event'] == 'readBegin'), isTrue);
    expect(section['capture_mute_readbacks'], {
      'last_unconfirmed': {
        'at_ms': mismatchAt,
        'event': 'captureMuteReadback',
        'reason': 'commandFailed',
        'connection_epoch': 1,
        'requested_muted': true,
        'observed_muted': false,
      },
      'last_confirmed': {
        'at_ms': now.millisecondsSinceEpoch,
        'event': 'captureMuteReadback',
        'reason': 'none',
        'connection_epoch': 2,
        'requested_muted': true,
        'observed_muted': true,
      },
    });
    expect(build('other-device')['capture_mute_readbacks'], isEmpty);
  });
  test('neighbours refer to adjacent records; a new read clears first samples only', () {
    recorder.beginRead('pendant', epoch: 1, ringId: 42, start: 0, records: 3);
    observe(0, phone());
    observe(1, 1967677294);
    observe(2, phone());
    final bad = (build()['implausible_records_last_24h'] as List).single;
    expect(bad['previous_plausible'], true);
    expect(bad['next_plausible'], true);
    recorder.beginRead('pendant', epoch: 1, ringId: 42, start: 20, records: 1);
    observe(20, phone());
    expect((build()['latest_read_first_records'] as List).single['previous_plausible'], null);
    expect((build()['implausible_records_last_24h'] as List).length, 1);
    now = now.add(const Duration(hours: 24, milliseconds: 1));
    expect(build()['implausible_records_last_24h'], isEmpty);
  });
  test('route counts expire and old device histories are evicted', () {
    recorder.route('pendant', RingCaptureRoute.ordinaryWal, frames: 12);
    recorder.route('pendant', RingCaptureRoute.mobileBatch, frames: 8, proofPublished: true);
    expect(build()['routes_last_hour'], {'ordinaryWal_frames': 12, 'mobileBatch_proof_frames': 8});
    now = now.add(const Duration(hours: 1));
    expect(build()['routes_last_hour'], isEmpty);
    for (var i = 0; i < 4; i++) {
      recorder.event('other$i', RingDiagnosticEvent.connection);
    }
    expect(build()['observed_since_ms'], null);
  });
  test('builder does not forward content or arbitrary log keys', () {
    final result = recorder.build('pendant', device: {
      'firmware': '3.0.24',
      'transcript': 'private',
      'filename': 'private',
      'audio': [1, 2],
      'title': 'private',
      'used': {'audio': 'private'},
    }, ledger: {
      'durable_frontier': 20,
      'wals': ['private'],
      'owner': 'private',
      'ring_id': {'title': 'private'},
    }, walStates: {
      'miss': 3,
      'private': 4
    });
    expect(jsonEncode(result), isNot(contains('private')));
    expect(result['ledger'], {'durable_frontier': 20});
    expect(result['wal_states'], {'miss': 3});
  });
  test('grant timestamp is scoped to the same connection', () {
    recorder.event('pendant', RingDiagnosticEvent.connection, epoch: 1);
    recorder.event('pendant', RingDiagnosticEvent.liveGrant, epoch: 1, granted: true);
    expect(build()['live_persistence_granted_at_ms'], now.millisecondsSinceEpoch);
    recorder.event('pendant', RingDiagnosticEvent.connection, epoch: 2);
    expect(build()['live_persistence_granted_at_ms'], null);
  });
  test('absent pendant is honest and has no invented device values', () async {
    final section = await exportRingCustody(
        deviceId: 'absent', firmware: null, connection: null, wals: null, recorder: recorder, now: () => now);
    expect((section['device'] as Map)['read_error'], 'absent_pendant');
    expect((section['device'] as Map)['rtc_raw_seconds'], null);
    expect(section['wal_states'], null);
    expect(section['events'], isEmpty);
  });
  test('connected export reads little-endian RTC and live ring without time writes', () async {
    final connection = _Connection();
    final section = await exportRingCustody(
        deviceId: 'pendant', firmware: '3.0.24', connection: connection, wals: [], recorder: recorder, now: () => now);
    final device = section['device'] as Map;
    expect(device['rtc_raw_seconds'], 1967677294);
    expect(device['rtc_valid'], 1);
    expect(device['read_seq'], 20);
    expect(device['write_seq'], 30);
    expect(device['dropped'], 99);
    expect(device['used'], 10);
    expect(connection.transport.reads, [timeSyncReadCharacteristicUuid]);
  });
  test('legacy firmware exports raw RTC but no ring query or fake validity bit', () async {
    final connection = _Connection();
    final section = await exportRingCustody(
        deviceId: 'pendant', firmware: '3.0.17', connection: connection, wals: [], recorder: recorder, now: () => now);
    expect((section['device'] as Map)['read_error'], 'legacy_firmware');
    expect((section['device'] as Map)['rtc_valid'], null);
    expect(connection.infoReads, 0);
    expect(connection.statusReads, 0);
  });
  test('a changed connection discards cross-epoch device readings', () async {
    final connection = _Connection();
    connection.transport.afterRead = () => connection.epoch++;
    final section = await exportRingCustody(
        deviceId: 'pendant', firmware: '3.0.24', connection: connection, wals: [], recorder: recorder, now: () => now);
    expect((section['device'] as Map)['read_error'], 'connection_changed');
    expect((section['device'] as Map).containsKey('rtc_raw_seconds'), false);
  });
  test('ledger getter computes union and first gap without validation, advance or content', () async {
    final dir = await Directory.systemTemp.createTemp('ring-diagnostic-ledger');
    addTearDown(() => dir.delete(recursive: true));
    var validations = 0, advances = 0;
    final custody = PendantRingCustody(
      store: PendantCustodyStore(directoryProvider: () async => dir),
      walValidator: (_) async {
        validations++;
        return true;
      },
    );
    await custody.beginConnection(
        'pendant',
        1,
        RingInfo(
            readSeq: 20,
            writeSeq: 40,
            capacityPackets: 100,
            droppedPackets: 0,
            packetSize: 444,
            ringId: 42,
            advertisedCaps: 15,
            contractVersion: 1,
            infoBytes: 41), onAdvanceReady: (_) async {
      advances++;
      return 0;
    });
    // Claims need nonempty scoped references; the getter must still perform
    // no validation or file I/O. Actual custody is tested independently.
    List<CustodyWalRef> proof(int start, int end) => [
          CustodyWalRef(
              fileName: 'fixture.bin',
              bytes: 2,
              frames: 1,
              ownerUid: 'owner',
              downloadDeviceId: 'pendant',
              downloadRingId: 42,
              downloadSeqStart: start,
              downloadSeqEnd: end),
        ];
    await custody.recordDurableRingRange('pendant', 1, 42, 20, 25, proof(20, 25));
    await custody.recordDurableRingRange('pendant', 1, 42, 30, 35, proof(30, 35));
    await custody.recordDurableRingRange('pendant', 1, 42, 21, 24, proof(21, 24));
    final before = custody.durableFrontierFor('pendant', 1);
    final mark = custody.diagnosticMarkStateByDevice['pendant']!;
    expect(mark.keys.toSet(),
        {'ring_id', 'evidence_broken', 'incarnation_invalid', 'last_observed_mark_seq', 'last_observed_mark_index'});
    expect(mark['ring_id'], 42);
    expect(() => mark['ring_id'] = 999, throwsUnsupportedError);
    final ledger = custody.diagnosticsByDevice['pendant']!;
    expect(ledger['proof_record_span'], 10);
    expect(ledger['durable_frontier'], 25);
    expect(ledger['first_unproven_start'], 25);
    expect(ledger['first_unproven_length'], 5);
    expect(ledger['records_held_behind_gap'], 10);
    expect(validations, 0);
    expect(advances, 0);
    expect(custody.durableFrontierFor('pendant', 1), before);
    expect(() => ledger['durable_frontier'] = 999, throwsUnsupportedError);
    expect(jsonEncode(ledger), isNot(contains('file')));
  });
}
