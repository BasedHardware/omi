import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_sound/flutter_sound.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

class SyncProvider extends ChangeNotifier implements IWalServiceListener, IWalSyncProgressListener {
  // WAL management
  List<Wal> _allWals = [];
  List<Wal> get allWals => _allWals;
  bool _isLoadingWals = false;
  bool get isLoadingWals => _isLoadingWals;

  List<Wal> _missingWals = [];
  List<Wal> get missingWals => _missingWals;
  int get missingWalsInSeconds =>
      _missingWals.isEmpty ? 0 : _missingWals.map((val) => val.seconds).reduce((a, b) => a + b);

  // Sync state
  bool isSyncing = false;
  bool syncCompleted = false;
  bool isFetchingConversations = false;
  double _walsSyncedProgress = 0.0;
  double get walsSyncedProgress => _walsSyncedProgress;
  List<SyncedConversationPointer> syncedConversationsPointers = [];

  // Error handling
  String? syncError;
  Wal? failedWal;

  // Audio playback
  FlutterSoundPlayer? _audioPlayer;
  String? _currentPlayingWalId;
  bool _isProcessingAudio = false;
  String? _currentSharingWalId;

  // Playback position tracking
  Duration _currentPosition = Duration.zero;
  Duration _totalDuration = Duration.zero;
  StreamSubscription<PlaybackDisposition>? _positionSubscription;

  // Waveform generation
  final Map<String, List<double>> _waveformCache = {};
  final Map<String, String> _wavFileCache = {}; // Cache WAV file paths

  String? get currentPlayingWalId => _currentPlayingWalId;
  bool get isProcessingAudio => _isProcessingAudio;
  bool get isSharingAudio => _currentSharingWalId != null;
  bool isWalSharing(String walId) => _currentSharingWalId == walId;
  Duration get currentPosition => _currentPosition;
  Duration get totalDuration => _totalDuration;
  double get playbackProgress {
    if (_totalDuration.inMilliseconds <= 0) {
      return 0.0;
    }
    final progress = _currentPosition.inMilliseconds.toDouble() / _totalDuration.inMilliseconds.toDouble();
    final clampedProgress = progress.clamp(0.0, 1.0);
    return clampedProgress;
  }

  IWalService get _wal => ServiceManager.instance().wal;

  SyncProvider() {
    _wal.subscribe(this, this);
    _initializeAudioPlayer();
    refreshWals();
  }

  void _initializeAudioPlayer() async {
    _audioPlayer = FlutterSoundPlayer();
    await _audioPlayer?.openPlayer();
  }

  Future<void> refreshWals() async {
    _isLoadingWals = true;
    notifyListeners();
    try {
      _allWals = await _wal.getSyncs().getAllWals();
      _missingWals = _allWals.where((w) => w.status == WalStatus.miss).toList();
      debugPrint('SyncProvider.refreshWals() loaded ${_allWals.length} WALs');
    } catch (e) {
      debugPrint('Error in SyncProvider.refreshWals(): $e');
      _allWals = [];
    } finally {
      _isLoadingWals = false;
      notifyListeners();
    }
  }

  Future<WalStats> getWalStats() async {
    try {
      return await _wal.getSyncs().getWalStats();
    } catch (e) {
      debugPrint('Error in SyncProvider.getWalStats(): $e');
      return WalStats(
        totalFiles: 0,
        phoneFiles: 0,
        sdcardFiles: 0,
        phoneSize: 0,
        sdcardSize: 0,
        syncedFiles: 0,
        missedFiles: 0,
      );
    }
  }

  Future<void> deleteWal(Wal wal) async {
    try {
      await _wal.getSyncs().deleteWal(wal);
      await refreshWals();
    } catch (e) {
      debugPrint('Error deleting WAL: $e');
    }
  }

  Future<void> deleteAllSyncedWals() async {
    try {
      await _wal.getSyncs().deleteAllSyncedWals();
      notifyListeners();
    } catch (e) {
      debugPrint('Error deleting all synced WALs: $e');
    }
  }

