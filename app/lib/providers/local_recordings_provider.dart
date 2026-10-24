import 'dart:io';
import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/audio_player_utils.dart';
import 'package:omi/utils/conversation_sync_utils.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/waveform_utils.dart';

enum LocalUploadOutcome { started, fairUseLimited, backendBusy, failed, busy }

/// Home's view of explicit Transcribe Later custody. No queue, scanner or uploader.
class LocalRecordingsProvider extends ChangeNotifier {
  LocalRecordingsProvider(
      {LocalWalSyncImpl? ledger,
      bool initialize = true,
      Future<void> Function(SyncLocalFilesResponse)? surfaceConversations})
      : _ledgerOverride = ledger,
        _surfaceOverride = surfaceConversations {
    _audio.addListener(_onAudioChanged);
    if (initialize) {
      _subscribed = true;
      _ledger.heldRevision.addListener(_onLedgerChanged);
      _ledger.conversationCompletions.addListener(_onConversationsCompleted);
      refresh();
    }
  }
  final LocalWalSyncImpl? _ledgerOverride;
  LocalWalSyncImpl get _ledger => _ledgerOverride ?? ServiceManager.instance().wal.getSyncs().phone as LocalWalSyncImpl;
  final AudioPlayerUtils _audio = AudioPlayerUtils.instance;
  bool _subscribed = false;
  bool _disposed = false;
  int _generation = 0;
  bool _isLoading = false;
  bool get isLoading => _isLoading;
  List<LocalRecording> _recordings = [];
  List<LocalRecording> get recordings => _recordings;
  final Map<String, Wal> _rows = {};
  final Future<void> Function(SyncLocalFilesResponse)? _surfaceOverride;
  SyncLocalFilesResponse? _lastCompletion;
  ConversationProvider? _conversationProvider;
  void setConversationProvider(ConversationProvider provider) {
    if (identical(_conversationProvider, provider)) return;
    _conversationProvider = provider;
    _onConversationsCompleted();
  }

  void _onConversationsCompleted() {
    if (_disposed || (_conversationProvider == null && _surfaceOverride == null)) return;
    final result = _ledger.conversationCompletions.value;
    if (result == null || identical(result, _lastCompletion)) return;
    _lastCompletion = result;
    unawaited(_surface(result));
  }

  Future<void> _surface(SyncLocalFilesResponse result) async {
    if (result.newConversationIds.isEmpty && result.updatedConversationIds.isEmpty) return;
    final session = _ledger.sessionGeneration;
    final provider = _conversationProvider;
    try {
      final surface = _surfaceOverride;
      if (surface != null) {
        await surface(result);
        return;
      }
      if (provider == null) return;
      final pointers = await ConversationSyncUtils.processConversationIds(
          newConversationIds: result.newConversationIds, updatedConversationIds: result.updatedConversationIds);
      if (_disposed || session != _ledger.sessionGeneration || !identical(provider, _conversationProvider)) return;
      for (final pointer in pointers) {
        provider.upsertConversation(pointer.conversation);
      }
    } catch (e) {
      Logger.error('LocalRecordings: surfacing confirmed conversations failed: $e');
    }
  }

  void _onLedgerChanged() {
    _readLedger();
  }

  Future<void>? _refreshInFlight;
  Future<void> refresh() {
    final active = _refreshInFlight;
    if (active != null) return active;
    final pass = _refresh();
    _refreshInFlight = pass;
    return pass.whenComplete(() {
      if (identical(_refreshInFlight, pass)) _refreshInFlight = null;
    });
  }

