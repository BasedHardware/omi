import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:flutter_sound/flutter_sound.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/utils/share_sheet.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/utils/audio/wal_wav_worker.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

export 'package:omi/utils/audio/wal_wav_worker.dart' show OpusFrameDecoder;

class AudioPlayerUtils extends ChangeNotifier {
  // Singleton pattern
  static final AudioPlayerUtils _instance = AudioPlayerUtils._internal();
  static AudioPlayerUtils get instance => _instance;

  factory AudioPlayerUtils() => _instance;

  AudioPlayerUtils._internal();

  FlutterSoundPlayer? _audioPlayer;
  String? _currentPlayingId;
  bool _isProcessingAudio = false;

  Duration _currentPosition = Duration.zero;
  Duration _totalDuration = Duration.zero;
  StreamSubscription<PlaybackDisposition>? _positionSubscription;

  final Map<String, String> _audioFileCache = {};
  String? _lastWorkerIsolateName;

  @visibleForTesting
  OpusFrameDecoder? debugOpusFrameDecoder;

  @visibleForTesting
  String? get lastWorkerIsolateName => _lastWorkerIsolateName;

  String? get currentPlayingId => _currentPlayingId;
  bool get isProcessingAudio => _isProcessingAudio;
  Duration get currentPosition => _currentPosition;
  Duration get totalDuration => _totalDuration;

  double get playbackProgress {
    if (_totalDuration.inMilliseconds <= 0) return 0.0;
    final progress = _currentPosition.inMilliseconds.toDouble() / _totalDuration.inMilliseconds.toDouble();
    return progress.clamp(0.0, 1.0);
  }

  /// Lazily initialize the audio player only when needed
  Future<void> _ensurePlayerInitialized() async {
    if (_audioPlayer != null) return;

    _audioPlayer = FlutterSoundPlayer();

    if (_audioPlayer != null && !_audioPlayer!.isOpen()) {
      await _audioPlayer!.openPlayer();
      // onProgress emits nothing unless a subscription interval is set (default 0ms).
      await _audioPlayer!.setSubscriptionDuration(const Duration(milliseconds: 100));
    }
  }

  bool isPlaying(String id) => _currentPlayingId == id;

  bool canPlayOrShare(Wal wal) {
    if (wal.storage == WalStorage.sdcard && wal.fileNum == -1) {
      return false;
    }
    return (wal.filePath != null && wal.filePath!.isNotEmpty) ||
        wal.data.isNotEmpty ||
        wal.storage == WalStorage.sdcard;
  }

  Future<void> togglePlayback(Wal wal) async {
    if (!canPlayOrShare(wal)) {
      Logger.error('AudioPlayerUtils: Audio file not available for playback, WAL ${wal.id}');
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.audioPlaybackUnavailable ?? 'Audio file is not available for playback',
      );
      return;
    }

    if (_isProcessingAudio) return;

    if (isPlaying(wal.id)) {
      await _stopPlayback();
      return;
    }

