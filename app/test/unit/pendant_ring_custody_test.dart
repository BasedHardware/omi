import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';

Uint8List infoPayload({
  int readSeq = 0,
  int writeSeq = 0,
  int capacity = 100,
  int dropped = 0,
  int packetSize = 444,
  int? caps,
  int? contractVersion,
  int? ringId,
}) {
  final extra = (caps != null ? 1 : 0) + (contractVersion != null ? 1 : 0) + (ringId != null ? 8 : 0);
  final bd = ByteData(31 + extra);
  bd.setUint8(0, RingProtocol.notifyInfo);
  bd.setUint64(1, readSeq, Endian.big);
  bd.setUint64(9, writeSeq, Endian.big);
  bd.setUint32(17, capacity, Endian.big);
  bd.setUint64(21, dropped, Endian.big);
  bd.setUint16(29, packetSize, Endian.big);
  if (caps != null) bd.setUint8(31, caps);
  if (contractVersion != null) bd.setUint8(32, contractVersion);
  if (ringId != null) bd.setUint64(33, ringId, Endian.big);
  return bd.buffer.asUint8List();
}

Uint8List liveMark(int ringId, int ringSeq, int liveIndex) {
  final bd = ByteData(19);
  bd.setUint8(0, RingProtocol.notifyLiveMark);
  bd.setUint64(1, ringId, Endian.big);
  bd.setUint64(9, ringSeq, Endian.big);
  bd.setUint16(17, liveIndex, Endian.big);
  return bd.buffer.asUint8List();
}

RingInfo v1Info({int readSeq = 0, int writeSeq = 20, int caps = 0x0F, int ringId = 7}) =>
    RingProtocol.parseInfoNotification(
      infoPayload(readSeq: readSeq, writeSeq: writeSeq, caps: caps, contractVersion: 1, ringId: ringId),
    )!;

