// #20500: custody checkpoint writes that a caller cannot await (mismatch
// invalidation, ring reincarnation) used to outlive the test that queued them.
// The `.json.tmp` -> rename then ran after teardown deleted the directory and
// failed the suite "after it has completed". `flush()` is the one completion a
// caller can wait on before tearing storage down.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';

const _ringId = 0x1122334455667788;

RingInfo _ringInfo({int ringId = _ringId, int readSeq = 0, int writeSeq = 64}) => RingInfo(
      readSeq: readSeq,
      writeSeq: writeSeq,
      capacityPackets: 1024,
      droppedPackets: 0,
      packetSize: 444,
      advertisedCaps: 0x0F,
      contractVersion: 1,
      ringId: ringId,
      infoBytes: 41,
    );

LiveMarkNotification _liveMark(int ringSeq, int liveIndex) {
  final bd = ByteData(19);
  bd.setUint8(0, RingProtocol.notifyLiveMark);
  bd.setUint64(1, _ringId, Endian.big);
  bd.setUint64(9, ringSeq, Endian.big);
  bd.setUint16(17, liveIndex, Endian.big);
  return RingProtocol.parseLiveMarkNotification(bd.buffer.asUint8List())!;
}

/// A store whose directory lookups block until [open] is called, so a queued
/// write is provably still pending — no sleeps, no scheduling luck.
class _GatedDirectory {
  _GatedDirectory(this.dir);

  final Directory dir;
  Completer<void> _gate = Completer<void>()..complete();

  void close() => _gate = Completer<void>();

  void open() {
    if (!_gate.isCompleted) _gate.complete();
  }

  Future<Directory> call() async {
    await _gate.future;
    return dir;
  }
}

Future<bool> _completesWithoutWaiting(Future<void> future) async {
  var done = false;
  unawaited(future.then((_) => done = true));
  // Let every microtask and short timer that does not depend on the gate run.
  await Future<void>.delayed(const Duration(milliseconds: 20));
  return done;
}

void main() {
  late Directory tmp;
  late _GatedDirectory gated;
  late PendantCustodyStore store;
  late PendantRingCustody custody;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('custody_flush_test');
    gated = _GatedDirectory(tmp);
    store = PendantCustodyStore(directoryProvider: gated.call);
    custody = PendantRingCustody(store: store, walValidator: (_) async => true);
    await custody.beginConnection('omi-1', 1, _ringInfo());
    await custody.recordDurableRingRange('omi-1', 1, _ringId, 0, 10, const [
      CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
    ]);
  });

  tearDown(() async {
    gated.open();
    await custody.flush();
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  File checkpointFile() => File('${tmp.path}/custody_omi-1.json');

  /// The checkpoint as it is on disk right now, read synchronously so no queued
  /// store work can run first.
  Map<String, dynamic> checkpointOnDisk() => jsonDecode(checkpointFile().readAsStringSync()) as Map<String, dynamic>;
  int? ringIdOnDisk() => checkpointOnDisk()['ring_id'] as int?;

  test('flush waits for a fire-and-forget reincarnation write', () async {
    gated.close();
    // A new ring id resets the checkpoint and persists it without awaiting.
    custody.noteInfo('omi-1', 1, _ringInfo(ringId: 0x99));

    final flushed = custody.flush();
    expect(await _completesWithoutWaiting(flushed), isFalse,
        reason: 'flush must not complete while a queued custody write is still pending');

    gated.open();
    await flushed;
    expect(ringIdOnDisk(), 0x99);
    expect(File('${checkpointFile().path}.tmp').existsSync(), isFalse);
  });

  test('flush waits for a fire-and-forget mismatch-invalidation write', () async {
    gated.close();
    custody.noteMismatch('omi-1', 1);

    final flushed = custody.flush();
    expect(await _completesWithoutWaiting(flushed), isFalse);

    gated.open();
    await flushed;
    expect(checkpointOnDisk()['durable_seq'], 0, reason: 'the invalidated frontier is what reached disk');
  });

  test('flush also waits for a write queued while it was already waiting', () async {
    gated.close();
    custody.noteMismatch('omi-1', 1);
    final flushed = custody.flush();
    await Future<void>.delayed(Duration.zero);
    custody.noteInfo('omi-1', 1, _ringInfo(ringId: 0x77));

    expect(await _completesWithoutWaiting(flushed), isFalse);
    gated.open();
    await flushed;

    expect(ringIdOnDisk(), 0x77, reason: 'the later write must land before flush completes');
  });

  test('flush also waits for a checkpoint queued while it waits on the store', () async {
    gated.close();
    // Occupy the I/O queue so flush gets past the idle checkpoint queue and waits on the store.
    unawaited(store.load('omi-1'));
    final flushed = custody.flush();
    await Future<void>.delayed(Duration.zero);
    custody.noteMismatch('omi-1', 1);
    // Queued behind the mismatch write's checkpoint save, so it reaches the I/O queue last.
    custody.noteInfo('omi-1', 1, _ringInfo(ringId: 0x99));
    gated.open();
    await flushed;

    expect(ringIdOnDisk(), 0x99, reason: 'the last queued checkpoint must be on disk when flush completes');
    expect(File('${checkpointFile().path}.tmp').existsSync(), isFalse);
  });

  test('flush waits for live-mark checkpoint writes still queued on an open session', () async {
    custody.setLivePersistEnabled('omi-1', 1, true);
    var frame = 0;
    for (var record = 1; record <= 50; record++) {
      for (var i = 0; i < 20; i++) {
        custody.observeLiveFrame('omi-1', 1, (frame++) & 0xFFFF, 0);
      }
      custody.observeLiveMark('omi-1', 1, _liveMark(record, (record * 20) & 0xFFFF));
    }

    await custody.flush();
    await tmp.delete(recursive: true);
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(tmp.existsSync(), isFalse, reason: 'a live-mark write queued before flush recreated the deleted storage');
  });

  test('store flush waits for I/O queued while it was already waiting', () async {
    gated.close();
    unawaited(store.load('omi-1'));
    final flushed = store.flush();
    await Future<void>.delayed(Duration.zero);
    unawaited(store.saveJson('omi-1', RingCustodyCheckpoint(deviceId: 'omi-1', ringId: 0x42).toJson()));
    gated.open();
    await flushed;

    expect(ringIdOnDisk(), 0x42, reason: 'a write queued during the wait must land before the store flush completes');
  });

  test('flush completes immediately when nothing is queued', () async {
    expect(await _completesWithoutWaiting(custody.flush()), isTrue);
    expect(await _completesWithoutWaiting(store.flush()), isTrue);
  });

  test('a teardown that flushes never leaves a custody write to outlive its directory', () async {
    gated.close();
    custody.noteInfo('omi-1', 1, _ringInfo(ringId: 0x55));
    gated.open();
    // What every custody test teardown now does before deleting storage. noteInfo logs and
    // swallows a failed write, so the proof is what reached disk before the directory goes.
    await custody.flush();

    expect(ringIdOnDisk(), 0x55);
    expect(File('${checkpointFile().path}.tmp').existsSync(), isFalse);
    await tmp.delete(recursive: true);
  });
}
