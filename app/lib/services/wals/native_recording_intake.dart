import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/native_batch_geolocation.dart';
import 'package:omi/services/capture/watch_recording_receipt.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/watch_live_coverage.dart';
import 'package:omi/services/experiments/watch_copy_dedupe.dart';
import 'package:omi/utils/batch_recording.dart';
import 'package:omi/utils/off_ui_isolate.dart';
import 'legacy_recording_owners.dart';
import 'native_custody_diagnostics.dart';

Future<Directory> nativeRecordingDirectory() async {
  final configured = SharedPreferencesUtil().getString('batchAudioDir');
  final documents = await getApplicationDocumentsDirectory();
  if (configured.isNotEmpty && path.normalize(path.absolute(configured)) != path.normalize(documents.absolute.path)) {
    // A stale absolute path, e.g. after an iOS update moved the app container. Ledger paths resolve
    // against documents, so scan there and repoint native capture at it rather than halting intake.
    nativeCustodyObserved(NativeCustodyObservedOutcome.directoryMismatch);
    await SharedPreferencesUtil().saveString('batchAudioDir', documents.path);
  }
  return documents;
}

/// The only native-file discovery and migration path. Serialized scans prevent
/// finalize/resume/receipt races, while the ledger persists file-name identity.
class NativeRecordingIntake {
  NativeRecordingIntake(this.ledger,
      {Future<Directory> Function()? directory,
      Future<bool> Function()? dedupeOff,
      WatchLiveCoverage? coverage,
      DateTime Function()? now})
      : _now = now ?? DateTime.now,
        directory = directory ?? nativeRecordingDirectory,
        coverage = coverage ?? WatchLiveCoverage(getApplicationDocumentsDirectory),
        dedupeOff = dedupeOff ?? WatchCopyDedupePolicy.keepRecoveryCopies;
  static const unboundWatchReceiptTimeout = Duration(minutes: 30);
  final DateTime Function() _now;
  final LocalWalSyncImpl ledger;
  final Future<Directory> Function() directory;
  final WatchLiveCoverage coverage;
  final Future<bool> Function() dedupeOff;
  Future<void> _tail = Future.value();

  Future<void> scan() {
    final generation = ledger.sessionGeneration;
    final uid = SharedPreferencesUtil().uid;
    final work = _tail.then((_) => _scan(generation, uid));
    _tail = work.catchError((_) {});
    return work;
  }