void main() {
  group('RingProtocol INFO capability extension', () {
    test('31-byte legacy payload parses with zero effective caps', () {
      final info = RingProtocol.parseInfoNotification(infoPayload(readSeq: 3, writeSeq: 9));
      expect(info, isNotNull);
      expect(info!.readSeq, 3);
      expect(info.writeSeq, 9);
      expect(info.advertisedCaps, 0);
      expect(info.contractVersion, 0);
      expect(info.ringId, isNull);
      expect(info.effectiveCaps, 0);
    });

    test('33-byte payload (caps+version, no ring id) yields zero effective caps', () {
      final info = RingProtocol.parseInfoNotification(infoPayload(caps: 0x0F, contractVersion: 1));
      expect(info, isNotNull);
      expect(info!.advertisedCaps, 0x0F);
      expect(info.contractVersion, 1);
      expect(info.ringId, isNull);
      expect(info.effectiveCaps, 0);
    });

    test('40-byte truncated payload yields zero effective caps', () {
      final full = infoPayload(caps: 0x0F, contractVersion: 1, ringId: 5);
      final truncated = full.sublist(0, 40);
      final info = RingProtocol.parseInfoNotification(truncated);
      expect(info, isNotNull);
      expect(info!.effectiveCaps, 0);
      expect(info.ringId, isNull);
    });

    test('41-byte v1 payload exposes all four capability bits', () {
      final info = v1Info();
      expect(info.effectiveCaps, 0x0F);
      expect(info.capAppAckReclaim, isTrue);
      expect(info.capLivePersist, isTrue);
      expect(info.capAdvanceIdempotent, isTrue);
      expect(info.capRingId, isTrue);
      expect(info.ringId, 7);
    });

    test('reserved bits are masked out of effective caps but visible raw', () {
      final info = v1Info(caps: 0xFF);
      expect(info.advertisedCaps, 0xFF);
      expect(info.effectiveCaps, 0x0F);
    });

    test('unknown contract version yields zero effective caps', () {
      final info = RingProtocol.parseInfoNotification(infoPayload(caps: 0x0F, contractVersion: 2, ringId: 5));
      expect(info!.effectiveCaps, 0);
    });

    test('zero ring id is invalid and yields zero effective caps', () {
      final info = v1Info(ringId: 0);
      expect(info.ringId, 0);
      expect(info.effectiveCaps, 0);
    });

    test('high-bit ring ids parse with the full 64-bit bit pattern intact', () {
      const ringId = 0x8000000000000001 | 0; // high bit set: wraps negative on VM
      final bd = ByteData(8)..setUint64(0, ringId, Endian.big);
      final info = RingProtocol.parseInfoNotification(
        infoPayload(caps: 0x0F, contractVersion: 1, ringId: bd.getUint64(0, Endian.big)),
      );
      expect(info!.ringId, equals(ringId));
      expect(info.capRingId, isTrue);
    });
  });

  group('RingProtocol custody commands and marks', () {
    test('CUSTODY_ENABLE encodes [0x14, version=1, requested caps]', () {
      final cmd = RingProtocol.encodeCustodyEnableCommand(0x0F);
      expect(cmd, [0x14, 0x01, 0x0F]);
    });

    test('ADVANCE_ID encodes opcode, u64 ring id and u64 seq', () {
      const ringId = -1; // all bits set — full 64-bit pattern
      final cmd = RingProtocol.encodeAdvanceIdCommand(ringId, 42);
      expect(cmd.length, 17);
      expect(cmd[0], 0x15);
      final bd = ByteData.sublistView(cmd);
      expect(bd.getUint64(1, Endian.big), equals(ringId));
      expect(bd.getUint64(9, Endian.big), 42);
    });

    test('live mark parses [ring_id, ring_seq, live_index]', () {
      final mark = RingProtocol.parseLiveMarkNotification(liveMark(9, 100, 512));
      expect(mark, isNotNull);
      expect(mark!.ringId, 9);
      expect(mark.ringSeq, 100);
      expect(mark.liveIndex, 512);
    });

    test('truncated or wrong-opcode marks return null', () {
      expect(RingProtocol.parseLiveMarkNotification(liveMark(9, 1, 1).sublist(0, 18)), isNull);
      expect(RingProtocol.parseLiveMarkNotification([0x05, ...List.filled(18, 0)]), isNull);
    });
  });

  group('LivePacketOrdinals', () {
    test('sequential counters allocate sequential ordinals', () {
      final o = LivePacketOrdinals();
      expect(o.observe(10, 0), 0);
      expect(o.observe(11, 0), 1);
      expect(o.observe(12, 0), 2);
      expect(o.isBroken, isFalse);
    });

    test('u16 wrap 65535 -> 0 is accepted', () {
      final o = LivePacketOrdinals();
      expect(o.observe(0xFFFF, 0), 0);
      expect(o.observe(0x0000, 0), 1);
      expect(o.isBroken, isFalse);
    });

    test('ordinals map marks across more than two u16 wraps', () {
      final ord = LivePacketOrdinals();
      for (var i = 0; i < 2 * 65536 + 10; i++) {
        expect(ord.observe(i & 0xFFFF, 0), i);
      }
      expect(ord.ordinalBoundaryFor(8), 2 * 65536 + 8);
    });

    test('a gap fails closed and stays broken', () {
      final o = LivePacketOrdinals();
      o.observe(5, 0);
      expect(o.observe(7, 0), isNull);
      expect(o.isBroken, isTrue);
      expect(o.observe(8, 0), isNull);
    });

    test('duplicates and reverse counters fail closed', () {
      final o = LivePacketOrdinals();
      o.observe(5, 0);
      expect(o.observe(5, 0), isNull); // duplicate
      final r = LivePacketOrdinals();
      r.observe(5, 0);
      expect(r.observe(4, 0), isNull); // reverse
    });

    test('nonzero fragment evidence fails closed', () {
      final o = LivePacketOrdinals();
      o.observe(5, 0);
      expect(o.observe(6, 1), isNull);
      expect(o.isBroken, isTrue);
    });
  });

  group('PendantRingCustody', () {
    late Directory tmp;
    late PendantRingCustody custody;
    // Every custody a test creates; tearDown flushes them before deleting storage (#20500).
    final custodies = <PendantRingCustody>[];
    PendantRingCustody tracked(PendantRingCustody c) {
      custodies.add(c);
      return c;
    }

    RingInfo info({int readSeq = 0, int writeSeq = 50, int ringId = 42}) =>
        v1Info(readSeq: readSeq, writeSeq: writeSeq, ringId: ringId);

    setUp(() async {
      tmp = await Directory.systemTemp.createTemp('custody_test');
      custody = tracked(PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => tmp),
        walValidator: (_) async => true,
      ));
    });

    tearDown(() async {
      for (final c in custodies) {
        await c.flush();
      }
      custodies.clear();
      for (var i = 0; i < 10; i++) {
        try {
          if (await tmp.exists()) await tmp.delete(recursive: true);
          return;
        } on FileSystemException {
          await Future<void>.delayed(const Duration(milliseconds: 20));
        }
      }
    });

    test('reconnect with the same ring id replays the durable frontier before read', () async {
      await custody.beginConnection('dev', 1, info());
      await custody.recordDurableRingRange('dev', 1, 42, 0, 10, [
        const CustodyWalRef(fileName: 'a.bin', bytes: 100, frames: 10),
      ]);
      custody.endConnection('dev', 1);

      final replayed = <int>[];
      await custody.beginConnection(
        'dev',
        2,
        info(),
        replayAdvance: (seq) async {
          replayed.add(seq);
          return 0;
        },
      );
      expect(replayed, [10]);
    });

    test('a changed ring id discards the stale checkpoint — zero replay', () async {
      await custody.beginConnection('dev', 1, info(ringId: 42));
      await custody.recordDurableRingRange('dev', 1, 42, 0, 10, [
        const CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
      ]);
      custody.endConnection('dev', 1);

      var replayed = false;
      await custody.beginConnection(
        'dev',
        2,
        info(ringId: 77),
        replayAdvance: (seq) async {
          replayed = true;
          return 0;
        },
      );
      expect(replayed, isFalse);
    });

    test('checkpoint survives a store reload for the same incarnation', () async {
      final store = PendantCustodyStore(directoryProvider: () async => tmp);
      final c1 = tracked(PendantRingCustody(store: store, walValidator: (_) async => true));
      await c1.beginConnection('dev', 1, info());
      await c1.recordDurableRingRange('dev', 1, 42, 0, 12, [
        const CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
      ]);

      final c2 = tracked(PendantRingCustody(store: store, walValidator: (_) async => true));
      final replayed = <int>[];
      await c2.beginConnection(
        'dev',
        9,
        info(),
        replayAdvance: (seq) async {
          replayed.add(seq);
          return 0;
        },
      );
      expect(replayed, [12]);
    });

    test('two marks plus durable packets prove a live range; first mark alone proves nothing', () async {
      await custody.beginConnection('dev', 1, info());
      custody.setLivePersistEnabled('dev', 1, true);

      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 10, 0))!);
      expect(await custody.isDurableLiveRecord('dev', 42, 5), isFalse);
      expect(custody.advanceTarget('dev', 1), isNull);

      for (var c = 0; c < 100; c++) {
        expect(custody.observeLiveFrame('dev', 1, c, 0), isNotNull);
      }
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 20, 100))!);
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        0,
        100,
        const CustodyWalRef(fileName: 'w.bin', bytes: 10, frames: 10, liveRingId: 42),
      );

      expect(await custody.isDurableLiveRecord('dev', 42, 15), isTrue);
      expect(await custody.isDurableLiveRecord('dev', 42, 20), isFalse);
      expect(custody.advanceTarget('dev', 1), isNull); // [0,10) still unproven
      await custody.recordDurableRingRange('dev', 1, 42, 0, 10, [
        const CustodyWalRef(fileName: 'r.bin', bytes: 1, frames: 1),
      ]);
      expect(custody.advanceTarget('dev', 1), 20);
    });

    test('a packet gap fails closed: no live range is proven', () async {
      await custody.beginConnection('dev', 1, info());
      custody.setLivePersistEnabled('dev', 1, true);
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 10, 0))!);
      for (var c = 0; c < 50; c++) {
        custody.observeLiveFrame('dev', 1, c, 0);
      }
      custody.observeLiveFrame('dev', 1, 51, 0); // gap at 50
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 20, 60))!);
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        0,
        60,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );
      await custody.recordDurableRingRange('dev', 1, 42, 0, 10, [
        const CustodyWalRef(fileName: 'r.bin', bytes: 1, frames: 1),
      ]);
      expect(custody.advanceTarget('dev', 1), 10); // ring-read range only; live range not proven
      expect(await custody.isDurableLiveRecord('dev', 42, 15), isFalse);
    });

    test('a mark from another ring incarnation breaks evidence', () async {
      await custody.beginConnection('dev', 1, info(ringId: 42));
      custody.setLivePersistEnabled('dev', 1, true);
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(999, 5, 0))!);
      for (var c = 0; c < 10; c++) {
        custody.observeLiveFrame('dev', 1, c, 0);
      }
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 8, 10))!);
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        0,
        10,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );
      expect(await custody.isDurableLiveRecord('dev', 42, 6), isFalse);
    });

    test('live frames observed while not enabled carry no evidence', () {
      expect(custody.observeLiveFrame('dev', 1, 0, 0), isNull);
    });

    test('advance target never exceeds the INFO write_seq', () async {
      await custody.beginConnection('dev', 1, info(writeSeq: 15));
      await custody.recordDurableRingRange('dev', 1, 42, 0, 30, [
        const CustodyWalRef(fileName: 'a.bin', bytes: 1, frames: 1),
      ]);
      expect(custody.advanceTarget('dev', 1), 15);
    });

    test('a deleted proof WAL blocks validatedAdvanceTarget — no release of the stale range', () async {
      final live = <String>{'r.bin', 'w.bin'};
      final c = tracked(PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => tmp),
        walValidator: (ref) async => live.contains(ref.fileName),
      ));
      await c.beginConnection('dev', 1, info());
      c.setLivePersistEnabled('dev', 1, true);
      await c.recordDurableRingRange('dev', 1, 42, 0, 5, [const CustodyWalRef(fileName: 'r.bin', bytes: 1, frames: 1)]);
      for (var f = 0; f < 10; f++) {
        c.observeLiveFrame('dev', 1, f, 0);
      }
      c.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 5, 0))!);
      c.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 6, 9))!);
      await c.recordDurableLiveFrames(
        'dev',
        1,
        0,
        10,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );

      expect(await c.validatedAdvanceTarget('dev', 1, 42), 6);

      live.remove('w.bin');
      expect(
        await c.validatedAdvanceTarget('dev', 1, 42),
        isNull,
        reason: 'a missing proof file invalidates its range and refuses the advance this round',
      );
      expect(
        await c.validatedAdvanceTarget('dev', 1, 42),
        5,
        reason: 'the repaired frontier covers only the durable ring prefix — never past it',
      );
      expect(await c.isDurableLiveRecord('dev', 42, 5), isFalse);
    });

    test('validatedAdvanceTarget never extends past the target it validated', () async {
      final gate = Completer<void>();
      final live = <String>{'r.bin'};
      final c = tracked(PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => tmp),
        walValidator: (ref) async {
          await gate.future;
          return live.contains(ref.fileName);
        },
      ));
      await c.beginConnection('dev', 1, info());
      await c.recordDurableRingRange('dev', 1, 42, 0, 5, [const CustodyWalRef(fileName: 'r.bin', bytes: 1, frames: 1)]);

      final first = c.validatedAdvanceTarget('dev', 1, 42);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      // A new proof for (5,10] lands while validation is still in flight; its
      // WAL does not exist on disk, so it can never be part of this release.
      await c.recordDurableRingRange('dev', 1, 42, 5, 10, [
        const CustodyWalRef(fileName: 'b.bin', bytes: 1, frames: 1),
      ]);
      gate.complete();

      expect(await first, 5, reason: 'release is capped at the validated target, never extended');
      expect(
        await c.validatedAdvanceTarget('dev', 1, 42),
        isNull,
        reason: 'the missing WAL invalidates its range and refuses this round',
      );
      expect(
        await c.validatedAdvanceTarget('dev', 1, 42),
        5,
        reason: 'the repaired frontier covers only the still-provable prefix',
      );
    });

    test('isDurableLiveRecord returns false when the incarnation changes during validation', () async {
      final gate = Completer<void>();
      final c = tracked(PendantRingCustody(
        store: PendantCustodyStore(directoryProvider: () async => tmp),
        walValidator: (ref) async {
          await gate.future;
          return true;
        },
      ));
      await c.beginConnection('dev', 1, info());
      c.setLivePersistEnabled('dev', 1, true);
      for (var f = 0; f < 10; f++) {
        c.observeLiveFrame('dev', 1, f, 0);
      }
      c.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 1, 0))!);
      c.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 2, 9))!);
      await c.recordDurableLiveFrames(
        'dev',
        1,
        0,
        10,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );

      final pending = c.isDurableLiveRecord('dev', 42, 1);
      await Future<void>.delayed(const Duration(milliseconds: 20));
      c.noteInfo('dev', 1, info(ringId: 43));
      gate.complete();
      expect(
        await pending,
        isFalse,
        reason: 'a re-anchored incarnation must not trust a proof validated under the old ring',
      );
    });

    test('marks spaced one record apart stay provable across a u16 counter wrap', () async {
      await custody.beginConnection('dev', 1, info());
      // Ending the session drops its thousands of lazily queued mark persists, so teardown's
      // flush does not write them one by one (even when an expectation below fails).
      addTearDown(() => custody.endConnection('dev', 1));
      custody.setLivePersistEnabled('dev', 1, true);
      var frame = 0;
      for (var r = 1; r <= 3300; r++) {
        for (var i = 0; i < 20; i++) {
          custody.observeLiveFrame('dev', 1, (frame++) & 0xFFFF, 0);
        }
        custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, r, (r * 20) & 0xFFFF))!);
      }
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        20,
        66000,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );
      expect(await custody.isDurableLiveRecord('dev', 42, 3200), isTrue);
    });

    test('a first mark delayed beyond a full wrap is unprovable — fail closed, keep both', () async {
      await custody.beginConnection('dev', 1, info());
      custody.setLivePersistEnabled('dev', 1, true);
      for (var k = 0; k < 65546; k++) {
        custody.observeLiveFrame('dev', 1, k & 0xFFFF, 0);
      }
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 1, 5))!);
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 2, 10))!);
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        65541,
        65546,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );
      expect(await custody.isDurableLiveRecord('dev', 42, 1), isFalse);
      expect(await custody.validatedAdvanceTarget('dev', 1, 42), isNull);
    });

    test('a large record gap after a valid anchor cannot be proven by a u16 lookalike index delta', () async {
      await custody.beginConnection('dev', 1, info());
      custody.setLivePersistEnabled('dev', 1, true);
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 0, 0))!);
      for (var k = 0; k < 65546; k++) {
        custody.observeLiveFrame('dev', 1, k & 0xFFFF, 0);
      }
      custody.observeLiveMark('dev', 1, RingProtocol.parseLiveMarkNotification(liveMark(42, 400, 10))!);
      await custody.recordDurableLiveFrames(
        'dev',
        1,
        0,
        10,
        const CustodyWalRef(fileName: 'w.bin', bytes: 1, frames: 1, liveRingId: 42),
      );
      expect(
        await custody.isDurableLiveRecord('dev', 42, 5),
        isFalse,
        reason: 'seq gap 400 * 220 exceeds the u16 window — the delta-10 index cannot anchor a boundary',
      );
      expect(
        await custody.validatedAdvanceTarget('dev', 1, 42),
        isNull,
        reason: 'no release to 400 — keep both copies',
      );
    });

    test('nothing persists without CAP_RING_ID', () async {
      final legacy = RingProtocol.parseInfoNotification(infoPayload(readSeq: 0, writeSeq: 20))!;
      await custody.beginConnection('dev', 1, legacy);
      await custody.recordDurableRingRange('dev', 1, 0, 0, 10, []); // no-op: ring_id mismatch (null != 0)
      custody.endConnection('dev', 1);
      var replayed = false;
      await custody.beginConnection(
        'dev',
        2,
        legacy,
        replayAdvance: (seq) async {
          replayed = true;
          return 0;
        },
      );
      expect(replayed, isFalse);
      expect(await tmp.list().toList(), isEmpty);
    });
  });
}
