import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/wals/capture_committed_journal.dart';
import 'package:omi/services/wals/recording_inventory.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_frame_encoder.dart';

const _owner = 'private-owner';
const _root = '11111111-2222-4333-8444-555555555555';
const _filename = 'audio_phone_pcm16_16000_1_100.bin';
const _sample = [3, 9];

AudioCustodyEvent _manifest(List<(int, List<int>)> frames,
    {String? session = 'recording', int epoch = 2, String owner = _owner}) {
  final wire = jsonDecode(File('test/fixtures/listen_audio_custody.json').readAsStringSync()) as Map<String, dynamic>;
  wire.remove('client_session_id');
  wire['recording_session_id'] = session;
  final receipt = wire['receipt'] as Map<String, dynamic>;
  for (final key in ['path', 'manifest_path']) {
    final parts = (receipt[key] as String).split('/');
    parts[1] = owner;
    receipt[key] = parts.join('/');
  }
  wire['frames'] = [
    for (final (index, (ordinal, payload)) in frames.indexed)
      <String, dynamic>{
        'sequence': index,
        'byte_offset': index * _sample.length,
        'bytes': payload.length,
        'samples': 1,
        'start': 100.0,
        'gap_before': false,
        'sha256': sha256.convert(payload).toString(),
        'source': <String, dynamic>{'capture_root': _root, 'clock_epoch': epoch, 'source_frame': ordinal},
      },
  ];
  return AudioCustodyEvent.parse(wire)!;
}

CaptureCommittedEvent _range({AudioCustodyEvent? audio, int start = 7, int end = 8}) => CaptureCommittedEvent.parse({
      'type': 'capture_committed',
      'conversation_id': 'conversation',
      'capture_root': _root,
      'channel': 'mono',
      'clock_epoch': '2',
      'recording_session_id': 'recording',
      'source_start': start,
      'source_end': end,
      if (audio != null) 'audio_custody': audio.toJson(),
    }) as CaptureCommittedEvent;

Wal _wal({int start = 7, int count = 1}) => Wal(
      timerStart: 100,
      codec: BleAudioCodec.pcm16,
      storage: WalStorage.disk,
      status: WalStatus.miss,
      sampleRate: 16000,
      seconds: 1,
      totalFrames: count,
      ownerUid: _owner,
      captureRoot: _root,
      sourceFrameStart: start,
      sourceClockEpoch: 2,
      recordingSessionId: 'recording',
      device: 'phone',
      filePath: _filename,
    );

