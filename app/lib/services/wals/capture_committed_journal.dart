import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:omi/backend/schema/capture_committed_event.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/sync_upload_batch.dart';

/// Owner-scoped, durable receipts. Corrupt/missing proof never releases audio.
/// Each event is retained; union coverage cannot count overlaps twice.
class CaptureCommittedJournal {
  CaptureCommittedJournal(this.directory);
  final Future<Directory> Function() directory;
  final Map<String, List<CaptureCommittedEvent>> _cache = {};
  Future<File> _file(String owner) async =>
      File('${(await directory()).path}/capture_committed_${sha256.convert(utf8.encode(owner))}.json');
  Future<List<CaptureCommittedEvent>> _read(String owner) async {
    if (_cache[owner] case final rows?) return rows;
    final file = await _file(owner);
    if (!await file.exists()) return _cache[owner] = [];
    final rows = jsonDecode(await file.readAsString()) as List;
    return _cache[owner] = rows
        .map((row) => CaptureCommittedEvent.parse(Map<String, dynamic>.from(row as Map)))
        .whereType<CaptureCommittedEvent>()
        .toList();
  }

  Future<void> record(String owner, CaptureCommittedEvent event) async {
    List<CaptureCommittedEvent> rows;
    try {
      rows = List.of(await _read(owner));
    } catch (_) {
      rows = [];
    }
    final encoded = jsonEncode(event.toJson());
    if (!rows.any((row) => jsonEncode(row.toJson()) == encoded)) rows.add(event);
    if (rows.length > 10000) rows.removeRange(0, rows.length - 10000);
    final file = await _file(owner);
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(jsonEncode(rows.map((row) => row.toJson()).toList()), flush: true);
    await tmp.rename(file.path);
    _cache[owner] = rows;
  }

  Future<bool> covers(String owner, Wal wal) async {
    final start = wal.sourceFrameStart;
    // Upload and release share one S1 eligibility rule (including mono channel).
    if (owner.isEmpty || wal.ownerUid != owner || start == null || !captureEvidenceWalClaimable(wal)) {
      return false;
    }
    try {
      final rows = (await _read(owner))
          .where((row) =>
              row.captureRoot == wal.captureRoot &&
              row.channel == 'mono' &&
              row.clockEpoch == wal.sourceClockEpoch.toString() &&
              (row.recordingSessionId == null || row.recordingSessionId == wal.recordingSessionId))
          .toList()
        ..sort((a, b) => a.sourceStart.compareTo(b.sourceStart));
      var cursor = start;
      for (final row in rows) {
        if (row.sourceStart > cursor) break;
        if (row.sourceEnd > cursor) cursor = row.sourceEnd;
        if (cursor >= start + wal.totalFrames) return true;
      }
    } catch (_) {
      return false;
    }
    return false;
  }
}
