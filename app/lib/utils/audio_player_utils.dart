import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

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
    if (Platform.isMacOS) return;

    _audioPlayer = FlutterSoundPlayer();

    if (_audioPlayer != null && !_audioPlayer!.isOpen()) {
      await _audioPlayer!.openPlayer();
    }
  }

  bool isPlaying(String id) => _currentPlayingId == id;

  bool canPlayOrShare(Wal wal) {
    return (wal.filePath != null && wal.filePath!.isNotEmpty) ||
        wal.data.isNotEmpty ||
        wal.storage == WalStorage.sdcard;
  }

  Future<void> togglePlayback(Wal wal) async {
    if (!canPlayOrShare(wal)) {
      throw Exception('Audio file not available for playback');
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
      throw Exception('Unable to create playable audio file');
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
    debugPrint('Audio playback finished');
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
    );

    if (result.status == ShareResultStatus.success) {
      debugPrint('Audio file shared successfully');
    }
  }

  Future<String?> _getOrCreateAudioFile(Wal wal, {bool forSharing = false}) async {
    final cacheKey = forSharing ? '${wal.id}_share' : wal.id;

    if (!forSharing && _audioFileCache.containsKey(cacheKey)) {
      final cachedPath = _audioFileCache[cacheKey]!;
      if (File(cachedPath).existsSync()) {
        return cachedPath;
      }
    }

    final audioFilePath = await _getAudioFilePath(wal);
    if (audioFilePath == null) return null;

    String? processedFilePath;
    if (wal.codec.isOpusSupported()) {
      processedFilePath = await _decodeOpusToWav(wal, audioFilePath, forSharing: forSharing);
    } else {
      processedFilePath = await _convertPcmToWav(wal, audioFilePath, forSharing: forSharing);
    }

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
        if (file.existsSync()) return fullPath;
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
      var frame = wal.data[i].sublist(3);
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

  Future<String?> _decodeOpusToWav(Wal wal, String opusFilePath, {bool forSharing = false}) async {
    final file = File(opusFilePath);
    if (!file.existsSync()) return null;

    final opusData = await file.readAsBytes();
    List<Uint8List> opusFrames = [];
    int offset = 0;

    while (offset < opusData.length - 4) {
      final lengthBytes = opusData.sublist(offset, offset + 4);
      final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
      offset += 4;

      if (offset + length > opusData.length) break;

      final frameData = opusData.sublist(offset, offset + length);
      opusFrames.add(Uint8List.fromList(frameData));
      offset += length;
    }

    if (opusFrames.isEmpty) return null;

    final decoder = SimpleOpusDecoder(
      sampleRate: wal.sampleRate,
      channels: wal.channel,
    );

    List<Uint8List> pcmFrames = [];
    for (final opusFrame in opusFrames) {
      final pcmFrame = decoder.decode(input: opusFrame);
      if (pcmFrame != null) {
        final uint8Frame = Uint8List.fromList(pcmFrame.buffer.asUint8List());
        pcmFrames.add(uint8Frame);
      }
    }

    if (pcmFrames.isEmpty) return null;

    final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
    final combinedPcm = Uint8List(totalLength);
    int writeOffset = 0;
    for (final frame in pcmFrames) {
      combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
      writeOffset += frame.length;
    }

    return await _createWavFile(
      pcmData: combinedPcm,
      wal: wal,
      bitsPerSample: 16,
      forSharing: forSharing,
    );
  }

  Future<String?> _convertPcmToWav(Wal wal, String pcmFilePath, {bool forSharing = false}) async {
    final file = File(pcmFilePath);
    if (!file.existsSync()) return null;

    final pcmFileData = await file.readAsBytes();
    List<Uint8List> pcmFrames = [];
    int offset = 0;

    while (offset < pcmFileData.length - 4) {
      final lengthBytes = pcmFileData.sublist(offset, offset + 4);
      final length = ByteData.sublistView(pcmFileData, offset + 4, offset + 8).getUint32(0, Endian.little);
      offset += 4;

      if (offset + length > pcmFileData.length) break;

      final frameData = pcmFileData.sublist(offset, offset + length);
      pcmFrames.add(Uint8List.fromList(frameData));
      offset += length;
    }

    if (pcmFrames.isEmpty) return null;

    final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
    final combinedPcm = Uint8List(totalLength);
    int writeOffset = 0;
    for (final frame in pcmFrames) {
      combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
      writeOffset += frame.length;
    }

    final bitsPerSample = wal.codec == BleAudioCodec.pcm16 ? 16 : 8;
    return await _createWavFile(
      pcmData: combinedPcm,
      wal: wal,
      bitsPerSample: bitsPerSample,
      forSharing: forSharing,
    );
  }

  Future<String> _createWavFile({
    required Uint8List pcmData,
    required Wal wal,
    required int bitsPerSample,
    bool forSharing = false,
  }) async {
    final tempDir = await getTemporaryDirectory();
    final fileName = forSharing
        ? wal.getFileName().replaceAll('.bin', '.wav')
        : 'audio_${DateTime.now().millisecondsSinceEpoch}.wav';
    final wavFilePath = '${tempDir.path}/$fileName';

    final wavData = _createWavHeader(
      pcmData: pcmData,
      sampleRate: wal.sampleRate,
      channels: wal.channel,
      bitsPerSample: bitsPerSample,
    );

    await File(wavFilePath).writeAsBytes(wavData);
    return wavFilePath;
  }

  Uint8List _createWavHeader({
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
      if (File(cachedPath).existsSync()) {
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
