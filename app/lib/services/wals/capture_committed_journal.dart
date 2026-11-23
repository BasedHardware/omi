import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:pool/pool.dart';

import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/audio/wal_wav_worker.dart' show readLengthPrefixedFrames;
import 'package:omi/utils/off_ui_isolate.dart';

typedef _StreamKey = (String root, int epoch);
typedef _FrameRun = ({_StreamKey key, String? session, int start, List<String> hashes});
typedef _WalIdentity = ({
  _StreamKey key,
  String? session,
  int start,
  int count,
  WalStorage storage,
  String? filePath,
  String? fileSha256,
});

const _defaultEvidenceBytes = 16 * 1024 * 1024;
const _bucketCount = 8192;
const _maxHeaderBytes = 256 * 1024;
const _maxWalBytes = 32 * 1024 * 1024;
final _rootPattern = RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$');
final _digestPattern = RegExp(r'^[0-9a-f]{64}$');

/// Durable, owner-scoped audio manifest evidence. Range-only receipts cannot
/// advance custody. The legacy JSON journal is left intact for inventory.
class CaptureCommittedJournal {
  CaptureCommittedJournal(this.directory, {int maxEvidenceBytes = _defaultEvidenceBytes})
      : _maxEvidenceBytes = maxEvidenceBytes.clamp(0, _defaultEvidenceBytes);

  final Future<Directory> Function() directory;
  final int _maxEvidenceBytes;
  static final _lock = Pool(1);
  static final _failedWrites = <String>{};
  static int _revision = 0;
  ({String path, FileStat stat, int revision, _ProofLog proof})? _cache;

  /// Return the source intervals whose evidence changed, to limit receipt-time
  /// reconciliation to WALs that this write can affect.
  Future<List<({String root, int epoch, int start, int end})>> record(String owner, MessageEvent event,
      {String? recordingSessionId}) async {
    if (owner.isEmpty || owner == 'legacy') return const [];
    final runs = _manifestRuns(owner, event, recordingSessionId);
    final transcriptOnly = event is CaptureCommittedEvent && event.audioCustody == null;
    if (runs.isEmpty && !transcriptOnly) return const [];
    return _lock.withResource(() async {
      final ownerHash = sha256.convert(utf8.encode(owner)).toString();
      final file = await _file(ownerHash);
      final proof = await _read(file, ownerHash);
      final fresh = runs.where(proof.hasNewEvidence).toList();
      if (fresh.isEmpty && !transcriptOnly) return const [];
      // Preserve the immutable object pins alongside the exact source evidence.
      // Replay goes through the same wire parser as live delivery. Bare
      // transcript receipts remain readable but never populate the proof index.
      final wire = event is CaptureCommittedEvent ? event.toJson() : (event as AudioCustodyEvent).toJson();
      final line = '${jsonEncode([recordingSessionId, wire])}\n';
      final lineBytes = utf8.encode(line).length;
      // Historical transcript information must never evict durable audio proof.
      if (transcriptOnly && proof.payloadBytes + lineBytes > _maxEvidenceBytes) return const [];
      _revision++;
      try {
        if (proof.payloadBytes + lineBytes > _maxEvidenceBytes) {
          // Once a key is forgotten, an old or contradictory receipt can never
          // make it releasable again. Bucket collisions only extend the fence.
          proof.evict();
          final fits = lineBytes <= _maxEvidenceBytes;
          if (!fits) {
            for (final run in fresh) {
              proof.fence(run.key, run.start + run.hashes.length - 1);
            }
          }
          await _replace(file, proof.header(ownerHash) + (fits ? line : ''));
          if (fits) proof.add(fresh, lineBytes);
        } else {
          if (_cache?.stat.type == FileSystemEntityType.notFound) {
            await _replace(file, proof.header(ownerHash) + line);
          } else {
            await file.writeAsString(line, mode: FileMode.append, flush: true);
          }
          proof.add(fresh, lineBytes);
        }
        _cache = (path: file.path, stat: await file.stat(), revision: _revision, proof: proof);
        return [
          for (final run in fresh)
            (root: run.key.$1, epoch: run.key.$2, start: run.start, end: run.start + run.hashes.length)
        ];
      } catch (_) {
        // A failed write may have been carrying a contradiction. Any later
        // evaluation in this process must keep this owner's audio pending.
        _cache = null;
        _failedWrites.add(file.path);
        rethrow;
      }
    });
  }

