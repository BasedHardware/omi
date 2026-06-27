import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum VoiceRecorderState { idle, recording, transcribing, transcribeSuccess, transcribeFailed, pendingRecovery }

typedef VoiceMessageTranscriber = Future<String> Function(List<File> audioFiles);

class VoiceRecorderProvider extends ChangeNotifier {
  static const _wavPathKey = 'voice_recorder_pending_wav_path';

  /// Maximum WAV chunk size in bytes (10 MB of PCM data per chunk).
  /// Each chunk gets its own 44-byte WAV header so the backend can decode it independently.
  static const maxChunkPcmBytes = 10 * 1024 * 1024;

  VoiceRecorderState _state = VoiceRecorderState.idle;
  String _transcript = '';
  bool _isProcessing = false;

  // Disk-based recording: PCM chunks stream to a temp file instead of RAM
  IOSink? _pcmSink;
  File? _pcmFile;
  int _pcmBytesWritten = 0;

  // Persisted WAV file for retry (kept until transcription succeeds or user closes)
  File? _wavFile;

  // Audio visualization — more bars give the wave a denser, more "speech-like"
  // look that matches modern voice-mode designs.
  final List<double> _audioLevels = List.generate(50, (_) => 0.05);
  Timer? _waveformTimer;

  // Callbacks for UI integration
  Function(String transcript, bool autoSend)? _onTranscriptReady;
  VoidCallback? _onClose;

  // Set by the caller (e.g. tapping the send button mid-recording) before
  // processRecording() — instructs the chat page to send immediately after
  // filling the text field instead of waiting for a manual send tap.
  bool _autoSendRequested = false;
  void requestAutoSendOnNextTranscript() {
    _autoSendRequested = true;
  }

  final VoiceMessageTranscriber _transcribeVoiceMessage;

  VoiceRecorderProvider({VoiceMessageTranscriber? transcriber})
      : _transcribeVoiceMessage = transcriber ?? transcribeVoiceMessage;

  VoiceRecorderState get state => _state;
  String get transcript => _transcript;
  bool get isProcessing => _isProcessing;
  List<double> get audioLevels => List.unmodifiable(_audioLevels);
  bool get isRecording => _state == VoiceRecorderState.recording;
  bool get isActive => _state != VoiceRecorderState.idle;
  bool get hasPendingRecording => _state == VoiceRecorderState.pendingRecovery;

  /// Check for a WAV file persisted from a previous session.
  /// Call this on app startup to recover interrupted recordings.
  Future<void> checkPendingRecording() async {
    final path = SharedPreferencesUtil().getString(_wavPathKey);
    if (path.isEmpty) return;

    final file = File(path);
    if (file.existsSync()) {
      _wavFile = file;
      _state = VoiceRecorderState.pendingRecovery;
      notifyListeners();
    } else {
      // File was cleaned up externally — clear the stale preference
      await SharedPreferencesUtil().remove(_wavPathKey);
    }
  }

  void setCallbacks({Function(String transcript, bool autoSend)? onTranscriptReady, VoidCallback? onClose}) {
    _onTranscriptReady = onTranscriptReady;
    _onClose = onClose;
  }

  void clearCallbacks() {
    _onTranscriptReady = null;
    _onClose = null;
  }

  static const _audioSessionChannel = MethodChannel('com.omi.ios/audioSession');

