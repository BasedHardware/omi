import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/batch_recording.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/waveform_utils.dart';

/// Owns the batch/offline-mode recordings captured natively to the phone.
///
/// Design (fieldy-style): the recordings directory is the queue and the `.bin`
/// files are the single source of truth — there is no WAL/offline-sync entry.
/// The list is derived by scanning the dir; uploading a recording turns it into
/// a conversation. Only the truly-stateless leaf helpers are reused:
/// [uploadLocalFilesV2] (the `/v2/sync-local-files` call), [fetchSyncJobStatus]
/// (reconcile), and [AudioPlayerUtils] (opus playback, fed a transient [Wal]).
///
/// Robustness beyond fieldy: an in-flight upload's `jobId` is persisted in a
/// tiny sidecar (SharedPreferences) so an app-kill mid-processing reconciles on
/// next launch, and the local file is deleted only once the job reports
/// `completed` (never fire-and-forget).
/// Result of a user-triggered [LocalRecordingsProvider.upload], so the UI can
/// react (fair-use message, generic error, or navigate away) instead of guessing.
enum LocalUploadOutcome { started, fairUseLimited, backendBusy, failed, busy }

class LocalRecordingsProvider extends ChangeNotifier {
  final AudioPlayerUtils _audio = AudioPlayerUtils.instance;

  // Sidecar: fileName -> server jobId for recordings uploaded but not yet
  // confirmed transcribed. Persisted as JSON under [_jobsPrefKey].
  static const String _jobsPrefKey = 'localRecordingJobs';
  Map<String, String> _jobs = {};

  // Exact per-file duration (seconds), computed once by walking the frame
  // prefixes. Finalized .bin files are immutable, so this is cached by fileName.
  final Map<String, int> _secondsByFile = {};

  List<LocalRecording> _recordings = [];
  List<LocalRecording> get recordings => _recordings;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  // Single-flight upload guard + the file currently uploading (for its state).
  bool _isUploading = false;
  String? _uploadingName;
  String? _failedName; // last upload that errored (file intact, retriable)

  Timer? _reconcileTimer;
  bool _disposed = false;

  ConversationProvider? _conversationProvider;

  LocalRecordingsProvider() {
    _audio.addListener(_onAudioChanged);
    // Native batch writer → Dart on file finalize (rotation/gap/stop) so a
    // rotated recording surfaces without waiting for a BLE disconnect.
    BleBridge.instance.addBatchRecordingFinalizedListener(_onRecordingFinalized);
    _jobs = _loadJobs();
    refresh();
    if (_jobs.isNotEmpty) {
      _startReconcileTimer();
      _reconcile();
    }
  }

  /// Wired from main.dart so a finished transcription can surface its
  /// conversation into the list the user is looking at.
  void setConversationProvider(ConversationProvider provider) {
    _conversationProvider = provider;
  }

  void _onRecordingFinalized(String fileName) {
    refresh().then((_) {
      PlatformManager.instance.analytics.transcribeLaterRecordingCaptured(durationSeconds: _secondsByFile[fileName]);
    });
  }

  // ───────────────────────── scanning ─────────────────────────

  Future<Directory?> _dir() async {
    final configured = SharedPreferencesUtil().getString('batchAudioDir');
    if (configured.isNotEmpty) return Directory(configured);
    return getApplicationDocumentsDirectory();
  }

  LocalRecordingState _stateFor(String name) {
    if (name == _uploadingName) return LocalRecordingState.uploading;
    if (_jobs.containsKey(name)) return LocalRecordingState.processing;
    if (name == _failedName) return LocalRecordingState.failed;
    return LocalRecordingState.pending;
  }

  /// Rescan the recordings directory and rebuild [recordings]. Cheap and
  /// idempotent — call it on app foreground, after a BLE disconnect, etc.
  Future<void> refresh() async {
    _isLoading = true;
    notifyListeners();
    try {
      final dir = await _dir();
      if (dir == null || !await dir.exists()) {
        _recordings = [];
        return;
      }
      final list = <LocalRecording>[];
      final seen = <String>{};
      for (final entity in dir.listSync().whereType<File>()) {
        final name = entity.path.split('/').last;
        // Only batch recordings (audio_omibatch* — includes the omibatchlimitless
        // marker) — never offline-sync WAL flushes, which share this directory and
        // the same audio_*.bin naming.
        if (!name.startsWith('audio_$batchRecordingDevice') || !name.endsWith('.bin')) continue;
        final size = await entity.length();
        seen.add(name);
        final rec = LocalRecording.fromFile(
          fileName: name,
          filePath: entity.path,
          sizeBytes: size,
          seconds: await _durationSeconds(name, entity.path, size),
          jobId: _jobs[name],
          state: _stateFor(name),
        );
        if (rec != null) list.add(rec);
      }
      list.sort((a, b) => b.timerStart.compareTo(a.timerStart));
      _recordings = list;
      _secondsByFile.removeWhere((k, _) => !seen.contains(k));
    } catch (e) {
      Logger.error('LocalRecordings: scan failed: $e');
    } finally {
      _isLoading = false;
      // Resume polling if recordings are still awaiting transcription (e.g. the
      // timer was dropped while backgrounded and we just resumed).
      if (_jobs.isNotEmpty) _startReconcileTimer();
      if (!_disposed) notifyListeners();
    }
  }