  /// Capture the same source and file identity used by the evaluator, so a
  /// caller deciding a batch can revalidate each row immediately before commit.
  static Object? releaseIdentity(String owner, Wal wal) => _identity(owner, wal);

  Future<bool> covers(String owner, Wal wal) async {
    final result = await evaluate(owner, wal);
    return result.covered && result.audited == true;
  }

  /// [covered] is the compact interval check. [audited] walks local frame
  /// payloads against the manifest hashes. Null indicates unavailable evidence.
  Future<({bool covered, bool? audited})> evaluate(String owner, Wal wal) async {
    const unknown = (covered: false, audited: null);
    final identity = _identity(owner, wal);
    if (identity == null) return unknown;
    try {
      return await _lock.withResource(() async {
        final ownerHash = sha256.convert(utf8.encode(owner)).toString();
        final file = await _file(ownerHash);
        if (_failedWrites.contains(file.path)) return unknown;
        final proof = await _read(file, ownerHash);
        final stream = proof.streams[identity.key];
        if (stream == null || identity.start <= proof.floor(stream.bucket) || identity != _identity(owner, wal)) {
          return unknown;
        }
        final covered = stream.covers(identity.start, identity.start + identity.count, identity.session);
        bool? audited;
        try {
          audited = await _audit(file.parent, wal, identity, stream);
        } on FileSystemException {
          // The compact predicate remains meaningful when local audio is unavailable.
        }
        if (identity != _identity(owner, wal)) return unknown;
        return (covered: covered, audited: audited);
      });
    } catch (_) {
      return unknown;
    }
  }

  Future<File> _file(String ownerHash) async => File('${(await directory()).path}/capture_committed_$ownerHash.jsonl');

  Future<_ProofLog> _read(File file, String ownerHash) async {
    final stat = await file.stat();
    if (await File('${file.path}.tmp').exists()) throw const FormatException('interrupted custody journal replacement');
    final cached = _cache;
    if (cached != null && cached.path == file.path && cached.revision == _revision && _sameStat(cached.stat, stat)) {
      return cached.proof;
    }
    final _ProofLog proof;
    if (stat.type == FileSystemEntityType.notFound) {
      proof = _ProofLog();
    } else {
      if (stat.type != FileSystemEntityType.file || stat.size > _maxHeaderBytes + _defaultEvidenceBytes) {
        throw const FormatException('invalid custody journal size');
      }
      final content = await file.readAsString();
      if (!_sameStat(stat, await file.stat())) throw const FormatException('custody journal changed');
      final expected = ownerHash;
      proof = await offUiIsolate(() => _decodeProof(content, expected),
          size: stat.size, threshold: 64 * 1024, debugName: 'custody_journal_read');
    }
    _cache = (path: file.path, stat: stat, revision: _revision, proof: proof);
    return proof;
  }

  static Future<void> _replace(File file, String contents) async {
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(contents, flush: true);
    await tmp.rename(file.path);
  }

  /// Read-only inventory validation. No proof or owner data leaves the census.
  static bool isReadableProofLog(String content, String ownerHash) {
    try {
      _walkProof(content, ownerHash);
      return true;
    } on FormatException {
      return false;
    }
  }
}

