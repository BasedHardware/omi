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
    final length = ByteData.sublistView(
      Uint8List.fromList(lengthBytes),
    ).getUint32(0, Endian.little);
    offset += 4;

    if (offset + length > data.length) break;

    final frameData = data.sublist(offset, offset + length);
    frames.add(Uint8List.fromList(frameData));
    offset += length;
  }

  return frames;
}

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
  String? _lastDecodeIsolateDebugName;

  @visibleForTesting
  OpusFrameDecoder? opusFrameDecoder;

  @visibleForTesting
  String? get lastDecodeIsolateDebugName => _lastDecodeIsolateDebugName;

  String? get currentPlayingId => _currentPlayingId;
  bool get isProcessingAudio => _isProcessingAudio;
  Duration get currentPosition => _currentPosition;
  Duration get totalDuration => _totalDuration;

  double get playbackProgress {
    if (_totalDuration.inMilliseconds <= 0) return 0.0;
    final progress =
        _currentPosition.inMilliseconds.toDouble() /
        _totalDuration.inMilliseconds.toDouble();
    return progress.clamp(0.0, 1.0);
  }

  /// Lazily initialize the audio player only when needed
  Future<void> _ensurePlayerInitialized() async {
    if (_audioPlayer != null) return;

    _audioPlayer = FlutterSoundPlayer();

    if (_audioPlayer != null && !_audioPlayer!.isOpen()) {
      await _audioPlayer!.openPlayer();
      // onProgress emits nothing unless a subscription interval is set (default 0ms).
      await _audioPlayer!.setSubscriptionDuration(
        const Duration(milliseconds: 100),
      );
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
      Logger.error(
        'AudioPlayerUtils: Audio file not available for playback, WAL ${wal.id}',
      );
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.audioPlaybackUnavailable ??
            'Audio file is not available for playback',
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
      Logger.error(
        'AudioPlayerUtils: Unable to create playable audio file for WAL ${wal.id}',
      );
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.audioPlaybackFailed ??
            'Unable to play audio. The file may be corrupted or missing.',
      );
      return;
    }

    _currentPlayingId = wal.id;
    _isProcessingAudio = false;

    await _audioPlayer?.startPlayer(
      fromURI: audioFilePath,
      whenFinished: () => _onPlaybackFinished(),
    );

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
        final estimatedPosition =
            _currentPosition + const Duration(milliseconds: 100);
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
  @visibleForTesting
  Future<File?> writeRecordingWav(
    List<Wal> wals, {
    required String outputPath,
  }) async {
    final parts = <File>[];
    for (final wal in [
      ...wals,
    ]..sort((a, b) => a.timerStart.compareTo(b.timerStart))) {
      if (!canPlayOrShare(wal)) continue;
      final path = await _getOrCreateAudioFile(wal, forSharing: true);
      if (path != null) parts.add(File(path));
    }
    if (parts.isEmpty) return null;
    return WavCombiner.combineWavFiles(parts, outputPath);
  }

  Future<void> shareRecordingAsAudio(List<Wal> wals) async {
    final start = wals.map((w) => w.timerStart).reduce((a, b) => a < b ? a : b);
    final tempDir = await getTemporaryDirectory();
    final file = await writeRecordingWav(
      wals,
      outputPath: '${tempDir.path}/omi_recording_$start.wav',
    );
    if (file == null)
      throw Exception('No audio on this phone for this recording');
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(file.path, mimeType: 'audio/wav')],
        text:
            'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(start * 1000).toString().split('.')[0]}',
        sharePositionOrigin: shareSheetOrigin(),
      ),
    );
  }

  Future<String?> _getOrCreateAudioFile(
    Wal wal, {
    bool forSharing = false,
  }) async {
    final cacheKey = forSharing ? '${wal.id}_share' : wal.id;

    if (!forSharing && _audioFileCache.containsKey(cacheKey)) {
      final cachedPath = _audioFileCache[cacheKey]!;
      if (await File(cachedPath).exists()) {
        return cachedPath;
      }
    }

    // Sharing reuses the already-decoded playback file (e.g. the one produced when
    // the waveform loaded) instead of decoding the whole recording again.
    if (forSharing) {
      final playbackCached = _audioFileCache[wal.id];
      if (playbackCached != null && await File(playbackCached).exists()) {
        return playbackCached;
      }
    }

    final tempDir = await getTemporaryDirectory();
    final job = await _prepareDecodeJob(
      wal,
      tempDirPath: tempDir.path,
      forSharing: forSharing,
    );
    if (job == null) return null;

    final decoderOverride = opusFrameDecoder;
    final result = await Isolate.run(
      () => _decodeWalAudioInIsolate(job, opusFrameDecoder: decoderOverride),
      debugName: 'decodeWalAudio',
    );
    _lastDecodeIsolateDebugName = result.isolateName;
    for (final warning in result.warnings) {
      Logger.warning(warning);
    }

    final processedFilePath = result.wavPath;
    if (processedFilePath != null && !forSharing) {
      _audioFileCache[cacheKey] = processedFilePath;
    }

    return processedFilePath;
  }

  Future<_AudioDecodeJob?> _prepareDecodeJob(
    Wal wal, {
    required String tempDirPath,
    required bool forSharing,
  }) async {
    String? inputFilePath;
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final fullPath = await Wal.getFilePath(wal.filePath);
      if (fullPath != null && await File(fullPath).exists()) {
        inputFilePath = fullPath;
      }
    }

    if (inputFilePath == null && wal.data.isEmpty) return null;

    final fileName = forSharing
        ? wal.getFileName().replaceAll('.bin', '.wav')
        : 'audio_${DateTime.now().millisecondsSinceEpoch}.wav';
    final isOpus = wal.codec.isOpusSupported();
    return _AudioDecodeJob(
      walId: wal.id,
      outputWavPath: '$tempDirPath/$fileName',
      isOpus: isOpus,
      sampleRate: wal.sampleRate,
      channels: wal.channel,
      bitsPerSample: isOpus || wal.codec == BleAudioCodec.pcm16 ? 16 : 8,
      inputFilePath: inputFilePath,
      memoryFrames: inputFilePath == null ? wal.data : const [],
    );
  }

  Future<void> seekToPosition(Duration position) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      await _audioPlayer!.seekToPlayer(position);
      _currentPosition = position;
      notifyListeners();
    }
  }

  Future<void> skipForward({
    Duration duration = const Duration(seconds: 10),
  }) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      final newPosition = _currentPosition + duration;
      final clampedPosition = newPosition > _totalDuration
          ? _totalDuration
          : newPosition;
      await seekToPosition(clampedPosition);
    }
  }

  Future<void> skipBackward({
    Duration duration = const Duration(seconds: 10),
  }) async {
    if (_audioPlayer != null && _currentPlayingId != null) {
      final newPosition = _currentPosition - duration;
      final clampedPosition = newPosition < Duration.zero
          ? Duration.zero
          : newPosition;
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

typedef OpusFrameDecoder =
    Uint8List Function(int sampleRate, int channels, Uint8List opusFrame);

class _AudioDecodeJob {
  const _AudioDecodeJob({
    required this.walId,
    required this.outputWavPath,
    required this.isOpus,
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    this.inputFilePath,
    this.memoryFrames = const [],
  });

  final String walId;
  final String outputWavPath;
  final bool isOpus;
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final String? inputFilePath;
  final List<List<int>> memoryFrames;
}

class _AudioDecodeResult {
  const _AudioDecodeResult({
    required this.wavPath,
    required this.isolateName,
    required this.warnings,
  });

  final String? wavPath;
  final String? isolateName;
  final List<String> warnings;
}

Future<void> _ensureOpusInitializedInIsolate() async {
  try {
    getOpusVersion();
    return;
  } catch (_) {}
  try {
    initOpus(await opus_flutter.load());
  } catch (_) {}
}

Future<_AudioDecodeResult> _decodeWalAudioInIsolate(
  _AudioDecodeJob job, {
  OpusFrameDecoder? opusFrameDecoder,
}) async {
  final warnings = <String>[];
  List<Uint8List> frames = const [];

  if (job.inputFilePath != null) {
    final file = File(job.inputFilePath!);
    if (!await file.exists()) {
      return _AudioDecodeResult(
        wavPath: null,
        isolateName: Isolate.current.debugName,
        warnings: warnings,
      );
    }
    final fileBytes = await file.readAsBytes();
    frames = parseLengthPrefixedFrames(fileBytes);
  } else if (job.memoryFrames.isNotEmpty) {
    frames = [for (final frame in job.memoryFrames) Uint8List.fromList(frame)];
  }

  if (frames.isEmpty) {
    return _AudioDecodeResult(
      wavPath: null,
      isolateName: Isolate.current.debugName,
      warnings: warnings,
    );
  }

  final pcmFrames = <Uint8List>[];
  if (job.isOpus) {
    if (opusFrameDecoder != null) {
      for (final opusFrame in frames) {
        try {
          pcmFrames.add(
            opusFrameDecoder(job.sampleRate, job.channels, opusFrame),
          );
        } catch (e) {
          warnings.add(
            'AudioPlayerUtils: skipping corrupted Opus frame for WAL ${job.walId}: $e',
          );
        }
      }
    } else {
      await _ensureOpusInitializedInIsolate();
      final decoder = SimpleOpusDecoder(
        sampleRate: job.sampleRate,
        channels: job.channels,
      );
      try {
        for (final opusFrame in frames) {
          try {
            final pcmFrame = decoder.decode(input: opusFrame);
            pcmFrames.add(Uint8List.fromList(pcmFrame.buffer.asUint8List()));
          } catch (e) {
            warnings.add(
              'AudioPlayerUtils: skipping corrupted Opus frame for WAL ${job.walId}: $e',
            );
          }
        }
      } finally {
        decoder.destroy();
      }
    }
  } else {
    pcmFrames.addAll(frames);
  }

  if (pcmFrames.isEmpty) {
    return _AudioDecodeResult(
      wavPath: null,
      isolateName: Isolate.current.debugName,
      warnings: warnings,
    );
  }

  final totalLength = pcmFrames.fold<int>(
    0,
    (sum, frame) => sum + frame.length,
  );
  final combinedPcm = Uint8List(totalLength);
  int writeOffset = 0;
  for (final frame in pcmFrames) {
    combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
    writeOffset += frame.length;
  }

  final wavBytes = _buildWavFileBytes(
    pcmData: combinedPcm,
    sampleRate: job.sampleRate,
    channels: job.channels,
    bitsPerSample: job.bitsPerSample,
  );
  await File(job.outputWavPath).writeAsBytes(wavBytes);
  return _AudioDecodeResult(
    wavPath: job.outputWavPath,
    isolateName: Isolate.current.debugName,
    warnings: warnings,
  );
}

Uint8List _buildWavFileBytes({
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
