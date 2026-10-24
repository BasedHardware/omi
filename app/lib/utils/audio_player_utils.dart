import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:flutter_sound/flutter_sound.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:opus_flutter/opus_flutter.dart' as opus_flutter;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/utils/share_sheet.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/utils/audio/wav_combiner.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';

/// Parse length-prefixed binary frames: [4-byte LE uint32 length][payload] per frame.
/// Used by both Opus and PCM WAL binary files.
@visibleForTesting
List<Uint8List> parseLengthPrefixedFrames(Uint8List data) {
  List<Uint8List> frames = [];
  int offset = 0;

  while (offset < data.length - 4) {
    final lengthBytes = data.sublist(offset, offset + 4);
    final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
    offset += 4;

    if (offset + length > data.length) break;

    final frameData = data.sublist(offset, offset + length);
    frames.add(Uint8List.fromList(frameData));
    offset += length;
  }

  return frames;
}

@visibleForTesting
typedef OpusFrameDecoder = Int16List Function(Uint8List frame, int sampleRate, int channels);

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

    final result = await Share.shareXFiles(
      [XFile(audioFilePath)],
      text:
          'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toString().split('.')[0]}',
      // No widget to anchor to here; the fallback is only required to be non-zero.
      sharePositionOrigin: shareSheetOrigin(),
    );

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
    final items = <_WalWavWorkItem>[];
    for (final wal in playable) {
      final item = await _prepareWalWavWorkItem(wal, tempDir: tempDir, forSharing: true);
      if (item != null) items.add(item);
    }
    if (items.isEmpty) return null;

    final result = await compute(
      _buildRecordingWavInIsolate,
      _RecordingWavJob(items: items, outputPath: outputPath),
      debugLabel: 'writeRecordingWav',
    );
    _lastWorkerIsolateName = result.isolateName;
    return result.path == null ? null : File(result.path!);
  }

  Future<void> shareRecordingAsAudio(List<Wal> wals) async {
    final start = wals.map((w) => w.timerStart).reduce((a, b) => a < b ? a : b);
    final tempDir = await getTemporaryDirectory();
    final file = await writeRecordingWav(wals, outputPath: '${tempDir.path}/omi_recording_$start.wav');
    if (file == null) throw Exception('No audio on this phone for this recording');
    await SharePlus.instance.share(ShareParams(
      files: [XFile(file.path, mimeType: 'audio/wav')],
      text: 'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(start * 1000).toString().split('.')[0]}',
      sharePositionOrigin: shareSheetOrigin(),
    ));
  }

  Future<_WalWavWorkItem?> _prepareWalWavWorkItem(
    Wal wal, {
    required Directory tempDir,
    bool forSharing = false,
  }) async {
    final cacheKey = forSharing ? '${wal.id}_share' : wal.id;

    if (!forSharing && _audioFileCache.containsKey(cacheKey)) {
      final cachedPath = _audioFileCache[cacheKey]!;
      if (await File(cachedPath).exists()) {
        return _WalWavWorkItem.cached(walId: wal.id, cachedWavPath: cachedPath);
      }
    }

    // Sharing reuses the already-decoded playback file (e.g. the one produced when
    // the waveform loaded) instead of decoding the whole recording again.
    if (forSharing) {
      final playbackCached = _audioFileCache[wal.id];
      if (playbackCached != null && await File(playbackCached).exists()) {
        return _WalWavWorkItem.cached(walId: wal.id, cachedWavPath: playbackCached);
      }
    }

    final audioFilePath = await _getAudioFilePath(wal);
    if (audioFilePath == null) return null;

    final fileName = forSharing
        ? wal.getFileName().replaceAll('.bin', '.wav')
        : 'audio_${DateTime.now().millisecondsSinceEpoch}.wav';
    final wavFilePath = '${tempDir.path}/$fileName';
    final isOpus = wal.codec.isOpusSupported();
    final bitsPerSample = isOpus ? 16 : (wal.codec == BleAudioCodec.pcm16 ? 16 : 8);

    return _WalWavWorkItem.decode(
      walId: wal.id,
      inputPath: audioFilePath,
      outputPath: wavFilePath,
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
      _decodeWalWorkItemInIsolate,
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

  Future<String?> _getAudioFilePath(Wal wal) async {
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final fullPath = await Wal.getFilePath(wal.filePath);
      if (fullPath != null) {
        final file = File(fullPath);
        if (await file.exists()) return fullPath;
      }
    }

    if (wal.data.isNotEmpty) {
      return await _createTempFileFromMemoryData(wal);
    }

    return null;
  }

  Future<String?> _createTempFileFromMemoryData(Wal wal) async {
    final tempDir = await getTemporaryDirectory();
    final tempFilePath = '${tempDir.path}/temp_${wal.id}_${DateTime.now().millisecondsSinceEpoch}.bin';

    List<int> data = [];
    for (int i = 0; i < wal.data.length; i++) {
      var frame = wal.data[i];
      final byteFrame = ByteData(frame.length);
      for (int j = 0; j < frame.length; j++) {
        byteFrame.setUint8(j, frame[j]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }

    final file = File(tempFilePath);
    await file.writeAsBytes(data);
    return tempFilePath;
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

class _WalWavWorkItem {
  final String walId;
  final String? cachedWavPath;
  final String? inputPath;
  final String? outputPath;
  final bool isOpus;
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final OpusFrameDecoder? opusFrameDecoder;

  const _WalWavWorkItem.cached({required this.walId, required String this.cachedWavPath})
      : inputPath = null,
        outputPath = null,
        isOpus = false,
        sampleRate = 0,
        channels = 0,
        bitsPerSample = 0,
        opusFrameDecoder = null;

  const _WalWavWorkItem.decode({
    required this.walId,
    required String this.inputPath,
    required String this.outputPath,
    required this.isOpus,
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    this.opusFrameDecoder,
  }) : cachedWavPath = null;
}

class _RecordingWavJob {
  final List<_WalWavWorkItem> items;
  final String outputPath;

  const _RecordingWavJob({required this.items, required this.outputPath});
}

class _IsolateWavResult {
  final String? path;
  final String? isolateName;

  const _IsolateWavResult({required this.path, required this.isolateName});
}

bool _opusInitializedInIsolate = false;

Future<void> _ensureOpusInitializedInIsolate() async {
  if (_opusInitializedInIsolate) return;
  try {
    getOpusVersion();
    _opusInitializedInIsolate = true;
    return;
  } catch (_) {}
  initOpus(await opus_flutter.load());
  _opusInitializedInIsolate = true;
}

Future<_IsolateWavResult> _decodeWalWorkItemInIsolate(_WalWavWorkItem item) async {
  final path = await _decodeWalWorkItemToWav(item);
  return _IsolateWavResult(path: path, isolateName: Isolate.current.debugName);
}

Future<_IsolateWavResult> _buildRecordingWavInIsolate(_RecordingWavJob job) async {
  final parts = <File>[];
  for (final item in job.items) {
    final path = await _decodeWalWorkItemToWav(item);
    if (path != null) parts.add(File(path));
  }
  if (parts.isEmpty) {
    return _IsolateWavResult(path: null, isolateName: Isolate.current.debugName);
  }
  final combined = await WavCombiner.combineWavFiles(parts, job.outputPath);
  return _IsolateWavResult(path: combined.path, isolateName: Isolate.current.debugName);
}

Future<String?> _decodeWalWorkItemToWav(_WalWavWorkItem item) async {
  if (item.cachedWavPath != null) {
    final cachedFile = File(item.cachedWavPath!);
    return await cachedFile.exists() ? item.cachedWavPath : null;
  }
  final inputPath = item.inputPath;
  final outputPath = item.outputPath;
  if (inputPath == null || outputPath == null) return null;

  final file = File(inputPath);
  if (!await file.exists()) return null;

  final rawData = await file.readAsBytes();
  final frames = parseLengthPrefixedFrames(rawData);
  if (frames.isEmpty) return null;

  final Uint8List combinedPcm;
  if (item.isOpus) {
    final customDecoder = item.opusFrameDecoder;
    SimpleOpusDecoder? nativeDecoder;
    if (customDecoder == null) {
      await _ensureOpusInitializedInIsolate();
      nativeDecoder = SimpleOpusDecoder(sampleRate: item.sampleRate, channels: item.channels);
    }
    final pcmFrames = <Uint8List>[];
    try {
      for (final opusFrame in frames) {
        try {
          final pcmFrame = customDecoder != null
              ? customDecoder(opusFrame, item.sampleRate, item.channels)
              : nativeDecoder!.decode(input: opusFrame);
          pcmFrames.add(Uint8List.fromList(pcmFrame.buffer.asUint8List()));
        } catch (e) {
          Logger.debug('AudioPlayerUtils: skipping corrupted Opus frame for WAL ${item.walId}: $e');
        }
      }
    } finally {
      nativeDecoder?.destroy();
    }
    if (pcmFrames.isEmpty) return null;
    final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
    combinedPcm = Uint8List(totalLength);
    int writeOffset = 0;
    for (final frame in pcmFrames) {
      combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
      writeOffset += frame.length;
    }
  } else {
    final totalLength = frames.fold<int>(0, (sum, frame) => sum + frame.length);
    combinedPcm = Uint8List(totalLength);
    int writeOffset = 0;
    for (final frame in frames) {
      combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
      writeOffset += frame.length;
    }
  }

  final wavData = _buildWavHeaderAndData(
    pcmData: combinedPcm,
    sampleRate: item.sampleRate,
    channels: item.channels,
    bitsPerSample: item.bitsPerSample,
  );
  await File(outputPath).writeAsBytes(wavData);
  return outputPath;
}

Uint8List _buildWavHeaderAndData({
  required Uint8List pcmData,
  required int sampleRate,
  required int channels,
  required int bitsPerSample,
}) {
  const int wavHeaderSize = 44;
  final int frameSize = ((bitsPerSample + 7) ~/ 8) * channels;
  final int fileSize = wavHeaderSize + pcmData.length;

  final ByteData header = ByteData(wavHeaderSize);
  const Endian endian = Endian.little;

  header.setUint32(4, fileSize - 8, endian);
  header.setUint32(16, 16, endian);
  header.setUint16(20, 1, endian);
  header.setUint16(22, channels, endian);
  header.setUint32(24, sampleRate, endian);
  header.setUint32(28, sampleRate * frameSize, endian);
  header.setUint16(32, frameSize, endian);
  header.setUint16(34, bitsPerSample, endian);
  header.setUint32(40, pcmData.length, endian);

  final Uint8List headerBytes = header.buffer.asUint8List();
  headerBytes.setAll(0, ascii.encode('RIFF'));
  headerBytes.setAll(8, ascii.encode('WAVE'));
  headerBytes.setAll(12, ascii.encode('fmt '));
  headerBytes.setAll(36, ascii.encode('data'));

  final Uint8List wavFile = Uint8List(fileSize);
  wavFile.setAll(0, headerBytes);
  wavFile.setAll(wavHeaderSize, pcmData);

  return wavFile;
}