_WalIdentity? _identity(String owner, Wal wal) {
  if (owner.isEmpty ||
      owner == 'legacy' ||
      owner != wal.ownerUid ||
      wal.holdForUser ||
      wal.onDeviceOnly ||
      wal.isSyncing ||
      (wal.status != WalStatus.miss && (wal.status != WalStatus.synced || wal.syncedAt != 0)) ||
      (wal.storage != WalStorage.disk && wal.storage != WalStorage.mem) ||
      !captureEvidenceWalClaimable(wal)) {
    return null;
  }
  final start = wal.sourceFrameStart!;
  if (start + wal.totalFrames <= start) return null;
  return (
    key: (wal.captureRoot!, wal.sourceClockEpoch!),
    session: wal.recordingSessionId,
    start: start,
    count: wal.totalFrames,
    storage: wal.storage,
    filePath: wal.filePath,
    fileSha256: wal.fileSha256,
  );
}

List<_FrameRun> _manifestRuns(String owner, MessageEvent event, String? socketSession) {
  final range = event is CaptureCommittedEvent ? event : null;
  final audio = event is AudioCustodyEvent ? event : range?.audioCustody;
  if (audio == null || audio.owner != owner || (range != null && range.conversationId != audio.conversationId)) {
    return const [];
  }
  final rangeSession = range?.recordingSessionId;
  final audioSession = audio.recordingSessionId;
  if (rangeSession != null && audioSession != null && rangeSession != audioSession) return const [];
  final supplied = rangeSession ?? audioSession;
  if (socketSession != null && supplied != null && socketSession != supplied) return const [];
  final session = supplied ?? socketSession;
  if (session != null && session.trim().isEmpty) return const [];
  final runs = <_FrameRun>[];
  for (final frame in audio.frames) {
    if (frame.channel != 'mono' ||
        frame.clockEpoch < 0 ||
        frame.ordinal < 0 ||
        frame.ordinal + 1 <= frame.ordinal ||
        !_rootPattern.hasMatch(frame.captureRoot) ||
        !_digestPattern.hasMatch(frame.sha256)) {
      continue;
    }
    if (range != null &&
        (range.captureRoot != frame.captureRoot ||
            range.channel != frame.channel ||
            range.clockEpoch != frame.clockEpoch.toString() ||
            frame.ordinal < range.sourceStart ||
            frame.ordinal >= range.sourceEnd)) {
      continue;
    }
    final key = (frame.captureRoot, frame.clockEpoch);
    final last = runs.lastOrNull;
    if (last != null && last.key == key && last.start + last.hashes.length == frame.ordinal) {
      last.hashes.add(frame.sha256);
    } else {
      runs.add((key: key, session: session, start: frame.ordinal, hashes: [frame.sha256]));
    }
  }
  return runs;
}

_ProofLog _decodeProof(String content, String ownerHash) {
  final proof = _ProofLog();
  _walkProof(content, ownerHash, onHeader: proof.floors.addAll, onEntry: proof.add);
  return proof;
}

void _walkProof(String content, String ownerHash,
    {void Function(Map<int, int>)? onHeader, void Function(List<_FrameRun>, int)? onEntry}) {
  if (!content.endsWith('\n')) throw const FormatException('torn custody journal');
  final lines = const LineSplitter().convert(content);
  final header = jsonDecode(lines.first);
  if (header is! Map ||
      header.length != 3 ||
      header['v'] != 1 ||
      header['owner'] != ownerHash ||
      header['floor'] is! Map) {
    throw const FormatException('invalid custody journal header');
  }
  final floors = <int, int>{};
  for (final MapEntry(:key, :value) in (header['floor'] as Map).entries) {
    final bucket = int.tryParse(key as String);
    if (bucket == null ||
        bucket.toString() != key ||
        bucket < 0 ||
        bucket >= _bucketCount ||
        value is! int ||
        value < 0 ||
        value + 1 <= value) {
      throw const FormatException('invalid custody journal fence');
    }
    floors[bucket] = value;
  }
  onHeader?.call(floors);
  for (final line in lines.skip(1)) {
    final entry = jsonDecode(line);
    if (entry is! List ||
        entry.length != 2 ||
        entry[1] is! Map<String, dynamic> ||
        (entry[0] != null && (entry[0] is! String || (entry[0] as String).trim().isEmpty))) {
      throw const FormatException('invalid custody journal entry');
    }
    final wire = entry[1] as Map<String, dynamic>;
    final event = MessageEvent.fromJson(wire);
    if (event is CaptureCommittedEvent && !wire.keys.every(event.toJson().containsKey)) {
      throw const FormatException('unknown transcript journal field');
    }
    final audio = event is AudioCustodyEvent
        ? event
        : event is CaptureCommittedEvent
            ? event.audioCustody
            : null;
    if (audio == null && (event is! CaptureCommittedEvent || wire.containsKey('audio_custody'))) {
      throw const FormatException('invalid journal receipt');
    }
    if (audio != null && sha256.convert(utf8.encode(audio.owner)).toString() != ownerHash) {
      throw const FormatException('foreign journal receipt');
    }
    final runs = audio == null ? <_FrameRun>[] : _manifestRuns(audio.owner, event, entry[0] as String?);
    onEntry?.call(runs, utf8.encode(line).length + 1);
  }
}

