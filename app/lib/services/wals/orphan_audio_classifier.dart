// Read-only orphan identity, framing and age classification for the ledger and
// diagnostics. Local file identities never enter the aggregate export.
part of 'recording_inventory.dart';

/// Device-local data only. Export [summary], never this object or its candidates.
class RecordingOrphanCensus {
  RecordingOrphanCensus(this.summary, this.orphans, this._directories, this._sources, this.owner);
  final Map<String, Object?> summary;
  final List<OrphanAudioFile> orphans;
  final Map<String, FileStat> _directories;
  final List<_Metadata> _sources;
  final String owner;
  bool isDocumentsFile(OrphanAudioFile file) => path.dirname(file.filePath) == _directories.keys.first;
  bool get complete => summary['orphan_census_complete'] == true;

  /// Small metadata-only commit fence. No directory walk on the capture queue.
  /// A new/removed receipt or index changes its parent directory stamp.
  bool sourcesUnchanged() {
    // An unusually large receipt archive remains classified but is deferred
    // rather than doing unbounded synchronous work on the capture queue.
    if (_sources.length > 512 || _directories.length > 4) return false;
    try {
      for (final e in _directories.entries) {
        // omi-perf-allow: sync-file-io -- At most four directory stamps; no traversal, and no await between final fence and publication.
        final stat = FileStat.statSync(e.key);
        if (stat.type != FileSystemEntityType.directory ||
            stat.modified != e.value.modified ||
            stat.changed != e.value.changed) {
          return false;
        }
      }
      for (final source in _sources) {
        // omi-perf-allow: sync-file-io -- At most 512 metadata stamps; larger archives defer, and audio/frame reads stay off the queue.
        final stat = FileStat.statSync(source.filePath);
        if (stat.type != FileSystemEntityType.file ||
            stat.size != source.bytes ||
            stat.modified.millisecondsSinceEpoch != source.modifiedMs ||
            stat.changed.millisecondsSinceEpoch != source.changedMs) {
          return false;
        }
      }
      return true;
    } catch (_) {
      return false;
    }
  }
}

class OrphanAudioFile {
  OrphanAudioFile(
      this.filePath, this.bytes, this.modifiedMs, this.changedMs, this.classification, this.info, this.frames);
  final String filePath;
  final int bytes, modifiedMs, changedMs, frames;
  final String classification;
  final BatchRecordingInfo? info;
  bool unchanged() {
    try {
      if (FileSystemEntity.typeSync(filePath, followLinks: false) != FileSystemEntityType.file) return false;
      // omi-perf-allow: sync-file-io -- At most 200 adopted-file stamps per pass, with no await between identity validation and admission.
      final stat = FileStat.statSync(filePath);
      return stat.size == bytes &&
          stat.modified.millisecondsSinceEpoch == modifiedMs &&
          stat.changed.millisecondsSinceEpoch == changedMs;
    } catch (_) {
      return false;
    }
  }
}

const orphanRecoveryWindowSeconds = 28 * 86400;
const orphanAudioClasses = ['working', 'unparseable', 'recoverable', 'expired', 'owner_unknown'];

List<OrphanAudioFile> _classifyOrphans(List<_Metadata> candidates, int phoneSeconds, bool owned) {
  return candidates.map((file) {
    final name = path.basename(file.filePath);
    final working = name.endsWith('.part') ||
        name.endsWith('.torn') ||
        name.startsWith('audio_omibatch') ||
        name.startsWith('audio_omimobilebatch');
    BatchRecordingInfo? info;
    var frames = 0;
    var classification = 'working';
    if (!working) {
      // BatchRecordingInfo is intentionally forgiving for legacy native intake;
      // unattended orphan adoption additionally requires the complete mono shape.
      if (RegExp(r'^audio_.+_(opus(?:_fs(?:160|320))?|pcm16|pcm8)_\d+_1_fs\d+_\d+\.bin$').hasMatch(name)) {
        info = BatchRecordingInfo.fromFileName(name);
      }
      if (info != null &&
          info.sampleRate > 0 &&
          info.frameSize > 0 &&
          info.timerStart >= 1704067200 &&
          info.timerStart <= phoneSeconds &&
          phoneSeconds <= 0x7fffffff) {
        frames = _strictFrameCount(file.filePath, file.bytes);
      }
      classification = frames <= 0
          ? 'unparseable'
          : !owned
              ? 'owner_unknown'
              : phoneSeconds - info!.timerStart > orphanRecoveryWindowSeconds
                  ? 'expired'
                  : 'recoverable';
    }
    return OrphanAudioFile(file.filePath, file.bytes, file.modifiedMs, file.changedMs, classification, info, frames);
  }).toList();
}

/// Streaming strict framing, off the UI isolate. Unlike native crash recovery,
/// a valid prefix does not make a malformed/truncated tail adoptable.
int _strictFrameCount(String path, int expectedBytes) {
  RandomAccessFile? file;
  try {
    // omi-perf-allow: sync-file-io -- This parser is called only by the forced offUiIsolate classifier, never on the capture/UI isolate.
    file = File(path).openSync();
    final buffer = Uint8List(64 * 1024), header = Uint8List(4);
    var headerHave = 0, remaining = 0, frames = 0, bytes = 0;
    while (true) {
      final count = file.readIntoSync(buffer);
      if (count == 0) break;
      bytes += count;
      var i = 0;
      while (i < count) {
        if (remaining > 0) {
          final skip = min(remaining, count - i);
          i += skip;
          remaining -= skip;
          if (remaining == 0) frames++;
        } else {
          header[headerHave++] = buffer[i++];
          if (headerHave == 4) {
            headerHave = 0;
            remaining = ByteData.sublistView(header).getUint32(0, Endian.little);
            if (remaining <= 0 || remaining > expectedBytes) return 0;
          }
        }
      }
    }
    return bytes == expectedBytes && remaining == 0 && headerHave == 0 ? frames : 0;
  } catch (_) {
    return 0;
  } finally {
    file?.closeSync();
  }
}

Map<String, Object?> orphanClassificationSummary(List<OrphanAudioFile> files, int phoneSeconds) {
  final classes = {
    for (final c in orphanAudioClasses) c: <String, int>{'count': 0, 'bytes': 0}
  };
  final ages = {
    for (final age in ['0_7', '8_14', '15_28', '29_45', 'over_45', 'unknown'])
      age: <String, int>{'count': 0, 'bytes': 0}
  };
  for (final file in files) {
    classes[file.classification]!['count'] = classes[file.classification]!['count']! + 1;
    classes[file.classification]!['bytes'] = classes[file.classification]!['bytes']! + file.bytes;
    final time = file.info?.timerStart ?? _filenameTime(file.filePath);
    final age = time == null || time < 1704067200 || time > phoneSeconds ? null : phoneSeconds - time;
    final bucket = age == null
        ? 'unknown'
        : age <= 7 * 86400
            ? '0_7'
            : age <= 14 * 86400
                ? '8_14'
                : age <= 28 * 86400
                    ? '15_28'
                    : age <= 45 * 86400
                        ? '29_45'
                        : 'over_45';
    ages[bucket]!['count'] = ages[bucket]!['count']! + 1;
    ages[bucket]!['bytes'] = ages[bucket]!['bytes']! + file.bytes;
  }
  return {'classes': classes, 'age_buckets': ages};
}