  Future<void> startRecording() async {
    if (_state == VoiceRecorderState.recording) return;

    _state = VoiceRecorderState.recording;
    _transcript = '';
    _pcmBytesWritten = 0;

    // Clean up any previous WAV file
    await _cleanupWavFile();

    // Create a persisted PCM file for streaming audio to disk.
    final recordingsDir = await _recordingsDirectory();
    _pcmFile = File('${recordingsDir.path}/voice_recording_${DateTime.now().millisecondsSinceEpoch}.pcm');
    _pcmSink = _pcmFile!.openWrite();

    // Reset audio levels
    for (int i = 0; i < _audioLevels.length; i++) {
      _audioLevels[i] = 0.1;
    }
    notifyListeners();

    await Permission.microphone.request();

    // Configure audio session for Bluetooth before starting recorder.
    if (Platform.isIOS) {
      try {
        await _audioSessionChannel.invokeMethod('configureForBluetooth');
      } catch (e) {
        Logger.debug('VoiceRecorderProvider: Failed to configure audio session for Bluetooth: $e');
      }
    }

    // Repaint at ~60Hz so the wave flows smoothly. Levels are shifted in
    // onByteReceived (audio callback rate, much faster than the UI), but the
    // canvas only re-renders on notifyListeners — so a slower timer made the
    // wave appear frozen / laggy.
    _waveformTimer = Timer.periodic(const Duration(milliseconds: 16), (_) {
      if (_state == VoiceRecorderState.recording) {
        notifyListeners();
      }
    });

    await ServiceManager.instance().mic.start(
      onByteReceived: (bytes) {
        if (_state == VoiceRecorderState.recording) {
          // Write to disk instead of accumulating in RAM
          _pcmSink?.add(bytes);
          _pcmBytesWritten += bytes.length;

          // Update audio visualization based on actual audio levels
          if (bytes.isNotEmpty) {
            double rms = 0;
            for (int i = 0; i < bytes.length - 1; i += 2) {
              int sample = bytes[i] | (bytes[i + 1] << 8);
              if (sample > 32767) {
                sample = sample - 65536;
              }
              rms += sample * sample;
            }

            int sampleCount = bytes.length ~/ 2;
            if (sampleCount > 0) {
              rms = math.sqrt(rms / sampleCount) / 32768.0;
            } else {
              rms = 0;
            }

            // Wider dynamic range so quiet sections stay near zero and loud
            // peaks reach the full bar height. The 0.5 exponent boosts mid
            // levels so normal speech has visible amplitude.
            final level = math.pow(rms, 0.5).toDouble().clamp(0.02, 1.0);

            for (int i = 0; i < _audioLevels.length - 1; i++) {
              _audioLevels[i] = _audioLevels[i + 1];
            }
            _audioLevels[_audioLevels.length - 1] = level;
          }
        }
      },
      onRecording: () {
        Logger.debug('VoiceRecorderProvider: Recording started');
        _state = VoiceRecorderState.recording;
        // Reset audio levels
        for (int i = 0; i < _audioLevels.length; i++) {
          _audioLevels[i] = 0.1;
        }
        notifyListeners();
      },
      onStop: () {
        Logger.debug('VoiceRecorderProvider: Recording stopped');
      },
      onInitializing: () {
        Logger.debug('VoiceRecorderProvider: Initializing');
      },
    );
  }

  void stopRecording() {
    _waveformTimer?.cancel();
    ServiceManager.instance().mic.stop();
  }

  Future<void> processRecording() async {
    if (_isProcessing) return;

    _state = VoiceRecorderState.transcribing;
    _isProcessing = true;
    notifyListeners();

    stopRecording();

    try {
      // Flush and close the PCM sink
      await _pcmSink?.flush();
      await _pcmSink?.close();
      _pcmSink = null;

      // Check minimum audio length (0.5 seconds at 16kHz PCM16 = 16000 bytes)
      const int minAudioBytes = 16000;
      final pcmLength = _pcmFile != null && _pcmFile!.existsSync() ? await _pcmFile!.length() : _pcmBytesWritten;
      if (pcmLength < minAudioBytes) {
        Logger.debug('Audio too short ($pcmLength bytes), closing without error');
        close();
        return;
      }

      // Convert PCM file to WAV file (reads from disk, writes to disk — no full-file RAM copy)
      // Keep PCM file until WAV is confirmed on disk — if conversion fails, PCM is the only copy
      _wavFile = await _convertPcmFileToWavFile(_pcmFile!, 16000, 1);

      // Persist WAV path so user can retry if the app is closed
      await SharedPreferencesUtil().saveString(_wavPathKey, _wavFile!.path);

      // WAV conversion succeeded — safe to delete PCM file now
      await _cleanupPcmFile();

      // Split into chunks if the WAV is large, then transcribe
      final chunks = await splitWavFileIfNeeded(_wavFile!, 16000, 1);
      try {
        final transcript = await _transcribeVoiceMessage(chunks);
        if (transcript.trim().isNotEmpty) {
          _transcript = transcript;
          _state = VoiceRecorderState.transcribeSuccess;
          _isProcessing = false;
          notifyListeners();
          final autoSend = _autoSendRequested;
          _autoSendRequested = false;
          _onTranscriptReady?.call(transcript, autoSend);
          close();
        } else {
          Logger.debug('Empty transcript received; preserving recording for retry');
          _markTranscriptionFailed();
        }
      } finally {
        _cleanupChunkFiles(chunks);
      }
    } catch (e) {
      Logger.debug('Error processing recording: $e');
      // Only clean up PCM if WAV exists (conversion succeeded).
      // If WAV conversion failed, keep PCM as the only surviving copy.
      if (_wavFile != null && _wavFile!.existsSync()) {
        await _cleanupPcmFile();
      }
      _state = VoiceRecorderState.transcribeFailed;
      _isProcessing = false;
      notifyListeners();
      _showTranscriptionFailedSnackbar();
    }
  }

