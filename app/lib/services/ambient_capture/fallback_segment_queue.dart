import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'package:omi/services/ambient_capture/ambient_capture_models.dart';

class FallbackSegmentQueue {
  FallbackSegmentQueue({File? file}) : _file = file;

  File? _file;

  Future<File> get _queueFile async {
    if (_file != null) return _file!;
    final dir = await getApplicationDocumentsDirectory();
    _file = File('${dir.path}/ambient_fallback_segments.jsonl');
    return _file!;
  }

  Future<void> enqueue(AmbientFallbackSegment segment) async {
    final existing = await _loadAll();
    final key = _dedupeKey(segment);
    if (existing.any((item) => _dedupeKey(item) == key)) return;
    final file = await _queueFile;
    await file.parent.create(recursive: true);
    await file.writeAsString('${jsonEncode(segment.toJson())}\n', mode: FileMode.append, flush: true);
  }

  Future<List<AmbientFallbackSegment>> loadPending() async {
    return (await _loadAll()).where((segment) => !segment.uploadedToOmi).toList();
  }

  Future<void> markUploaded(List<AmbientFallbackSegment> uploaded) async {
    final uploadedKeys = uploaded.map(_dedupeKey).toSet();
    final all = await _loadAll();
    await replaceAll(
      all
          .map(
            (segment) => uploadedKeys.contains(_dedupeKey(segment))
                ? segment.copyWith(uploadedToOmi: true)
                : segment,
          )
          .toList(),
    );
  }

  Future<void> clearUploaded() async {
    await replaceAll((await _loadAll()).where((segment) => !segment.uploadedToOmi).toList());
  }

  Future<List<AmbientFallbackSegment>> _loadAll() async {
    final file = await _queueFile;
    if (!await file.exists()) return [];
    final lines = await file.readAsLines();
    return lines
        .where((line) => line.trim().isNotEmpty)
        .map((line) => AmbientFallbackSegment.fromJson(jsonDecode(line) as Map<String, dynamic>))
        .toList();
  }

  Future<void> replaceAll(List<AmbientFallbackSegment> segments) async {
    final file = await _queueFile;
    await file.parent.create(recursive: true);
    final payload = segments.map((segment) => jsonEncode(segment.toJson())).join('\n');
    await file.writeAsString(payload.isEmpty ? '' : '$payload\n', flush: true);
  }

  Future<void> clear() async {
    final file = await _queueFile;
    if (await file.exists()) await file.delete();
  }

  String _dedupeKey(AmbientFallbackSegment segment) {
    return [
      segment.source.name,
      segment.text.trim(),
      segment.start.toUtc().toIso8601String(),
      segment.end.toUtc().toIso8601String(),
    ].join('|');
  }
}