int _bucket(_StreamKey key) {
  final hash = sha256.convert(utf8.encode('${key.$1}/${key.$2}')).bytes;
  return ((hash[0] << 8) | hash[1]) % _bucketCount;
}

class _ProofLog {
  final streams = <_StreamKey, _ManifestIndex>{};
  final floors = <int, int>{};
  int payloadBytes = 0;

  int floor(int bucket) => floors[bucket] ?? -1;

  String header(String ownerHash) =>
      '${jsonEncode({'v': 1, 'owner': ownerHash, 'floor': floors.map((key, value) => MapEntry('$key', value))})}\n';

  bool hasNewEvidence(_FrameRun run) {
    final stream = streams[run.key];
    final first = floor(stream?.bucket ?? _bucket(run.key)) + 1;
    for (var i = (first > run.start ? first - run.start : 0); i < run.hashes.length; i++) {
      final frame = stream?.frames[run.start + i];
      if (frame == null || !frame.conflict && (frame.hash != run.hashes[i] || !frame.supports(run.session))) {
        return true;
      }
    }
    return false;
  }

  void add(List<_FrameRun> runs, int bytes) {
    payloadBytes += bytes;
    for (final run in runs) {
      final stream = streams.putIfAbsent(run.key, () => _ManifestIndex(_bucket(run.key)));
      final first = floor(stream.bucket) + 1;
      final offset = first > run.start ? first - run.start : 0;
      if (offset < run.hashes.length) stream.add(run, offset);
    }
  }

  void fence(_StreamKey key, int ordinal) {
    final bucket = _bucket(key);
    if (ordinal > floor(bucket)) floors[bucket] = ordinal;
  }

  void evict() {
    for (final entry in streams.entries) {
      fence(entry.key, entry.value.lastOrdinal);
    }
    streams.clear();
    payloadBytes = 0;
  }
}

class _FrameProof {
  _FrameProof(this.hash, this.session);
  final String hash;
  final String? session;
  Set<String?>? _otherSessions;
  bool conflict = false;

  bool supports(String? candidate) => session == candidate || (_otherSessions?.contains(candidate) ?? false);

  void addScope(String? candidate) {
    if (!supports(candidate)) (_otherSessions ??= {}).add(candidate);
  }
}

class _ManifestIndex {
  _ManifestIndex(this.bucket);
  final int bucket;
  final frames = <int, _FrameProof>{};
  final _ranges = <String?, SplayTreeMap<int, int>>{};
  final _conflicts = SplayTreeMap<int, bool>();
  int lastOrdinal = -1;