  Future<void> retry() async {
    if (_wavFile != null && _wavFile!.existsSync()) {
      // Retry transcription with existing WAV file on disk (no re-encoding needed)
      await _retryTranscription();
    } else if (_pcmFile != null && _pcmFile!.existsSync()) {
      // WAV conversion failed but PCM survived — retry from PCM
      await processRecording();
    } else {
      await startRecording();
    }
  }

  Future<void> _retryTranscription() async {
    if (_isProcessing) return;

    _state = VoiceRecorderState.transcribing;
    _isProcessing = true;
    notifyListeners();

    try {
      final chunks = await splitWavFileIfNeeded(_wavFile!, 16000, 1);
      try {
        final transcript = await _transcribeVoiceMessage(chunks);
        if (transcript.trim().isNotEmpty) {
          _transcript = transcript;
          _state = VoiceRecorderState.transcribeSuccess;
          _isProcessing = false;
          notifyListeners();
          final autoSend = _autoSendRequested;
          _autoSendRequested = false;
          _onTranscriptReady?.call(transcript, autoSend);
          close();
        } else {
          Logger.debug('Empty transcript received on retry; preserving recording for retry');
          _markTranscriptionFailed();
        }
      } finally {
        _cleanupChunkFiles(chunks);
      }
    } catch (e) {
      Logger.debug('Error retrying transcription: $e');
      _state = VoiceRecorderState.transcribeFailed;
      _isProcessing = false;
      notifyListeners();
      _showTranscriptionFailedSnackbar();
    }
  }

  static Future<Directory> _recordingsDirectory() async {
    final supportDir = await getApplicationSupportDirectory();
    final directory = Directory('${supportDir.path}/voice_recordings');
    if (!directory.existsSync()) {
      await directory.create(recursive: true);
    }
    return directory;
  }

  /// Convert a PCM file on disk to a WAV file on disk.
  /// Reads and writes in chunks to avoid loading the entire file into memory.
  static Future<File> _convertPcmFileToWavFile(File pcmFile, int sampleRate, int channels) async {
    final pcmLength = await pcmFile.length();
    final wavHeader = WavBytesUtil.getWavHeader(pcmLength, sampleRate, channelCount: channels);

    final recordingsDir = await _recordingsDirectory();
    final wavPath = '${recordingsDir.path}/voice_recording_${DateTime.now().millisecondsSinceEpoch}.wav';
    final wavFile = File(wavPath);
    final sink = wavFile.openWrite();

    // Write 44-byte WAV header
    sink.add(wavHeader);

    // Stream PCM data in chunks (64KB) — never loads entire file into RAM
    const chunkSize = 65536;
    final reader = pcmFile.openRead();
    await for (final chunk in reader) {
      sink.add(chunk);
    }

    await sink.flush();
    await sink.close();

    Logger.debug('WAV file created: $wavPath (${pcmLength + 44} bytes from $pcmLength PCM bytes)');
    return wavFile;
  }

  Future<void> _cleanupPcmFile() async {
    try {
      if (_pcmFile != null && _pcmFile!.existsSync()) {
        await _pcmFile!.delete();
      }
    } catch (e) {
      Logger.debug('Error cleaning up PCM file: $e');
    }
    _pcmFile = null;
  }

  Future<void> _cleanupWavFile() async {
    try {
      if (_wavFile != null && _wavFile!.existsSync()) {
        await _wavFile!.delete();
      }
    } catch (e) {
      Logger.debug('Error cleaning up WAV file: $e');
    }
    _wavFile = null;
    await SharedPreferencesUtil().remove(_wavPathKey);
  }