void main() {
  late Directory directory;
  late File localFile;
  late String journalStem;
  late CaptureCommittedJournal journal;
  CaptureCommittedJournal restart({int? budget}) => budget == null
      ? CaptureCommittedJournal(() async => directory)
      : CaptureCommittedJournal(() async => directory, maxEvidenceBytes: budget);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('capture-committed-journal');
    journalStem = '${directory.path}/capture_committed_${sha256.convert(utf8.encode(_owner))}';
    localFile = File('${directory.path}/$_filename');
    await localFile.writeAsBytes(encodeWalFrames([_sample]));
    journal = restart();
  });
  tearDown(() => directory.delete(recursive: true));

  test('disk audit compares exact payload bytes, including order and file identity', () async {
    const second = [2, 4, 6];
    final wal = _wal(count: 2)..filePath = '/previous-container/$_filename';
    await journal.record(_owner, _manifest([(7, _sample), (8, second)]));
    final bytes = encodeWalFrames([_sample, second]);
    await localFile.writeAsBytes(bytes);
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: true));
    expect(await restart().covers(_owner, wal), isTrue);
    await localFile.writeAsBytes(encodeWalFrames([second, _sample]));
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: false));
    expect(await journal.covers(_owner, wal), isFalse);
    wal.fileSha256 = sha256.convert(bytes).toString();
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: null));
    await localFile.writeAsBytes(bytes);
    expect(await journal.covers(_owner, wal), isTrue);
  });

  test('a valid prefix with malformed framing cannot pass the audit', () async {
    final wal = _wal();
    await journal.record(_owner, _manifest([(7, _sample)]));
    final bytes = encodeWalFrames([_sample]);
    for (final invalid in [
      bytes.sublist(0, bytes.length - 1),
      [...bytes, 1],
      [...bytes, 4, 0, 0, 0, 9],
      [...bytes, ...bytes],
      [...bytes, 0, 0, 0, 0],
      [255, 255, 255, 255, ..._sample],
    ]) {
      await localFile.writeAsBytes(invalid);
      expect(await journal.evaluate(_owner, wal), (covered: true, audited: null));
      expect(await journal.covers(_owner, wal), isFalse);
    }
    await localFile.delete();
    expect(await journal.covers(_owner, wal), isFalse);
  });

  test('legacy range journal stays readable and only the explicit intersection proves custody', () async {
    final legacy = File('$journalStem.json');
    final bytes = jsonEncode([_range(end: 9).toJson()]);
    await legacy.writeAsString(bytes);
    await journal.record(_owner, _range(end: 9));
    final wal = _wal();
    expect(await journal.covers(_owner, wal), isFalse);
    await journal.record(_owner, _range(end: 9, audio: _manifest([(7, _sample)])));
    expect(await restart().covers(_owner, wal), isTrue);
    for (final start in [8, 9]) {
      expect(await journal.covers(_owner, _wal(start: start)), isFalse);
    }
    expect(await legacy.readAsString(), bytes);
    final inventory = await captureRecordingInventory(
        documents: directory.path, phoneSeconds: 100, currentOwner: _owner, memoryBuckets: {});
    final bucket = (inventory['buckets'] as Map)['capture_committed'] as Map;
    expect(bucket['readable_source_files'], 2);
    expect(bucket['by_owner_class'], {'current': 2});
    expect(jsonEncode(inventory), isNot(contains(_owner)));
  });

  test('ranges union within identity, with gaps and foreign or ineligible rows fenced', () async {
    final wal = _wal(count: 3);
    await localFile.writeAsBytes(encodeWalFrames(List.filled(3, _sample)));
    await Future.wait([
      journal.record(_owner, _manifest([(7, _sample)])),
      restart().record(_owner, _manifest([(9, _sample)])),
    ]);
    await journal.record(_owner, _manifest([(8, _sample)], session: 'other'));
    await journal.record(_owner, _manifest([(8, _sample)], epoch: 3));
    await journal.record(_owner, _manifest([(8, _sample)], owner: 'other'));
    expect(await journal.evaluate(_owner, wal), (covered: false, audited: null));
    await journal.record(_owner, _manifest([(8, _sample), (9, _sample)]));
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: true));
    expect(await journal.covers('other', wal), isFalse);
    for (final ineligible in [
      _wal(count: 3)..holdForUser = true,
      _wal(count: 3)..onDeviceOnly = true,
      _wal(count: 3)..isSyncing = true,
      _wal(count: 3)..channel = 2,
      _wal(count: 3)..status = WalStatus.uploaded,
      _wal(count: 3)..storage = WalStorage.sdcard,
      _wal(count: 3)..recordingSessionId = 'different',
    ]) {
      expect(await journal.covers(_owner, ineligible), isFalse);
    }
  });

  test('server rollover binds both kinds of receipt to the original phone session after restart', () async {
    final wire = _manifest([(7, _sample)]).toJson()..['client_session_id'] = 'phone-session';
    final rolled = AudioCustodyEvent.parse(wire)!;
    final wal = _wal()..recordingSessionId = 'phone-session';
    await journal.record(_owner, _range(audio: rolled), recordingSessionId: 'different-socket');
    expect(await restart().covers(_owner, wal), isFalse);
    await journal.record(_owner, _range(audio: rolled), recordingSessionId: 'phone-session');
    expect(await restart().covers(_owner, wal), isTrue);
    expect(await restart().covers(_owner, _wal()), isFalse);
  });

  test('shadow file or journal changes invalidate a previously matching disk audit', () async {
    final wal = _wal();
    await journal.record(_owner, _manifest([(7, _sample)]));
    expect((await journal.evaluate(_owner, wal, shadow: true)).audited, isTrue);
    expect((await journal.evaluate(_owner, wal, shadow: true)).audited, isTrue);
    await localFile.writeAsBytes(encodeWalFrames([
      [9, 9, 9]
    ]));
    expect((await journal.evaluate(_owner, wal, shadow: true)).audited, isFalse);
    await localFile.writeAsBytes(encodeWalFrames([_sample]));
    expect((await journal.evaluate(_owner, wal, shadow: true)).audited, isTrue);
    await journal.record(
        _owner,
        _manifest([
          (7, [8, 8])
        ]));
    expect(await journal.evaluate(_owner, wal, shadow: true), (covered: false, audited: false));
  });

  test('socket recording session scopes an unbound receipt across restart', () async {
    final unbound = _manifest([(7, _sample)], session: null);
    await journal.record(_owner, unbound);
    expect(await restart().covers(_owner, _wal()), isFalse);
    expect(await restart().covers(_owner, _wal()..recordingSessionId = null), isTrue);
    await journal.record(_owner, unbound, recordingSessionId: 'other');
    expect(await restart().covers(_owner, _wal()), isFalse);
    await journal.record(_owner, _manifest([(7, _sample)]), recordingSessionId: 'other');
    expect(await restart().covers(_owner, _wal()), isFalse);
    await journal.record(_owner, unbound, recordingSessionId: 'recording');
    expect(await restart().covers(_owner, _wal()), isTrue);
  });

  test('contradictory packets within a single manifest fence that ordinal across replay', () async {
    await journal.record(_owner, _manifest([(7, _sample)]));
    await journal.record(
        _owner,
        _manifest([
          (7, _sample),
          (7, [2, 5])
        ]));
    expect(await restart().covers(_owner, _wal()), isFalse);
  });
  test('a conflict survives duplicate replay, eviction and restart', () async {
    // Fit the first two wire receipts, then force rotation with the third.
    final budget = 2 *
        (utf8
                .encode(jsonEncode([
                  null,
                  _manifest([(7, _sample)]).toJson()
                ]))
                .length +
            1);
    journal = restart(budget: budget);
    final original = _manifest([(7, _sample)]);
    await journal.record(_owner, original);
    expect(await journal.covers(_owner, _wal()), isTrue);
    final copy = restart(budget: budget);
    expect(await copy.covers(_owner, _wal()), isTrue);
    await journal.record(
        _owner,
        _manifest([
          (7, [2, 5])
        ]));
    expect(await copy.evaluate(_owner, _wal()), (covered: false, audited: false));
    await journal.record(_owner, original);
    expect(await restart(budget: budget).covers(_owner, _wal()), isFalse);

    await journal.record(_owner, _manifest([(8, _sample), (9, _sample)])); // Rotates and fences ordinal 7.
    final reopened = restart(budget: budget);
    expect(await reopened.covers(_owner, _wal(start: 8)), isTrue);
    await reopened.record(_owner, original);
    expect(await reopened.covers(_owner, _wal()), isFalse);
    expect(await reopened.covers(_owner, _wal(start: 9)), isTrue);
  });

  test('a torn journal or mismatched on-disk owner invalidates cached proof', () async {
    await journal.record(_owner, _manifest([(7, _sample)]));
    final log = File('$journalStem.jsonl');
    final complete = await log.readAsString();
    await log.writeAsString('$complete[', flush: true);
    expect(await journal.evaluate(_owner, _wal()), (covered: false, audited: null));
    expect(await restart().covers(_owner, _wal()), isFalse);
    await expectLater(restart().record(_owner, _manifest([(7, _sample)])), throwsFormatException);
    expect(await log.readAsString(), '$complete[');
    await log.writeAsString(complete.replaceFirst(sha256.convert(utf8.encode(_owner)).toString(), 'foreign-owner'));
    expect(await restart().covers(_owner, _wal()), isFalse);
  });

  test('in-memory audit validates count and bytes before coverage can release', () async {
    final wal = _wal()
      ..storage = WalStorage.mem
      ..filePath = null
      ..data = [_sample];
    await journal.record(_owner, _manifest([(7, _sample)]));
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: true));
    wal.data = [
      [3, 8]
    ];
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: false));
    wal.data = [
      [3, 265]
    ];
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: null));
    wal.data = [_sample, _sample];
    expect(await journal.evaluate(_owner, wal), (covered: true, audited: null));
  });
}