  void add(_FrameRun run, int offset) {
    final start = run.start + offset;
    final end = run.start + run.hashes.length;
    if (end - 1 > lastOrdinal) lastOrdinal = end - 1;
    for (var i = offset; i < run.hashes.length; i++) {
      final ordinal = run.start + i;
      final hash = run.hashes[i];
      final frame = frames.putIfAbsent(ordinal, () => _FrameProof(hash, run.session));
      if (hash != frame.hash) {
        frame.conflict = true;
        _conflicts[ordinal] = true;
      }
      frame.addScope(run.session);
    }
    final intervals = _ranges.putIfAbsent(run.session, SplayTreeMap.new);
    final previous = intervals.lastKeyBefore(start + 1);
    var left = start, right = end;
    if (previous != null && intervals[previous]! >= start) {
      left = previous;
      if (intervals[previous]! > right) right = intervals[previous]!;
      intervals.remove(previous);
    }
    var next = intervals.firstKeyAfter(left);
    while (next != null && next <= right) {
      final nextEnd = intervals.remove(next)!;
      if (nextEnd > right) right = nextEnd;
      next = intervals.firstKeyAfter(left);
    }
    intervals[left] = right;
  }

  bool covers(int start, int end, String? session) {
    final conflict = _conflicts.firstKeyAfter(start - 1);
    if (conflict != null && conflict < end) return false;
    final intervals = _ranges[session];
    final left = intervals?.lastKeyBefore(start + 1);
    return left != null && intervals![left]! >= end;
  }
}

bool _sameStat(FileStat before, FileStat after) =>
    before.type == after.type &&
    before.size == after.size &&
    before.modified == after.modified &&
    before.changed == after.changed;

Future<bool?> _audit(Directory directory, Wal wal, _WalIdentity identity, _ManifestIndex stream) async {
  // With too few indexed coordinates, an independent payload walk cannot
  // certify this WAL. Avoid reopening a pending copy for each arriving frame.
  final end = identity.start + identity.count;
  if (stream.frames.length < identity.count ||
      !stream.frames.containsKey(identity.start) ||
      !stream.frames.containsKey(end - 1)) {
    return null;
  }

  var missing = false, mismatch = false, ordinal = identity.start;
  void compare(List<int> payload) {
    final frame = stream.frames[ordinal++];
    if (frame?.conflict == true) {
      mismatch = true;
    } else if (frame == null || !frame.supports(identity.session)) {
      missing = true;
    } else if (sha256.convert(payload).toString() != frame.hash) {
      mismatch = true;
    }
  }

  if (identity.storage == WalStorage.mem) {
    if (wal.data.length != identity.count) return null;
    for (final payload in wal.data) {
      if (payload.isEmpty || payload.any((byte) => byte < 0 || byte > 255)) return null;
      compare(payload);
    }
  } else {
    // Match Wal.getFilePath's rebasing for paths stored before a container move.
    final name = identity.filePath?.split('/').last;
    if (name == null || name.isEmpty || name == '.' || name == '..' || name.contains('\\')) return null;
    final file = File('${directory.path}/$name');
    if (await FileSystemEntity.type(file.path, followLinks: false) != FileSystemEntityType.file) return null;
    final before = await file.stat();
    if (before.size ~/ 5 < identity.count || before.size > _maxWalBytes) return null;
    Digest? fileDigest;
    final digestSink = identity.fileSha256 == null
        ? null
        : sha256.startChunkedConversion(
            ChunkedConversionSink<Digest>.withCallback((digests) => fileDigest = digests.single));
    var decodedBytes = 0;
    final chunks = file.openRead().map((chunk) {
      digestSink?.add(chunk);
      return chunk;
    });
    await for (final payload in readLengthPrefixedFrames(chunks)) {
      if (ordinal >= end || payload.isEmpty) return null;
      decodedBytes += 4 + payload.length;
      compare(payload);
    }
    digestSink?.close();
    // The playback decoder yields complete frames before a torn tail.
    // Requiring exact byte consumption prevents such a prefix proving custody.
    if (ordinal != end ||
        decodedBytes != before.size ||
        (digestSink != null && fileDigest.toString() != identity.fileSha256) ||
        !_sameStat(before, await file.stat())) {
      return null;
    }
  }
  return mismatch ? false : (missing ? null : true);
}
