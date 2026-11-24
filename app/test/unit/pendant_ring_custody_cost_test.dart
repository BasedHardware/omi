import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';

// Field report, firmware 3.0.24, phone holding ~16,000 recordings: every proof
// check reloaded the whole recording index once per referenced file, and proofs
// were never dropped after the pendant released them. A ring chunk took 8 s to
// credit at the start of a pass and 150 s half an hour in.

RingInfo _info({int readSeq = 0, int writeSeq = 100000, int ringId = 42}) => RingInfo(
      readSeq: readSeq,
      writeSeq: writeSeq,
      capacityPackets: 1 << 20,
      droppedPackets: 0,
      packetSize: 444,
      advertisedCaps: 0x0F,
      contractVersion: 1,
      ringId: ringId,
      infoBytes: 41,
    );

LiveMarkNotification _mark(int ringSeq, int liveIndex, {int ringId = 42}) {
  final bd = ByteData(19);
  bd.setUint8(0, RingProtocol.notifyLiveMark);
  bd.setUint64(1, ringId, Endian.big);
  bd.setUint64(9, ringSeq, Endian.big);
  bd.setUint16(17, liveIndex, Endian.big);
  return RingProtocol.parseLiveMarkNotification(bd.buffer.asUint8List())!;
}

void main() {
  late Directory tmp;
  final custodies = <PendantRingCustody>[];
  int indexLoads = 0;
  int fileChecks = 0;
  final missing = <String>{};

  PendantRingCustody counted() {
    final c = PendantRingCustody(
      store: PendantCustodyStore(directoryProvider: () async => tmp),
      walValidatorSnapshot: () async {
        indexLoads++;
        return (ref) async {
          fileChecks++;
          return !missing.contains(ref.fileName);
        };
      },
    );
    custodies.add(c);
    return c;
  }

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('custody_cost_test');
    indexLoads = 0;
    fileChecks = 0;
    missing.clear();
  });

  tearDown(() async {
    for (final c in custodies) {
      await c.flush();
    }
    custodies.clear();
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  CustodyWalRef chunk(int i) => CustodyWalRef(fileName: 'chunk_$i.bin', bytes: 100, frames: 60);

  Future<void> addChunk(PendantRingCustody c, int i) =>
      c.recordDurableRingRange('dev', 1, 42, i * 600, (i + 1) * 600, [chunk(i)]);

  test('one advance check reads the recording index once, however many proofs it covers', () async {
    final c = counted();
    await c.beginConnection('dev', 1, _info());
    for (var i = 0; i < 50; i++) {
      await addChunk(c, i);
    }
    indexLoads = 0;
    fileChecks = 0;

    expect(await c.validatedAdvanceTarget('dev', 1, 42), 50 * 600);

    expect(indexLoads, 1, reason: 'the index is read once per check, not once per referenced file');
    expect(fileChecks, 50);
  });

  test('proofs the pendant has released are not checked again', () async {
    final c = counted();
    await c.beginConnection('dev', 1, _info());
    for (var i = 0; i < 30; i++) {
      await addChunk(c, i);
      final target = await c.validatedAdvanceTarget('dev', 1, 42);
      expect(target, (i + 1) * 600);
      await c.markAdvanced('dev', 1, target!);
    }

    // One reference per chunk in total. Re-checking every earlier chunk on each
    // new one, as before, would be 30 * 31 / 2 = 465.
    expect(fileChecks, 30);
    expect(indexLoads, 30);
    expect(c.advanceTarget('dev', 1), isNull);
  });

  test('an acknowledged advance drops spent proofs from the saved checkpoint', () async {
    final c = counted();
    await c.beginConnection('dev', 1, _info());
    for (var i = 0; i < 20; i++) {
      await addChunk(c, i);
    }
    await c.markAdvanced('dev', 1, 19 * 600);
    await c.flush();

    final saved = jsonDecode(await File('${tmp.path}/custody_dev.json').readAsString()) as Map<String, dynamic>;
    expect((saved['ring_ranges'] as List).length, 1, reason: 'only the range above the released point remains');
    expect(saved['reported_read_seq'], 19 * 600);
    expect(saved['last_advanced_seq'], 19 * 600);

    // A later connection loads it, still owes the last chunk, and replays nothing below the read pointer.
    c.endConnection('dev', 1);
    final c2 = counted();
    final replayed = <int>[];
    await c2.beginConnection(
      'dev',
      2,
      _info(readSeq: 19 * 600),
      replayAdvance: (seq) async {
        replayed.add(seq);
        return RingProtocol.ackOk;
      },
    );
    expect(replayed, [20 * 600]);
  });

  test('a missing recording still stops the advance at the last proven record', () async {
    final c = counted();
    await c.beginConnection('dev', 1, _info());
    for (var i = 0; i < 5; i++) {
      await addChunk(c, i);
    }
    missing.add('chunk_3.bin');

    expect(await c.validatedAdvanceTarget('dev', 1, 42), isNull, reason: 'a failed proof never advances');
    // The broken range is discarded; the frontier falls back to what is still provable.
    expect(await c.validatedAdvanceTarget('dev', 1, 42), 3 * 600);
  });

  group('live ranges', () {
    Future<PendantRingCustody> proven() async {
      final c = counted();
      await c.beginConnection('dev', 1, _info());
      c.setLivePersistEnabled('dev', 1, true);
      c.observeLiveMark('dev', 1, _mark(0, 0));
      for (var batch = 1; batch <= 4; batch++) {
        for (var n = (batch - 1) * 60; n < batch * 60; n++) {
          c.observeLiveFrame('dev', 1, n, 0);
        }
        c.observeLiveMark('dev', 1, _mark(batch * 30, batch * 60));
      }
      await c.recordDurableLiveFrames(
        'dev',
        1,
        0,
        240,
        const CustodyWalRef(fileName: 'live.bin', bytes: 10, frames: 240, liveRingId: 42),
      );
      indexLoads = 0;
      fileChecks = 0;
      return c;
    }

    test('one ring read reuses its index while rechecking every duplicate skip', () async {
      final c = await proven();
      final memo = CustodyProofMemo();
      for (var seq = 0; seq < 30; seq++) {
        expect(await c.isDurableLiveRecord('dev', 42, seq, memo: memo), isTrue);
      }
      expect(indexLoads, 1);
      expect(fileChecks, 30, reason: 'each suppression revalidates current bytes; positive results are not cached');

      // A different range in the same read reuses the index and adds one file check.
      expect(await c.isDurableLiveRecord('dev', 42, 45, memo: memo), isTrue);
      expect(indexLoads, 1);
      expect(fileChecks, 31);

      // Without a memo every call stands alone, as before.
      expect(await c.isDurableLiveRecord('dev', 42, 5), isTrue);
      expect(indexLoads, 2);
    });

    test('a read memo never retains a positive recording check', () async {
      final c = await proven();
      final memo = CustodyProofMemo();
      expect(await c.isDurableLiveRecord('dev', 42, 5, memo: memo), isTrue);
      missing.add('live.bin');
      expect(await c.isDurableLiveRecord('dev', 42, 6, memo: memo), isFalse);
      expect(indexLoads, 1);
      expect(fileChecks, 2);
    });

    test('a read already in flight still drops records the pendant has just released', () async {
      final c = await proven();
      await c.markAdvanced('dev', 1, 120);

      expect(await c.isDurableLiveRecord('dev', 42, 100), isTrue, reason: 'released but still held by the phone');

      // Never dedupe against a recording that is gone: keep both copies.
      missing.add('live.bin');
      expect(await c.isDurableLiveRecord('dev', 42, 100), isFalse);
    });

    test('the unread ring is a live tail only from the first mark and while a mark covers the write head', () async {
      final c = await proven(); // marks at ring seq 0, 30, 60, 90 and 120

      expect(c.liveProofStartSeq('dev', 1), 0);
      expect(c.liveMarksReach('dev', 1, 120), isTrue);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 90, writeSeq: 120)), isTrue);
      // The pendant marks every commit of an unbroken live run at the committed
      // write position. One committed record beyond the last mark is therefore
      // a record the phone was not sent; with any slack here, a short unsent
      // stretch followed by silence would never be read.
      expect(c.liveMarksReach('dev', 1, 121), isFalse);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 90, writeSeq: 121)), isFalse);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 120, writeSeq: 156)), isFalse);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 90, writeSeq: 120, ringId: 7)), isFalse);

      // A broken live proof (here: a packet counter gap) can vouch for nothing.
      c.observeLiveFrame('dev', 1, 999, 0);
      expect(c.liveProofStartSeq('dev', 1), isNull);
      expect(c.liveMarksReach('dev', 1, 120), isFalse);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 90, writeSeq: 120)), isFalse);
    });

    test('records below the first mark cannot be proven live, so they are not a live tail', () async {
      // A range is proven between two marks. The batch written before the first
      // mark of a connection has no mark below it; leaving it to the live proof
      // would pin the pendant's read pointer there for the whole connection.
      final c = counted();
      await c.beginConnection('dev', 1, _info(readSeq: 100, writeSeq: 136));
      c.setLivePersistEnabled('dev', 1, true);
      for (var n = 0; n < 60; n++) {
        c.observeLiveFrame('dev', 1, n, 0);
      }
      c.observeLiveMark('dev', 1, _mark(136, 60));
      for (var n = 60; n < 120; n++) {
        c.observeLiveFrame('dev', 1, n, 0);
      }
      c.observeLiveMark('dev', 1, _mark(172, 120));

      expect(c.liveProofStartSeq('dev', 1), 136);
      expect(c.liveMarksReach('dev', 1, 172), isTrue);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 100, writeSeq: 172)), isFalse);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 136, writeSeq: 172)), isTrue);
    });

    test('a connection that has not opted in to live persist has no live tail', () async {
      final c = counted();
      await c.beginConnection('dev', 1, _info());
      expect(c.liveProofStartSeq('dev', 1), isNull);
      expect(c.liveRunCoversUnread('dev', 1, _info(readSeq: 0, writeSeq: 10)), isFalse);
    });

    test('a new connection starts with no live proof of its own', () async {
      final c = await proven();
      c.endConnection('dev', 1);
      await c.beginConnection('dev', 2, _info(readSeq: 90, writeSeq: 120));
      c.setLivePersistEnabled('dev', 2, true);
      expect(c.liveProofStartSeq('dev', 2), isNull);
      expect(c.liveRunCoversUnread('dev', 2, _info(readSeq: 90, writeSeq: 120)), isFalse);
    });
  });
}