    await _startPlayback(wal);
  }

  Future<void> _stopPlayback() async {
    await _audioPlayer?.stopPlayer();
    _currentPlayingId = null;
    _currentPosition = Duration.zero;
    _totalDuration = Duration.zero;
    _positionSubscription?.cancel();
    notifyListeners();
  }

  Future<void> _startPlayback(Wal wal) async {
    _isProcessingAudio = true;
    _currentPosition = Duration.zero;
    _totalDuration = Duration.zero;
    notifyListeners();

    // Initialize player lazily on first use
    await _ensurePlayerInitialized();

    final audioFilePath = await _getOrCreateAudioFile(wal);
    if (audioFilePath == null) {
      _resetPlaybackState();
      Logger.error('AudioPlayerUtils: Unable to create playable audio file for WAL ${wal.id}');
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.audioPlaybackFailed ??
            'Unable to play audio. The file may be corrupted or missing.',
      );
      return;
    }

    _currentPlayingId = wal.id;
    _isProcessingAudio = false;

    await _audioPlayer?.startPlayer(fromURI: audioFilePath, whenFinished: () => _onPlaybackFinished());

    _setupPositionTracking(wal);
  }

  void _onPlaybackFinished() {
    Logger.debug('Audio playback finished');
    _resetPlaybackState();
  }

  void _resetPlaybackState() {
    _currentPlayingId = null;
    _currentPosition = Duration.zero;
    _totalDuration = Duration.zero;
    _isProcessingAudio = false;
    _positionSubscription?.cancel();
    notifyListeners();
  }

  void _setupPositionTracking(Wal wal) {
    _positionSubscription?.cancel();
    _positionSubscription = _audioPlayer?.onProgress?.listen((disposition) {
      if (_currentPlayingId == wal.id) {
        _currentPosition = disposition.position;
        _totalDuration = disposition.duration;
        notifyListeners();
      }
    });

    Timer.periodic(const Duration(milliseconds: 100), (timer) {
      if (_currentPlayingId != wal.id || !(_audioPlayer?.isPlaying ?? false)) {
        timer.cancel();
        return;
      }

      if (_totalDuration.inMilliseconds > 0) {
        final estimatedPosition = _currentPosition + const Duration(milliseconds: 100);
        if (estimatedPosition <= _totalDuration) {
          _currentPosition = estimatedPosition;
          notifyListeners();
        }
      }
    });

    _totalDuration = Duration(seconds: wal.seconds);
    notifyListeners();
  }

  Future<void> shareAsAudio(Wal wal) async {
    if (!canPlayOrShare(wal)) {
      throw Exception('Audio file not available for sharing');
    }

    final audioFilePath = await _getOrCreateAudioFile(wal, forSharing: true);
    if (audioFilePath == null) {
      throw Exception('Unable to create shareable audio file');
    }

    final result = await SharePlus.instance.share(ShareParams(
      files: [XFile(audioFilePath, mimeType: 'audio/wav')],
      text:
          'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toString().split('.')[0]}',
      // No widget to anchor to here; the fallback is only required to be non-zero.
      sharePositionOrigin: shareSheetOrigin(),
    ));

    if (result.status == ShareResultStatus.success) {
      Logger.debug('Audio file shared successfully');
    }
  }

  /// One WAV for a whole recording, oldest file first: a recording can be hundreds of short files,
  /// and sharing them one at a time is not practical. Files with no audio on the phone are left out.
  /// Per-file decode and WAV combination run in a background isolate so multi-hour recordings do
  /// not block the UI isolate; the caller opens the share sheet on the main isolate.
  @visibleForTesting
  Future<File?> writeRecordingWav(List<Wal> wals, {required String outputPath}) async {
    final sorted = [...wals]..sort((a, b) => a.timerStart.compareTo(b.timerStart));
    final playable = sorted.where(canPlayOrShare).toList();
    if (playable.isEmpty) return null;

    final tempDir = await getTemporaryDirectory();
    final items = <WalWavWorkItem>[];
    for (final wal in playable) {
      final item = await _prepareWalWavWorkItem(wal, tempDir: tempDir, forSharing: true);
      if (item != null) items.add(item);
    }
    if (items.isEmpty) return null;

    final result = await compute(
      buildRecordingWavInIsolate,
      RecordingWavJob(items: items, outputPath: outputPath, tempDirectory: tempDir.path),
      debugLabel: 'writeRecordingWav',
    );
    _lastWorkerIsolateName = result.isolateName;
    return result.path == null ? null : File(result.path!);
  }

  Future<void> shareRecordingAsAudio(List<Wal> wals) async {
    final start = wals.map((w) => w.timerStart).reduce((a, b) => a < b ? a : b);
    final tempDir = await getTemporaryDirectory();
    final shareDir = await tempDir.createTemp('omi-recording-');
    File? file;
    try {
      file = await writeRecordingWav(wals, outputPath: '${shareDir.path}/omi_recording_$start.wav');
    } catch (_) {
      await shareDir.delete(recursive: true);
      rethrow;
    }
    if (file == null) {
      await shareDir.delete(recursive: true);
      throw Exception('No audio on this phone for this recording');
    }
    await SharePlus.instance.share(ShareParams(
      files: [XFile(file.path, mimeType: 'audio/wav')],
      text: 'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(start * 1000).toString().split('.')[0]}',
      sharePositionOrigin: shareSheetOrigin(),
    ));
  }

  Future<WalWavWorkItem?> _prepareWalWavWorkItem(
    Wal wal, {
    required Directory tempDir,
    bool forSharing = false,
  }) async {
    final cacheKey = forSharing ? '${wal.id}_share' : wal.id;

    if (!forSharing && _audioFileCache.containsKey(cacheKey)) {
      final cachedPath = _audioFileCache[cacheKey]!;
      if (await File(cachedPath).exists()) {
        return WalWavWorkItem.cached(walId: wal.id, cachedWavPath: cachedPath);
      }
    }

    // Sharing reuses the already-decoded playback file (e.g. the one produced when
    // the waveform loaded) instead of decoding the whole recording again.
    if (forSharing) {
      final playbackCached = _audioFileCache[wal.id];
      if (playbackCached != null && await File(playbackCached).exists()) {
        return WalWavWorkItem.cached(walId: wal.id, cachedWavPath: playbackCached);
      }
    }

    // Resolve platform directories here; frame traversal and all byte conversion belong to the worker.
    String? audioFilePath;
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final path = await Wal.getFilePath(wal.filePath);
      if (path != null && await File(path).exists()) audioFilePath = path;
    }
    if (audioFilePath == null && wal.data.isEmpty) return null;

    final isOpus = wal.codec.isOpusSupported();
    final bitsPerSample = isOpus ? 16 : (wal.codec == BleAudioCodec.pcm16 ? 16 : 8);

    return WalWavWorkItem.decode(
      walId: wal.id,
      inputPath: audioFilePath,
      memoryFrames: audioFilePath == null ? wal.data : const [],
      tempDirectory: tempDir.path,
      isOpus: isOpus,
      sampleRate: wal.sampleRate,
      channels: wal.channel,
      bitsPerSample: bitsPerSample,
      opusFrameDecoder: debugOpusFrameDecoder,
    );
  }

  Future<String?> _getOrCreateAudioFile(Wal wal, {bool forSharing = false}) async {
    final cacheKey = forSharing ? '${wal.id}_share' : wal.id;
    final tempDir = await getTemporaryDirectory();
    final item = await _prepareWalWavWorkItem(wal, tempDir: tempDir, forSharing: forSharing);
    if (item == null) return null;
    if (item.cachedWavPath != null) return item.cachedWavPath;

    final result = await compute(
      decodeWalWorkItemInIsolate,
      item,
      debugLabel: 'decodeWalAudio',
    );
    _lastWorkerIsolateName = result.isolateName;
    final processedFilePath = result.path;

    if (processedFilePath != null && !forSharing) {
      _audioFileCache[cacheKey] = processedFilePath;
    }

    return processedFilePath;
  }

  Future<void> seekToPosition(Duration position) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      await _audioPlayer!.seekToPlayer(position);
      _currentPosition = position;
      notifyListeners();
    }
  }

  Future<void> skipForward({Duration duration = const Duration(seconds: 10)}) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      final newPosition = _currentPosition + duration;
      final clampedPosition = newPosition > _totalDuration ? _totalDuration : newPosition;
      await seekToPosition(clampedPosition);
    }
  }

  Future<void> skipBackward({Duration duration = const Duration(seconds: 10)}) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      final newPosition = _currentPosition - duration;
      final clampedPosition = newPosition < Duration.zero ? Duration.zero : newPosition;
      await seekToPosition(clampedPosition);
    }
  }

  String? getCachedAudioPath(String id) => _audioFileCache[id];

  Future<String?> ensureAudioFileExists(Wal wal) async {
    final cacheKey = wal.id;

    if (_audioFileCache.containsKey(cacheKey)) {
      final cachedPath = _audioFileCache[cacheKey]!;
      if (await File(cachedPath).exists()) {
        return cachedPath;
      }
    }

    return await _getOrCreateAudioFile(wal, forSharing: false);
  }

  @override
  void dispose() {
    _positionSubscription?.cancel();
    _audioPlayer?.closePlayer();
    super.dispose();
  }
}