  Future<void> _scan(int generation, String uid) async {
    if (uid.isEmpty || generation != ledger.sessionGeneration) return;
    final dir = await directory();
    if (!await dir.exists()) return;
    final ownersFile = File('${dir.path}/omibatch_owners.json');
    final owners = await LegacyRecordingOwners.read(dir);
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('localRecordingJobs') ?? '';
    Map<String, String> jobs;
    try {
      jobs = raw.isEmpty ? <String, String>{} : await _decodeLegacyMap(raw);
    } catch (_) {
      // Preserve the evidence before retiring the poison pill. Emit only on quarantine.
      await prefs.setString('localRecordingJobsCorrupt', raw);
      await prefs.remove('localRecordingJobs');
      nativeCustodyObserved(NativeCustodyObservedOutcome.legacyJobsQuarantined);
      jobs = {};
    }
    final files = <String, File>{};
    await for (final entry in dir.list()) {
      if (entry is! File) continue;
      final name = entry.path.split('/').last;
      if (name.startsWith('audio_omibatch') && name.endsWith('.bin')) files[name] = entry;
    }
    // A missing local file with a queued job still belongs to the shared poller.
    for (final name in jobs.keys) {
      files.putIfAbsent(name, () => File('${dir.path}/$name'));
    }
    var complete = true;
    var watchCheckpointed = false;
    for (final entry in files.entries) {
      if (generation != ledger.sessionGeneration || uid != SharedPreferencesUtil().uid) return;
      final name = entry.key, file = entry.value;
      final info = BatchRecordingInfo.fromFileName(name);
      if (info == null || info.isOverflow) continue;
      final existing = ledger.nativeWalForFileName(name);
      if (existing != null) {
        // A previous save may have failed: migration removes its source only
        // after the ledger confirms this exact entry is durably indexed.
        if (jobs.containsKey(name) && existing.status == WalStatus.miss) {
          existing.status = WalStatus.uploaded;
          existing.jobId = jobs[name];
          existing.holdForUser = info.holdForUser;
        }
        if (jobs.containsKey(name) || !await ledger.nativeWalIsDurable(existing, generation)) {
          await ledger.persistRetryMetadata(existing);
        }
        jobs.remove(name);
        continue;
      }
      final owner = info.isWatch
          ? await watchRecordingOwner(dir, name)
          : await owners.resolve(file, name, uid, timerStart: info.timerStart);
      if (owner == null || owner.isEmpty) {
        complete = false;
        continue;
      }
      if (info.isWatch && owner == uid && !watchCheckpointed) {
        await ledger.checkpointWatchAudio();
        await ledger.refreshWatchCoverage(coverage);
        watchCheckpointed = true;
      }
      final exists = await file.exists();
      final size = exists ? await file.length() : 0;
      final frames = exists ? await countBatchRecordingFrames(file.path) : 0;
      if (size == 0 && !jobs.containsKey(name)) continue;
      final duration = frames * info.frameSize / info.sampleRate;
      bool off = true;
      if (info.isWatch && owner == uid && !jobs.containsKey(name)) {
        try {
          off = await dedupeOff();
        } catch (_) {/* keep on flag failure */}
        if (!off &&
            frames > 0 &&
            await coverage.covers(owner, info.timerStart.toDouble(), info.timerStart + duration)) {
          if (generation != ledger.sessionGeneration || uid != SharedPreferencesUtil().uid) return;
          // The native receipt is deliberately retained: retransmission stays acknowledged.
          await file.delete();
          nativeCustodyObserved(NativeCustodyObservedOutcome.watchDeleted);
          continue;
        }
        if (!off &&
            frames > 0 &&
            await coverage.covers(owner, info.timerStart.toDouble(), info.timerStart + duration,
                serverReachable: false)) {
          final receipt = await File('${dir.path}/.watch-receipts/$name').stat();
          if (_now().difference(receipt.modified) < unboundWatchReceiptTimeout) {
            nativeCustodyObserved(NativeCustodyObservedOutcome.watchDeferred);
            complete = false;
            continue;
          }
        }
      }
      if (!await ledger.ensureStorageAdmission(bytes: size, admittedGeneration: generation)) {
        complete = false;
        continue;
      }
      final job = jobs[name];
      final wal = Wal(
          timerStart: info.timerStart,
          codec: info.codec,
          sampleRate: info.sampleRate,
          seconds: info.secondsFromFrameCount(frames),
          totalFrames: frames,
          storage: WalStorage.disk,
          status: job == null ? WalStatus.miss : WalStatus.uploaded,
          filePath: name,
          device: info.marker,
          ownerUid: owner,
          holdForUser: info.holdForUser,
          jobId: job,
          geolocation: await readNativeBatchGeolocation(file.path))
        ..frameSize = info.frameSize;
      try {
        await ledger.addExternalWal(wal, admittedGeneration: generation);
        if (!await ledger.nativeWalIsDurable(wal, generation)) {
          complete = false;
          continue;
        }
        jobs.remove(name);
      } catch (_) {
        ledger.releaseStorageAdmission(size);
        rethrow;
      }
    }
    if (generation != ledger.sessionGeneration || uid != SharedPreferencesUtil().uid) return;
    if (complete && jobs.isEmpty && owners.corruptModified == null) {
      await prefs.remove('localRecordingJobs');
      if (await ownersFile.exists()) await ownersFile.delete();
    }
  }
}

/// Counts complete length-prefixed frames (`[4-byte LE length][payload]`) in a
/// batch `.bin` file. Reads in fixed 64 KB chunks so a long recording is never
/// loaded whole into memory, and only counts a frame once its full payload is
/// present — a truncated tail frame (e.g. from a crash-recovered file) is not
/// counted, keeping the duration exact.
Future<int> countBatchRecordingFrames(String path) async {
  final raf = await File(path).open();
  try {
    const chunkSize = 64 * 1024;
    final buf = Uint8List(chunkSize);
    final header = Uint8List(4);
    var headerHave = 0; // bytes of the current 4-byte header collected (0..4)
    var remaining = 0; // payload bytes still to consume for the in-flight frame
    var inPayload = false;
    var frames = 0;
    while (true) {
      final read = await raf.readInto(buf, 0, chunkSize);
      if (read <= 0) break;
      var i = 0;
      while (i < read) {
        if (inPayload) {
          final avail = read - i;
          final skip = remaining < avail ? remaining : avail;
          i += skip;
          remaining -= skip;
          if (remaining == 0) {
            frames++; // full payload consumed — frame is complete
            inPayload = false;
          }
        } else {
          header[headerHave++] = buf[i++];
          if (headerHave == 4) {
            headerHave = 0;
            final len = header[0] | (header[1] << 8) | (header[2] << 16) | (header[3] << 24);
            if (len <= 0) return frames; // invalid/zero length — stop
            remaining = len;
            inPayload = true;
          }
        }
      }
    }
    return frames; // any in-flight (truncated) frame is intentionally not counted
  } finally {
    await raf.close();
  }
}

Future<Map<String, String>> _decodeLegacyMap(String raw) =>
    offUiIsolate(() => Map<String, String>.from(jsonDecode(raw) as Map), size: raw.length, threshold: 16 * 1024);