  Future<void> resyncWal(Wal wal) async {
    try {
      debugPrint("SyncProvider > resyncWal ${wal.id}");
      clearSyncResult();
      setIsSyncing(true);
      _walsSyncedProgress = 0.0;
      var res = await _wal.getSyncs().resyncWal(wal);
      if (res != null) {
        if (res.newConversationIds.isNotEmpty || res.updatedConversationIds.isNotEmpty) {
          print('Resynced memories: ${res.newConversationIds} ${res.updatedConversationIds}');
          await getSyncedConversationsData(res);
        }
      }
      setSyncCompleted(true);
      setIsSyncing(false);
      notifyListeners();
    } catch (e) {
      final walInfo = '${secondsToHumanReadable(wal.seconds)} (${wal.codec.toFormattedString()})';
      final source = wal.storage == WalStorage.sdcard ? 'SD card' : 'phone';
      debugPrint('Error resyncing WAL ${wal.id}: $e');
      setIsSyncing(false);
      setSyncCompleted(false);
      syncError = 'Failed to reprocess $source audio file $walInfo: ${e.toString().replaceAll('Exception: ', '')}';
      failedWal = wal;
      notifyListeners();
    }
  }

  Future syncWals() async {
    try {
      debugPrint("SyncProvider > syncWals");
      clearSyncResult();
      _walsSyncedProgress = 0.0;
      setIsSyncing(true);
      var res = await _wal.getSyncs().syncAll(progress: this);
      if (res != null) {
        if (res.newConversationIds.isNotEmpty || res.updatedConversationIds.isNotEmpty) {
          await getSyncedConversationsData(res);
        }
      }
      setSyncCompleted(true);
      setIsSyncing(false);
      notifyListeners();
    } catch (e) {
      debugPrint('Error syncing all WALs: $e');
      setIsSyncing(false);
      setSyncCompleted(false);
      _walsSyncedProgress = 0.0;
      syncError = 'Error processing audio files: ${e.toString().replaceAll('Exception: ', '')}';
      failedWal = null;
      notifyListeners();
    }
  }

  Future syncWal(Wal wal) async {
    try {
      debugPrint("SyncProvider > syncWal ${wal.id}");
      clearSyncResult();
      setIsSyncing(true);
      _walsSyncedProgress = 0.0;
      var res = await _wal.getSyncs().syncWal(wal: wal, progress: this);
      if (res != null) {
        if (res.newConversationIds.isNotEmpty || res.updatedConversationIds.isNotEmpty) {
          print('Synced memories: ${res.newConversationIds} ${res.updatedConversationIds}');
          await getSyncedConversationsData(res);
        }
      }
      setSyncCompleted(true);
      setIsSyncing(false);
      notifyListeners();
    } catch (e) {
      final walInfo = '${secondsToHumanReadable(wal.seconds)} (${wal.codec.toFormattedString()})';
      final source = wal.storage == WalStorage.sdcard ? 'SD card' : 'phone';
      debugPrint('Error syncing WAL ${wal.id}: $e');
      setIsSyncing(false);
      setSyncCompleted(false);
      _walsSyncedProgress = 0.0;
      syncError = 'Failed to process $source audio file $walInfo: ${e.toString().replaceAll('Exception: ', '')}';
      failedWal = wal;
      notifyListeners();
    }
  }

  void setSyncCompleted(bool value) {
    syncCompleted = value;
    notifyListeners();
  }

  void setIsSyncing(bool value) {
    isSyncing = value;
    notifyListeners();
  }

  void setIsFetchingConversations(bool value) {
    isFetchingConversations = value;
    notifyListeners();
  }

  Future<void> retrySync() async {
    final walToRetry = failedWal;
    clearSyncResult(); // Clear error and previous state
    if (walToRetry != null) {
      await syncWal(walToRetry);
    } else {
      await syncWals();
    }
  }

  void clearSyncResult() {
    syncCompleted = false;
    syncedConversationsPointers = [];
    syncError = null;
    failedWal = null;
    notifyListeners();
  }