  /// Split a WAV file into multiple chunk files if it exceeds [maxChunkPcmBytes].
  /// Each chunk is a standalone WAV file with its own header.
  /// Returns the original file in a single-element list if no splitting is needed.
  @visibleForTesting
  static Future<List<File>> splitWavFileIfNeeded(File wavFile, int sampleRate, int channels) async {
    final fileLength = await wavFile.length();
    final pcmLength = fileLength - 44; // subtract WAV header

    if (pcmLength <= maxChunkPcmBytes) {
      return [wavFile];
    }

    final chunks = <File>[];
    final tempDir = await getTemporaryDirectory();
    final timestamp = DateTime.now().millisecondsSinceEpoch;
    final reader = wavFile.openRead(44); // skip the original WAV header

    int chunkIndex = 0;
    int pcmBytesRemaining = pcmLength;
    final buffer = BytesBuilder(copy: false);

    await for (final data in reader) {
      buffer.add(data);

      while (buffer.length >= maxChunkPcmBytes && pcmBytesRemaining > 0) {
        final chunkBytes = buffer.takeBytes();
        final chunkPcmSize = chunkBytes.length < maxChunkPcmBytes ? chunkBytes.length : maxChunkPcmBytes;

        final chunkFile = File('${tempDir.path}/voice_chunk_${timestamp}_$chunkIndex.wav');
        final sink = chunkFile.openWrite();
        sink.add(WavBytesUtil.getWavHeader(chunkPcmSize, sampleRate, channelCount: channels));
        sink.add(chunkBytes.sublist(0, chunkPcmSize));
        await sink.flush();
        await sink.close();

        chunks.add(chunkFile);
        pcmBytesRemaining -= chunkPcmSize;
        chunkIndex++;

        // Put leftover bytes back
        if (chunkBytes.length > chunkPcmSize) {
          buffer.add(chunkBytes.sublist(chunkPcmSize));
        }
      }
    }

    // Write remaining bytes as the final chunk
    if (buffer.length > 0) {
      final remaining = buffer.takeBytes();
      final chunkFile = File('${tempDir.path}/voice_chunk_${timestamp}_$chunkIndex.wav');
      final sink = chunkFile.openWrite();
      sink.add(WavBytesUtil.getWavHeader(remaining.length, sampleRate, channelCount: channels));
      sink.add(remaining);
      await sink.flush();
      await sink.close();
      chunks.add(chunkFile);
    }

    Logger.debug('Split WAV into ${chunks.length} chunks from $pcmLength PCM bytes');
    return chunks;
  }

  /// Clean up chunk files after transcription (but not the original WAV).
  void _cleanupChunkFiles(List<File> chunks) {
    for (final chunk in chunks) {
      // Don't delete the original WAV file — only delete split chunks
      if (chunk.path != _wavFile?.path) {
        try {
          if (chunk.existsSync()) chunk.deleteSync();
        } catch (e) {
          Logger.debug('Error cleaning up chunk file: $e');
        }
      }
    }
  }

  void _markTranscriptionFailed() {
    _state = VoiceRecorderState.transcribeFailed;
    _isProcessing = false;
    notifyListeners();
    _showTranscriptionFailedSnackbar();
  }

  void _showTranscriptionFailedSnackbar() {
    final context = globalNavigatorKey.currentContext;
    if (context == null) return;
    AppSnackbar.showSnackbarError(context.l10n.voiceFailedToTranscribe);
  }

  void close() {
    if (_state == VoiceRecorderState.idle) {
      return;
    }

    if (_state == VoiceRecorderState.recording) {
      stopRecording();
    }
    _waveformTimer?.cancel();
    _state = VoiceRecorderState.idle;
    _transcript = '';
    _isProcessing = false;
    _pcmBytesWritten = 0;
    _autoSendRequested = false;

    // Close PCM sink if still open
    _pcmSink?.close();
    _pcmSink = null;

    // Clean up temp files
    _cleanupPcmFile();
    _cleanupWavFile();

    // Reset audio levels
    for (int i = 0; i < _audioLevels.length; i++) {
      _audioLevels[i] = 0.1;
    }

    notifyListeners();
    _onClose?.call();
  }

  @override
  void dispose() {
    _waveformTimer?.cancel();
    _pcmSink?.close();
    if (_state == VoiceRecorderState.recording) {
      ServiceManager.instance().mic.stop();
    }
    super.dispose();
  }
}