  /// Exact recording duration (seconds), computed once per file by counting the
  /// length-prefixed frames (`[4-byte LE len][frame]`) and multiplying by the
  /// per-frame duration — the byte-size estimate is unreliable for VBR opus.
  /// Cached because finalized files never change; falls back to the size estimate
  /// if the file can't be read.
  Future<int> _durationSeconds(String name, String path, int sizeBytes) async {
    final cached = _secondsByFile[name];
    if (cached != null) return cached;
    final info = BatchRecordingInfo.fromFileName(name);
    if (info == null) return 1;
    int seconds;
    try {
      seconds = info.secondsFromFrameCount(await countBatchRecordingFrames(path));
    } catch (e) {
      // Transient read failure (e.g. file mid-write): return the rough estimate but
      // don't cache it, so the next refresh retries the exact frame count.
      Logger.error('LocalRecordings: duration scan failed for $name: $e');
      return info.estimateSeconds(sizeBytes);
    }
    _secondsByFile[name] = seconds;
    return seconds;
  }

  LocalRecording? getById(String id) {
    for (final r in _recordings) {
      if (r.id == id) return r;
    }
    return null;
  }

  // ───────────────────── upload / transcribe ─────────────────────

  /// Upload a single recording → backend transcribes it into a conversation.
  /// 200 fast-path: delete the file + surface the conversation immediately.
  /// 202 queued: persist the jobId and let the reconciler finish it.
  Future<LocalUploadOutcome> upload(LocalRecording rec) async {
    if (_isUploading || rec.isBusy) return LocalUploadOutcome.busy;
    _isUploading = true;
    _uploadingName = rec.fileName;
    _failedName = null;
    await refresh();

    var outcome = LocalUploadOutcome.started;
    try {
      final file = File(rec.filePath);
      if (!file.existsSync()) {
        Logger.error('LocalRecordings: file missing on upload: ${rec.fileName}');
        _failedName = rec.fileName;
        outcome = LocalUploadOutcome.failed;
      } else {
        final lane = syncUploadLaneForTimestamp(
          rec.timerStart,
          DateTime.now().millisecondsSinceEpoch ~/ 1000,
          hasServerCaptureProof: false,
        );
        final result = await SyncUploadGate.instance.upload([file], lane: lane);

        if (result.completed != null) {
          await _deleteFileOnly(rec.fileName);
          await _surface(result.completed!.newConversationIds, result.completed!.updatedConversationIds);
        } else if (result.jobId != null) {
          _jobs[rec.fileName] = result.jobId!;
          await _saveJobs();
          _startReconcileTimer();
        }
      }
    } on SyncRateLimitedException catch (e) {
      outcome = e.kind == SyncRateLimitKind.fairUse
          ? LocalUploadOutcome.fairUseLimited
          : LocalUploadOutcome.backendBusy;
    } catch (e) {
      _failedName = rec.fileName;
      Logger.error('LocalRecordings: upload failed for ${rec.fileName}: $e');
      outcome = LocalUploadOutcome.failed;
    } finally {
      _isUploading = false;
      _uploadingName = null;
      await refresh();
    }
    if (outcome == LocalUploadOutcome.started) {
      PlatformManager.instance.analytics.transcribeLaterRecordingProcessed();
    }
    return outcome;
  }

  // ───────────────────────── reconcile ─────────────────────────

  void _startReconcileTimer() {
    _reconcileTimer ??= Timer.periodic(const Duration(seconds: 15), (_) => _reconcile());
  }

  void _stopReconcileTimer() {
    _reconcileTimer?.cancel();
    _reconcileTimer = null;
  }

  /// Poll every pending job once. `completed` → delete file + surface the
  /// conversation. `failed`/`notFound` → drop the job; the file stays on disk
  /// so it reverts to a pending, retriable recording.
  Future<void> _reconcile() async {
    if (_jobs.isEmpty) {
      _stopReconcileTimer();
      return;
    }
    final newIds = <String>[];
    final updIds = <String>[];
    bool changed = false;

    for (final entry in Map<String, String>.from(_jobs).entries) {
      final name = entry.key;
      final jobId = entry.value;
      SyncJobFetch fetch;
      try {
        fetch = await fetchSyncJobStatus(jobId);
      } catch (_) {
        continue; // transient — retry next tick
      }
      switch (fetch.outcome) {
        case SyncJobFetchOutcome.transient:
          break;
        case SyncJobFetchOutcome.notFound:
          _jobs.remove(name);
          changed = true;
          break;
        case SyncJobFetchOutcome.ok:
          final s = fetch.status!;
          if (!s.isTerminal) break;
          if (s.result != null) {
            newIds.addAll(s.result!.newConversationIds);
            updIds.addAll(s.result!.updatedConversationIds);
          }
          if (s.status == 'completed') {
            await _deleteFileOnly(name);
          }
          // completed or failed: stop tracking. On failure the file is kept
          // (only `completed` deletes it) so the recording becomes pending again.
          _jobs.remove(name);
          changed = true;
          break;
      }
    }

    if (changed) await _saveJobs();
    if (newIds.isNotEmpty || updIds.isNotEmpty) await _surface(newIds, updIds);
    await refresh();
    if (_jobs.isEmpty) _stopReconcileTimer();
  }

