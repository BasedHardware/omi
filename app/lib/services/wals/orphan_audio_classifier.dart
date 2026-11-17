// Read-only orphan identity, framing and age classification for the ledger and
// diagnostics. Local file identities never enter the aggregate export.
part of 'recording_inventory.dart';

/// Derived framing results only; never ownership, references or deletion proof.
/// Process-local and replaced with the current corpus after each census.
class OrphanAudioFrameCache {
  const OrphanAudioFrameCache.empty() : _entries = const {};
  OrphanAudioFrameCache._(this._entries);
  final Map<String, _CachedAudioFrames> _entries;
}

class _CachedAudioFrames {
  _CachedAudioFrames(_Metadata file, this.frames)
      : bytes = file.bytes,
        modifiedUs = file.modifiedUs,
        changedUs = file.changedUs;
  final int bytes, modifiedUs, changedUs, frames;
  bool matches(_Metadata file) => bytes == file.bytes && modifiedUs == file.modifiedUs && changedUs == file.changedUs;
}

/// Device-local data only. Export [summary], never this object or its candidates.
class RecordingOrphanCensus {
  RecordingOrphanCensus(this.summary, this.orphans, this._directories, this._sources, this.owner, this.frameCache);
  final Map<String, Object?> summary;
  final List<OrphanAudioFile> orphans;
  final Map<String, FileStat> _directories;
  final List<_Metadata> _sources;
  final String owner;
  final OrphanAudioFrameCache frameCache;
  bool isDocumentsFile(OrphanAudioFile file) => path.dirname(file.filePath) == _directories.keys.first;
  bool get complete => summary['orphan_census_complete'] == true;
  bool get hasLocalOnlyHistory => summary['local_only_history'] != false;

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
            stat.modified.microsecondsSinceEpoch != source.modifiedUs ||
            stat.changed.microsecondsSinceEpoch != source.changedUs) {
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
  OrphanAudioFile(this.filePath, this.bytes, this.modifiedUs, this.changedUs, this.classification, this.info,
      this.frames, this.clockRun);
  final String filePath;
  final int bytes, modifiedUs, changedUs, frames;
  final String classification;
  final BatchRecordingInfo? info;
  final String? clockRun;
  bool unchanged() {
    try {
      if (FileSystemEntity.typeSync(filePath, followLinks: false) != FileSystemEntityType.file) return false;
      // omi-perf-allow: sync-file-io -- At most 200 adopted-file stamps per pass, with no await between identity validation and admission.
      final stat = FileStat.statSync(filePath);
      return stat.size == bytes &&
          stat.modified.microsecondsSinceEpoch == modifiedUs &&
          stat.changed.microsecondsSinceEpoch == changedUs;
    } catch (_) {
      return false;
    }
  }
}

const orphanRecoveryWindowSeconds = 28 * 86400;
const orphanAudioClasses = ['working', 'unparseable', 'recoverable', 'expired', 'owner_unknown'];

({List<OrphanAudioFile> files, OrphanAudioFrameCache cache, int reads, int hits}) _classifyOrphans(
    List<_Metadata> candidates, int phoneSeconds, bool owned, OrphanAudioFrameCache frameCache) {
  final entries = <String, _CachedAudioFrames>{};
  var reads = 0, hits = 0;
  final files = candidates.map((file) {
    final name = path.basename(file.filePath);
    final working = name.endsWith('.part') ||
        name.endsWith('.torn') ||
        name.startsWith('audio_omibatch') ||
        name.startsWith('audio_omimobilebatch');
    BatchRecordingInfo? info;
    String? clockRun;
    var frames = 0;
    var classification = 'working';
    if (!working) {
      // BatchRecordingInfo is intentionally forgiving for legacy native intake;
      // unattended orphan adoption additionally requires the complete mono shape.
      // Strip only known producer suffixes for the legacy parser. Preserve the
      // original path and estimated-clock provenance on the recovered row.
      final shape = RegExp(
              r'^(audio_.+_(?:opus(?:_fs(?:160|320))?|pcm16|pcm8)_\d+_1_fs(\d+))(?:_r\d+_\d+)?(?:_u\d+)?(?:_clke([0-9a-z]{1,32}))?_\d+(?:\.\d{1,6})?(?:_u\d{1,9})?\.bin$')
          .firstMatch(name);
      if (shape != null) {
        final time = _filenameTime(name);
        if (time != null) {
          // Preserve the exact original filename for the uploader. The ledger's
          // integer timer uses the same conservative floor as inventory clocks.
          final normalized = '${shape.group(1)}_$time.bin';
          try {
            info = BatchRecordingInfo.fromFileName(normalized);
            clockRun = shape.group(3);
          } catch (_) {/* Unparseable metadata retains the original bytes. */}
        }
      }
      final suffixFrame = shape?.group(2);
      if (info != null &&
          int.tryParse(suffixFrame ?? '') == info.frameSize &&
          info.sampleRate == info.frameSize * info.codec.getFramesPerSecond() &&
          info.sampleRate > 0 &&
          info.frameSize > 0 &&
          info.timerStart >= 1704067200 &&
          info.timerStart <= phoneSeconds &&
          phoneSeconds <= 0x7fffffff) {
        final previous = frameCache._entries[file.filePath];
        if (previous != null && previous.matches(file)) {
          frames = previous.frames;
          hits++;
        } else {
          frames = _strictFrameCount(file.filePath, file.bytes);
          reads++;
        }
        // Zero also represents transient I/O failure; retry it next census.
        if (frames > 0) entries[file.filePath] = _CachedAudioFrames(file, frames);
      }
      classification = frames <= 0
          ? 'unparseable'
          : !owned
              ? 'owner_unknown'
              : phoneSeconds - info!.timerStart > orphanRecoveryWindowSeconds
                  ? 'expired'
                  : 'recoverable';
    }
    return OrphanAudioFile(
        file.filePath, file.bytes, file.modifiedUs, file.changedUs, classification, info, frames, clockRun);
  }).toList();
  return (files: files, cache: OrphanAudioFrameCache._(entries), reads: reads, hits: hits);
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