  Future getSyncedConversationsData(SyncLocalFilesResponse syncResult) async {
    List<dynamic> newConversations = syncResult.newConversationIds;
    List<dynamic> updatedConversations = syncResult.updatedConversationIds;
    setIsFetchingConversations(true);
    List<Future<ServerConversation?>> newConversationsFutures =
        newConversations.map((item) => getConversationDetails(item)).toList();

    List<Future<ServerConversation?>> updatedConversationsFutures =
        updatedConversations.map((item) => getConversationDetails(item)).toList();
    var syncedConversations = {'new_memories': [], 'updated_memories': []};
    try {
      final newConversationsResponses = await Future.wait(newConversationsFutures);
      syncedConversations['new_memories'] = newConversationsResponses;

      final updatedConversationsResponses = await Future.wait(updatedConversationsFutures);
      syncedConversations['updated_memories'] = updatedConversationsResponses;
      addSyncedConversationsToGroupedConversations(syncedConversations);
      setIsFetchingConversations(false);
    } catch (e) {
      print('Error during API calls: $e');
      setIsFetchingConversations(false);
    }
  }

  void addSyncedConversationsToGroupedConversations(Map syncedConversations) {
    for (var conversation in syncedConversations['new_memories']!) {
      if (conversation != null && conversation.status == ConversationStatus.completed) {
        var res = getConversationDateAndIndex(conversation);
        syncedConversationsPointers.add(SyncedConversationPointer(
            type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, conversation: conversation));
      }
    }
    if (syncedConversations['updated_memories'] != []) {
      for (var conversation in syncedConversations['updated_memories']!) {
        if (conversation != null && conversation.status == ConversationStatus.completed) {
          var res = getConversationDateAndIndex(conversation);
          syncedConversationsPointers.add(SyncedConversationPointer(
              type: SyncedConversationType.newConversation, index: res.$2, key: res.$1, conversation: conversation));
        }
      }
    }
  }

  (DateTime, int) getConversationDateAndIndex(ServerConversation conversation) {
    var date = DateTime(conversation.createdAt.year, conversation.createdAt.month, conversation.createdAt.day);
    return (date, 0); // Simplified for sync provider
  }

  Future<ServerConversation?> getConversationDetails(String conversationId) async {
    var conversation = await getConversationById(conversationId);
    return conversation;
  }

  // Audio playback methods
  bool isWalPlaying(String walId) {
    return _currentPlayingWalId == walId;
  }

  bool canPlayOrShareWal(Wal wal) {
    return (wal.filePath != null && wal.filePath!.isNotEmpty) ||
        wal.data.isNotEmpty ||
        wal.storage == WalStorage.sdcard;
  }