  Future<void> _surface(List<String> newIds, List<String> updatedIds) async {
    if (_conversationProvider == null) return;
    if (newIds.isEmpty && updatedIds.isEmpty) return;
    try {
      final pointers = await ConversationSyncUtils.processConversationIds(
        newConversationIds: newIds,
        updatedConversationIds: updatedIds,
      );
      for (final p in pointers) {
        _conversationProvider!.upsertConversation(p.conversation);
      }
    } catch (e) {
      Logger.error('LocalRecordings: surfacing conversations failed: $e');
    }
  }

  // ───────────────────────── delete ─────────────────────────

  /// Delete a recording the user no longer wants. Stops playback first.
  Future<void> delete(LocalRecording rec) async {
    if (isPlaying(rec)) {
      await togglePlayback(rec);
    }
    await _deleteFileOnly(rec.fileName);
    if (_jobs.remove(rec.fileName) != null) await _saveJobs();
    await refresh();
  }

  Future<void> _deleteFileOnly(String fileName) async {
    try {
      final dir = await _dir();
      if (dir == null) return;
      final file = File('${dir.path}/$fileName');
      if (file.existsSync()) await file.delete();
    } catch (e) {
      Logger.error('LocalRecordings: delete failed for $fileName: $e');
    }
  }

  // ───────────────────── playback / waveform ─────────────────────

  /// A throwaway [Wal] used only to drive [AudioPlayerUtils] (opus decode +
  /// playback). Never stored anywhere. `filePath` is the relative name, which
  /// `Wal.getFilePath` resolves against the app documents dir (== batchAudioDir).
  Wal _walFor(LocalRecording r) => Wal(
    timerStart: r.timerStart,
    codec: r.codec,
    seconds: r.seconds,
    sampleRate: 16000,
    channel: 1,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    filePath: r.fileName,
    device: batchRecordingDevice,
  );

  String? get currentPlayingId => _audio.currentPlayingId;
  bool get isProcessingAudio => _audio.isProcessingAudio;
  Duration get currentPosition => _audio.currentPosition;
  Duration get totalDuration => _audio.totalDuration;
  double get playbackProgress => _audio.playbackProgress;

  bool isPlaying(LocalRecording r) => _audio.isPlaying(_walFor(r).id);
  bool canPlay(LocalRecording r) => _audio.canPlayOrShare(_walFor(r));
  Future<void> togglePlayback(LocalRecording r) => _audio.togglePlayback(_walFor(r));

  bool _isPreparingShare = false;
  bool get isPreparingShare => _isPreparingShare;

  Future<void> share(LocalRecording r) async {
    if (_isPreparingShare) return;
    final wal = _walFor(r);
    _isPreparingShare = true;
    notifyListeners();
    try {
      await Future.delayed(const Duration(milliseconds: 16));
      await _audio.ensureAudioFileExists(wal);
    } catch (e) {
      Logger.error('LocalRecordings: preparing share failed for ${r.fileName}: $e');
    } finally {
      _isPreparingShare = false;
      if (!_disposed) notifyListeners();
    }
    try {
      await _audio.shareAsAudio(wal);
    } catch (e) {
      Logger.error('LocalRecordings: share failed for ${r.fileName}: $e');
    }
  }

  Future<void> seekTo(Duration position) => _audio.seekToPosition(position);
  Future<void> skipForward() => _audio.skipForward();
  Future<void> skipBackward() => _audio.skipBackward();

  Future<List<double>?> getWaveform(LocalRecording r) async {
    final wal = _walFor(r);
    String? wavPath = _audio.getCachedAudioPath(wal.id);
    if (wavPath == null && _audio.canPlayOrShare(wal)) {
      wavPath = await _audio.ensureAudioFileExists(wal);
    }
    return compute(_generateWaveform, {'id': wal.id, 'path': wavPath});
  }

  static Future<List<double>?> _generateWaveform(Map<String, dynamic> params) {
    return WaveformUtils.generateWaveform(params['id'] as String, params['path'] as String?);
  }

  // ───────────────────────── sidecar ─────────────────────────

  Map<String, String> _loadJobs() {
    try {
      final raw = SharedPreferencesUtil().getString(_jobsPrefKey);
      if (raw.isEmpty) return {};
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      return decoded.map((k, v) => MapEntry(k, v.toString()));
    } catch (_) {
      return {};
    }
  }

  Future<void> _saveJobs() async {
    await SharedPreferencesUtil().saveString(_jobsPrefKey, jsonEncode(_jobs));
  }

  void _onAudioChanged() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _stopReconcileTimer();
    BleBridge.instance.removeBatchRecordingFinalizedListener(_onRecordingFinalized);
    _audio.removeListener(_onAudioChanged);
    super.dispose();
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