  Future<void> _refresh() async {
    if (!_subscribed && _ledgerOverride == null) return;
    _isLoading = true;
    try {
      await _ledger.intakeNativeRecordings();
    } catch (e) {
      Logger.error('LocalRecordings: refresh deferred: $e');
    } finally {
      await _readLedger();
      _isLoading = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> _readLedger() async {
    final generation = ++_generation;
    final wals = await _ledger.getAllWals();
    final rows = <String, Wal>{};
    final recordings = <LocalRecording>[];
    for (final wal in wals) {
      if (wal.ownerUid == null || wal.filePath == null) continue;
      rows[wal.filePath!] = wal;
      if (!wal.holdForUser || wal.status == WalStatus.synced) continue;
      final path = await Wal.getFilePath(wal.filePath);
      if (path == null) continue;
      var bytes = 0;
      try {
        bytes = await File(path).length();
      } catch (_) {}
      rows[wal.filePath!] = wal;
      recordings.add(LocalRecording.fromWal(wal, filePath: path, sizeBytes: bytes));
    }
    if (_disposed || generation != _generation) return;
    recordings.sort((a, b) => b.timerStart.compareTo(a.timerStart));
    _rows
      ..clear()
      ..addAll(rows);
    _recordings = recordings;
    notifyListeners();
  }

  LocalRecording? getById(String id) {
    for (final rec in _recordings) {
      if (rec.id == id) return rec;
    }
    return null;
  }

  Wal? _walFor(LocalRecording r) => _rows[r.fileName];

  Future<LocalUploadOutcome> upload(LocalRecording rec) async {
    final wal = _rows[rec.fileName];
    if (wal == null || wal.isSyncing || wal.status == WalStatus.uploaded) return LocalUploadOutcome.busy;
    final session = _ledger.sessionGeneration;
    try {
      final result = await _ledger.syncWal(wal: wal);
      if (_disposed || session != _ledger.sessionGeneration) return LocalUploadOutcome.busy;
      final accepted = wal.status == WalStatus.uploaded || wal.status == WalStatus.synced;
      if (accepted) {
        unawaited(RecordingTransferCoordinator.instance.wake(WakeTrigger.userRetry));
      }
      if (result != null) await _surface(result);
      return accepted ? LocalUploadOutcome.started : LocalUploadOutcome.failed;
    } on SyncRateLimitedException catch (e) {
      return switch (e.kind) {
        SyncRateLimitKind.fairUse => LocalUploadOutcome.fairUseLimited,
        SyncRateLimitKind.backendCapacity => LocalUploadOutcome.backendBusy,
        SyncRateLimitKind.edgeThrottle => LocalUploadOutcome.busy,
      };
    } on SyncOfflineQueueQuarantinedException {
      return LocalUploadOutcome.backendBusy;
    } catch (e) {
      Logger.error('LocalRecordings: manual sync failed: $e');
      return LocalUploadOutcome.failed;
    } finally {
      await _readLedger();
    }
  }

  Future<void> delete(LocalRecording rec) async {
    final wal = _rows[rec.fileName];
    if (wal == null) return;
    if (isPlaying(rec)) await togglePlayback(rec);
    await _ledger.deleteWal(wal);
    await _readLedger();
  }

  String? get currentPlayingId => _audio.currentPlayingId;
  bool get isProcessingAudio => _audio.isProcessingAudio;
  Duration get currentPosition => _audio.currentPosition;
  Duration get totalDuration => _audio.totalDuration;
  double get playbackProgress => _audio.playbackProgress;

  bool isPlaying(LocalRecording r) {
    final wal = _walFor(r);
    return wal != null && _audio.isPlaying(wal.id);
  }

  bool canPlay(LocalRecording r) {
    final wal = _walFor(r);
    return wal != null && _audio.canPlayOrShare(wal);
  }

  Future<void> togglePlayback(LocalRecording r) async {
    final wal = _walFor(r);
    if (wal != null) await _audio.togglePlayback(wal);
  }

  bool _isPreparingShare = false;
  bool get isPreparingShare => _isPreparingShare;

  Future<void> share(LocalRecording r) async {
    if (_isPreparingShare) return;
    final wal = _walFor(r);
    if (wal == null) return;
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
    if (wal == null) return null;
    String? wavPath = _audio.getCachedAudioPath(wal.id);
    if (wavPath == null && _audio.canPlayOrShare(wal)) {
      wavPath = await _audio.ensureAudioFileExists(wal);
    }
    return compute(_generateWaveform, {'id': wal.id, 'path': wavPath});
  }

  static Future<List<double>?> _generateWaveform(Map<String, dynamic> params) {
    return WaveformUtils.generateWaveform(params['id'] as String, params['path'] as String?);
  }

  void clearUserData() {
    _generation++;
    _rows.clear();
    _recordings = [];
    _lastCompletion = null;
    if (!_disposed) notifyListeners();
  }

  void _onAudioChanged() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    if (_subscribed) {
      _ledger.heldRevision.removeListener(_onLedgerChanged);
      _ledger.conversationCompletions.removeListener(_onConversationsCompleted);
    }
    _audio.removeListener(_onAudioChanged);
    super.dispose();
  }
}