  Future<void> toggleWalPlayback(Wal wal) async {
    if (!canPlayOrShareWal(wal)) {
      throw Exception('Audio file not available for playback');
    }

    if (_isProcessingAudio) return;

    if (isWalPlaying(wal.id)) {
      // Stop playback
      await _audioPlayer?.stopPlayer();
      _currentPlayingWalId = null;
      _currentPosition = Duration.zero;
      _totalDuration = Duration.zero;
      _positionSubscription?.cancel();
      notifyListeners();
      return;
    }

    // Start playback
    _isProcessingAudio = true;
    _currentPosition = Duration.zero;
    _totalDuration = Duration.zero;
    notifyListeners();

    try {
      String? wavFilePath;

      // Get the audio file path - create temporary file if needed
      String? audioFilePath = await _getAudioFilePath(wal);
      if (audioFilePath == null) {
        throw Exception('Unable to access audio data');
      }

      // Check if it's an opus file that needs decoding
      if (wal.codec.isOpusSupported()) {
        wavFilePath = await _decodeOpusToWav(wal, audioFilePath);
      } else {
        // For PCM files, we can try to play directly or convert to WAV
        wavFilePath = await _convertPcmToWav(wal, audioFilePath);
      }

      if (wavFilePath != null) {
        // Cache the WAV file path for waveform generation
        _wavFileCache[wal.id] = wavFilePath;

        _currentPlayingWalId = wal.id;
        _isProcessingAudio = false;

        await _audioPlayer?.startPlayer(
          fromURI: wavFilePath,
          whenFinished: () {
            debugPrint('Audio playback finished');
            _currentPlayingWalId = null;
            _currentPosition = Duration.zero;
            _totalDuration = Duration.zero;
            _positionSubscription?.cancel();
            notifyListeners();
          },
        );

        // Set up position tracking AFTER starting playback and ensure it's working
        _positionSubscription?.cancel();
        _positionSubscription = _audioPlayer?.onProgress?.listen((disposition) {
          if (_currentPlayingWalId == wal.id) {
            _currentPosition = disposition.position;
            _totalDuration = disposition.duration;
            debugPrint(
                'Position update: ${_currentPosition.inMilliseconds}ms / ${_totalDuration.inMilliseconds}ms (${(playbackProgress * 100).toStringAsFixed(1)}%)');
            notifyListeners();
          }
        });

        // Also start a manual timer as backup in case onProgress doesn't work
        Timer.periodic(const Duration(milliseconds: 100), (timer) {
          if (_currentPlayingWalId != wal.id || !(_audioPlayer?.isPlaying ?? false)) {
            timer.cancel();
            return;
          }

          // Manual position tracking as fallback
          if (_totalDuration.inMilliseconds > 0) {
            final estimatedPosition = _currentPosition + const Duration(milliseconds: 100);
            if (estimatedPosition <= _totalDuration) {
              _currentPosition = estimatedPosition;
              debugPrint(
                  'Manual position update: ${_currentPosition.inMilliseconds}ms / ${_totalDuration.inMilliseconds}ms');
              notifyListeners();
            }
          }
        });

        // Set initial duration from WAL data
        _totalDuration = Duration(seconds: wal.seconds);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error playing audio: $e');
      _isProcessingAudio = false;
      _currentPlayingWalId = null;
      _currentPosition = Duration.zero;
      _totalDuration = Duration.zero;
      _positionSubscription?.cancel();
      notifyListeners();
      rethrow;
    }
  }

  Future<void> shareWalAsWav(Wal wal) async {
    if (!canPlayOrShareWal(wal)) {
      throw Exception('Audio file not available for sharing');
    }

    if (isSharingAudio) return;

    _currentSharingWalId = wal.id;
    notifyListeners();

    try {
      String? wavFilePath;

      // Get the audio file path - create temporary file if needed
      String? audioFilePath = await _getAudioFilePath(wal);
      if (audioFilePath == null) {
        throw Exception('Unable to access audio data');
      }

      // Check if it's an opus file that needs decoding
      if (wal.codec.isOpusSupported()) {
        wavFilePath = await _decodeOpusToWav(wal, audioFilePath, forSharing: true);
      } else {
        // For PCM files, convert to WAV
        wavFilePath = await _convertPcmToWav(wal, audioFilePath, forSharing: true);
      }

      if (wavFilePath != null) {
        final result = await Share.shareXFiles(
          [XFile(wavFilePath)],
          text:
              'Omi Audio Recording - ${DateTime.fromMillisecondsSinceEpoch(wal.timerStart * 1000).toString().split('.')[0]}',
        );

        if (result.status == ShareResultStatus.success) {
          debugPrint('Audio file shared successfully');
        }
      }
    } catch (e) {
      debugPrint('Error sharing audio: $e');
      rethrow;
    } finally {
      _currentSharingWalId = null;
      notifyListeners();
    }
  }

  Future<String?> _getAudioFilePath(Wal wal) async {
    // If WAL already has a file path, use it
    if (wal.filePath != null && wal.filePath!.isNotEmpty) {
      final file = File(wal.filePath!);
      if (file.existsSync()) {
        return wal.filePath!;
      }
    }

    // If WAL has data in memory, create a temporary file
    if (wal.data.isNotEmpty) {
      return await _createTempFileFromMemoryData(wal);
    }

    // For SD card WALs, we would need to read from device
    if (wal.storage == WalStorage.sdcard) {
      return null;
    }

    return null;
  }

  Future<String?> _createTempFileFromMemoryData(Wal wal) async {
    try {
      final tempDir = await getTemporaryDirectory();
      final tempFilePath = '${tempDir.path}/temp_${wal.id}_${DateTime.now().millisecondsSinceEpoch}.bin';

      List<int> data = [];
      for (int i = 0; i < wal.data.length; i++) {
        var frame = wal.data[i].sublist(3); // Remove the 3-byte header

        // Format: <length>|<data> ; bytes: 4 | n
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
    } catch (e) {
      debugPrint('Error creating temp file from memory data: $e');
      return null;
    }
  }

  Future<String?> _decodeOpusToWav(Wal wal, String opusFilePath, {bool forSharing = false}) async {
    try {
      final file = File(opusFilePath);
      if (!file.existsSync()) {
        throw Exception('Opus file not found');
      }

      // Read the opus file data
      final opusData = await file.readAsBytes();

      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> opusFrames = [];
      int offset = 0;

      while (offset < opusData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = opusData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > opusData.length) break;

        // Read frame data
        final frameData = opusData.sublist(offset, offset + length);
        opusFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (opusFrames.isEmpty) {
        throw Exception('No opus frames found in file');
      }

      // Initialize opus decoder
      final decoder = SimpleOpusDecoder(
        sampleRate: wal.sampleRate,
        channels: wal.channel,
      );

      // Decode all frames
      List<Uint8List> pcmFrames = [];
      for (final opusFrame in opusFrames) {
        try {
          final pcmFrame = decoder.decode(input: opusFrame);
          if (pcmFrame != null) {
            // Convert Int16List to Uint8List
            final uint8Frame = Uint8List.fromList(pcmFrame.buffer.asUint8List());
            pcmFrames.add(uint8Frame);
          }
        } catch (e) {
          debugPrint('Error decoding opus frame: $e');
          // Continue with other frames
        }
      }

      if (pcmFrames.isEmpty) {
        throw Exception('No PCM data decoded');
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Create WAV file
      final tempDir = await getTemporaryDirectory();
      final fileName = forSharing
          ? wal.getFileName().replaceAll('.bin', '.wav')
          : 'decoded_${DateTime.now().millisecondsSinceEpoch}.wav';
      final wavFilePath = '${tempDir.path}/$fileName';

      final wavData = _createWavFile(
        pcmData: combinedPcm,
        sampleRate: wal.sampleRate,
        channels: wal.channel,
        bitsPerSample: 16,
      );

      await File(wavFilePath).writeAsBytes(wavData);
      return wavFilePath;
    } catch (e) {
      debugPrint('Error decoding opus to wav: $e');
      return null;
    }
  }

  Future<String?> _convertPcmToWav(Wal wal, String pcmFilePath, {bool forSharing = false}) async {
    try {
      final file = File(pcmFilePath);
      if (!file.existsSync()) {
        throw Exception('PCM file not found');
      }

      // Read the PCM file data (same custom format as opus)
      final pcmFileData = await file.readAsBytes();

      // Parse the custom format: <length>|<data> for each frame
      List<Uint8List> pcmFrames = [];
      int offset = 0;

      while (offset < pcmFileData.length - 4) {
        // Read frame length (4 bytes)
        final lengthBytes = pcmFileData.sublist(offset, offset + 4);
        final length = ByteData.sublistView(Uint8List.fromList(lengthBytes)).getUint32(0, Endian.little);
        offset += 4;

        if (offset + length > pcmFileData.length) break;

        // Read frame data
        final frameData = pcmFileData.sublist(offset, offset + length);
        pcmFrames.add(Uint8List.fromList(frameData));
        offset += length;
      }

      if (pcmFrames.isEmpty) {
        throw Exception('No PCM frames found in file');
      }

      // Combine all PCM frames
      final totalLength = pcmFrames.fold<int>(0, (sum, frame) => sum + frame.length);
      final combinedPcm = Uint8List(totalLength);
      int writeOffset = 0;
      for (final frame in pcmFrames) {
        combinedPcm.setRange(writeOffset, writeOffset + frame.length, frame);
        writeOffset += frame.length;
      }

      // Create WAV file
      final tempDir = await getTemporaryDirectory();
      final fileName = forSharing
          ? wal.getFileName().replaceAll('.bin', '.wav')
          : 'converted_${DateTime.now().millisecondsSinceEpoch}.wav';
      final wavFilePath = '${tempDir.path}/$fileName';

      final bitsPerSample = wal.codec == BleAudioCodec.pcm16 ? 16 : 8;
      final wavData = _createWavFile(
        pcmData: combinedPcm,
        sampleRate: wal.sampleRate,
        channels: wal.channel,
        bitsPerSample: bitsPerSample,
      );

      await File(wavFilePath).writeAsBytes(wavData);
      return wavFilePath;
    } catch (e) {
      debugPrint('Error converting PCM to wav: $e');
      return null;
    }
  }

  Uint8List _createWavFile({
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

    // WAV header
    header.setUint32(4, fileSize - 8, endian); // File size - 8
    header.setUint32(16, 16, endian); // PCM format chunk size
    header.setUint16(20, 1, endian); // Audio format (PCM)
    header.setUint16(22, channels, endian); // Number of channels
    header.setUint32(24, sampleRate, endian); // Sample rate
    header.setUint32(28, sampleRate * frameSize, endian); // Byte rate
    header.setUint16(32, frameSize, endian); // Block align
    header.setUint16(34, bitsPerSample, endian); // Bits per sample
    header.setUint32(40, pcmData.length, endian); // Data chunk size

    final Uint8List headerBytes = header.buffer.asUint8List();
    headerBytes.setAll(0, ascii.encode('RIFF'));
    headerBytes.setAll(8, ascii.encode('WAVE'));
    headerBytes.setAll(12, ascii.encode('fmt '));
    headerBytes.setAll(36, ascii.encode('data'));

    // Combine header and PCM data
    final Uint8List wavFile = Uint8List(fileSize);
    wavFile.setAll(0, headerBytes);
    wavFile.setAll(wavHeaderSize, pcmData);

    return wavFile;
  }

  @override
  void onWalUpdated() async {
    await refreshWals();
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) async {
    await refreshWals();
  }

  @override
  void onStatusChanged(WalServiceStatus status) {}

  @override
  void onWalSyncedProgress(double percentage) {
    _walsSyncedProgress = percentage;
    notifyListeners();
  }

  Future<void> seekToPosition(Duration position) async {
    if (_audioPlayer != null && _currentPlayingWalId != null) {
      try {
        await _audioPlayer!.seekToPlayer(position);
        _currentPosition = position;
        notifyListeners();
      } catch (e) {
        debugPrint('Error seeking to position: $e');
      }
    }
  }

  Future<void> skipForward({Duration duration = const Duration(seconds: 10)}) async {
    if (_audioPlayer != null && _currentPlayingWalId != null) {
      final newPosition = _currentPosition + duration;
      final clampedPosition = newPosition > _totalDuration ? _totalDuration : newPosition;
      await seekToPosition(clampedPosition);
    }
  }

  Future<void> skipBackward({Duration duration = const Duration(seconds: 10)}) async {
    if (_audioPlayer != null && _currentPlayingWalId != null) {
      final newPosition = _currentPosition - duration;
      final clampedPosition = newPosition < Duration.zero ? Duration.zero : newPosition;
      await seekToPosition(clampedPosition);
    }
  }

  // Waveform generation methods
  Future<List<double>?> getWaveformForWal(String walId) async {
    debugPrint('generating waveform for WAL $walId');
    if (_waveformCache.containsKey(walId)) {
      return _waveformCache[walId];
    }

    final wal = _allWals.firstWhere((w) => w.id == walId, orElse: () => throw Exception('WAL not found'));

    try {
      // Generate waveform from the same WAV file used for playback
      String? wavFilePath = _wavFileCache[walId];

      if (wavFilePath == null) {
        // Create WAV file if not cached
        String? audioFilePath = await _getAudioFilePath(wal);
        if (audioFilePath == null) {
          return null;
        }

        if (wal.codec.isOpusSupported()) {
          wavFilePath = await _decodeOpusToWav(wal, audioFilePath);
        } else {
          wavFilePath = await _convertPcmToWav(wal, audioFilePath);
        }

        if (wavFilePath != null) {
          _wavFileCache[walId] = wavFilePath;
        }
      }

      if (wavFilePath != null) {
        final waveformData = await _generateWaveformFromWavFile(wavFilePath);
        _waveformCache[walId] = waveformData;
        return waveformData;
      }
    } catch (e) {
      debugPrint('Error generating waveform for WAL $walId: $e');
    }

    return null;
  }

  Future<List<double>> _generateWaveformFromWavFile(String wavFilePath) async {
    debugPrint('Generating waveform from WAV file: $wavFilePath');
    try {
      final file = File(wavFilePath);
      if (!file.existsSync()) {
        debugPrint('WAV file does not exist');
        return _generateFallbackWaveform();
      }

      final wavData = await file.readAsBytes();

      // Parse WAV header to get format information
      final wavInfo = _parseWavHeader(wavData);
      if (wavInfo == null) {
        debugPrint('Failed to parse WAV header');
        return _generateFallbackWaveform();
      }

      debugPrint(
          'WAV Info: ${wavInfo.sampleRate}Hz, ${wavInfo.channels} channels, ${wavInfo.bitsPerSample} bits, data size: ${wavInfo.dataSize}');

      // Extract PCM data starting from the data chunk
      final pcmData = wavData.sublist(wavInfo.dataOffset, wavInfo.dataOffset + wavInfo.dataSize);

      // Convert PCM bytes to samples based on the actual format
      List<double> samples = [];

      if (wavInfo.bitsPerSample == 16) {
        // 16-bit PCM samples
        for (int i = 0; i < pcmData.length - 1; i += 2) {
          // Convert two bytes to a 16-bit signed integer (little-endian)
          int sample = pcmData[i] | (pcmData[i + 1] << 8);

          // Convert to signed value
          if (sample > 32767) {
            sample = sample - 65536;
          }

          // Normalize to -1.0 to 1.0 range
          samples.add(sample / 32768.0);
        }
      } else if (wavInfo.bitsPerSample == 8) {
        // 8-bit PCM samples (unsigned)
        for (int i = 0; i < pcmData.length; i++) {
          // Convert unsigned 8-bit to signed and normalize
          int sample = pcmData[i] - 128;
          samples.add(sample / 128.0);
        }
      } else if (wavInfo.bitsPerSample == 24) {
        // 24-bit PCM samples
        for (int i = 0; i < pcmData.length - 2; i += 3) {
          // Convert three bytes to a 24-bit signed integer (little-endian)
          int sample = pcmData[i] | (pcmData[i + 1] << 8) | (pcmData[i + 2] << 16);

          // Convert to signed value
          if (sample > 8388607) {
            sample = sample - 16777216;
          }

          // Normalize to -1.0 to 1.0 range
          samples.add(sample / 8388608.0);
        }
      } else if (wavInfo.bitsPerSample == 32) {
        // 32-bit PCM samples
        for (int i = 0; i < pcmData.length - 3; i += 4) {
          // Convert four bytes to a 32-bit signed integer (little-endian)
          int sample = pcmData[i] | (pcmData[i + 1] << 8) | (pcmData[i + 2] << 16) | (pcmData[i + 3] << 24);

          // Normalize to -1.0 to 1.0 range
          samples.add(sample / 2147483648.0);
        }
      } else {
        debugPrint('Unsupported bits per sample: ${wavInfo.bitsPerSample}');
        return _generateFallbackWaveform();
      }

      // Handle multi-channel audio by taking only the first channel
      if (wavInfo.channels > 1) {
        List<double> monoSamples = [];
        for (int i = 0; i < samples.length; i += wavInfo.channels) {
          monoSamples.add(samples[i]); // Take first channel only
        }
        samples = monoSamples;
      }

      debugPrint('Extracted ${samples.length} samples from WAV file');
      return _generateWaveformFromSamples(samples);
    } catch (e) {
      debugPrint('Error generating waveform from WAV file: $e');
      return _generateFallbackWaveform();
    }
  }

  WavInfo? _parseWavHeader(Uint8List wavData) {
    try {
      if (wavData.length < 44) {
        debugPrint('WAV file too small');
        return null;
      }

      // Check RIFF header
      final riffHeader = String.fromCharCodes(wavData.sublist(0, 4));
      if (riffHeader != 'RIFF') {
        debugPrint('Invalid RIFF header: $riffHeader');
        return null;
      }

      // Check WAVE format
      final waveFormat = String.fromCharCodes(wavData.sublist(8, 12));
      if (waveFormat != 'WAVE') {
        debugPrint('Invalid WAVE format: $waveFormat');
        return null;
      }

      // Find fmt chunk
      int offset = 12;
      int fmtChunkSize = 0;
      int sampleRate = 0;
      int channels = 0;
      int bitsPerSample = 0;

      while (offset < wavData.length - 8) {
        final chunkId = String.fromCharCodes(wavData.sublist(offset, offset + 4));
        final chunkSize = ByteData.sublistView(wavData, offset + 4, offset + 8).getUint32(0, Endian.little);

        if (chunkId == 'fmt ') {
          fmtChunkSize = chunkSize;
          // Parse format chunk
          final audioFormat = ByteData.sublistView(wavData, offset + 8, offset + 10).getUint16(0, Endian.little);
          channels = ByteData.sublistView(wavData, offset + 10, offset + 12).getUint16(0, Endian.little);
          sampleRate = ByteData.sublistView(wavData, offset + 12, offset + 16).getUint32(0, Endian.little);
          bitsPerSample = ByteData.sublistView(wavData, offset + 22, offset + 24).getUint16(0, Endian.little);

          if (audioFormat != 1) {
            debugPrint('Unsupported audio format: $audioFormat (only PCM supported)');
            return null;
          }

          break;
        }

        offset += 8 + chunkSize;
        // Align to even byte boundary
        if (chunkSize % 2 == 1) offset++;
      }

      if (fmtChunkSize == 0) {
        debugPrint('fmt chunk not found');
        return null;
      }

      // Find data chunk
      offset = 12;
      while (offset < wavData.length - 8) {
        final chunkId = String.fromCharCodes(wavData.sublist(offset, offset + 4));
        final chunkSize = ByteData.sublistView(wavData, offset + 4, offset + 8).getUint32(0, Endian.little);

        if (chunkId == 'data') {
          return WavInfo(
            sampleRate: sampleRate,
            channels: channels,
            bitsPerSample: bitsPerSample,
            dataOffset: offset + 8,
            dataSize: chunkSize,
          );
        }

        offset += 8 + chunkSize;
        // Align to even byte boundary
        if (chunkSize % 2 == 1) offset++;
      }

      debugPrint('data chunk not found');
      return null;
    } catch (e) {
      debugPrint('Error parsing WAV header: $e');
      return null;
    }
  }

  List<double> _generateWaveformFromSamples(List<double> samples) {
    if (samples.isEmpty) {
      return _generateFallbackWaveform();
    }

    const int targetBars = 100; // Number of bars in waveform
    final int samplesPerWindow = (samples.length / targetBars).ceil();

    List<double> waveformData = [];

    for (int i = 0; i < targetBars; i++) {
      final startIdx = i * samplesPerWindow;
      final endIdx = math.min(startIdx + samplesPerWindow, samples.length);

      if (startIdx >= samples.length) {
        break; // Stop generating bars when we run out of samples
      }

      // Calculate RMS (Root Mean Square) for this segment - exactly like voice recorder
      double rms = 0.0;
      int count = 0;
      for (int j = startIdx; j < endIdx; j++) {
        // Square the sample and add to sum - same as voice recorder
        rms += samples[j] * samples[j];
        count++;
      }

      if (count > 0) {
        // Calculate RMS - same as voice recorder
        rms = math.sqrt(rms / count);
      }

      // Apply lighter non-linear scaling for more dynamic range
      final level = math.pow(rms, 0.6).toDouble().clamp(0.02, 1.0);
      waveformData.add(level);
    }

    return waveformData;
  }

  List<double> _generateFallbackWaveform() {
    // Return empty list when no waveform data is available
    return [];
  }

  @override
  void dispose() {
    _positionSubscription?.cancel();
    _audioPlayer?.closePlayer();
    _wal.unsubscribe(this);
    super.dispose();
  }
}

class WavInfo {
  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final int dataOffset;
  final int dataSize;

  WavInfo({
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    required this.dataOffset,
    required this.dataSize,
  });
}
