import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/l10n_extensions.dart';

enum VoiceRecorderState { idle, recording, transcribing, transcribeSuccess, transcribeFailed }

class VoiceRecorderProvider extends ChangeNotifier {
  VoiceRecorderState _state = VoiceRecorderState.idle;
  String _transcript = '';
  bool _isProcessing = false;

  // Disk-based recording: PCM chunks stream to a temp file instead of RAM
  IOSink? _pcmSink;
  File? _pcmFile;
  int _pcmBytesWritten = 0;

  // Persisted WAV file for retry (kept until transcription succeeds or user closes)
  File? _wavFile;

  // Audio visualization
  final List<double> _audioLevels = List.generate(20, (_) => 0.1);
  Timer? _waveformTimer;

  // Callbacks for UI integration
  Function(String transcript)? _onTranscriptReady;
  VoidCallback? _onClose;

  VoiceRecorderState get state => _state;
  String get transcript => _transcript;
  bool get isProcessing => _isProcessing;
  List<double> get audioLevels => List.unmodifiable(_audioLevels);
  bool get isRecording => _state == VoiceRecorderState.recording;
  bool get isActive => _state != VoiceRecorderState.idle;

  void setCallbacks({Function(String transcript)? onTranscriptReady, VoidCallback? onClose}) {
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

    // Create temp PCM file for streaming audio to disk
    final tempDir = await getTemporaryDirectory();
    _pcmFile = File('${tempDir.path}/voice_recording_${DateTime.now().millisecondsSinceEpoch}.pcm');
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

    // Setup timer to update the wave visualization every second
    _waveformTimer = Timer.periodic(const Duration(seconds: 1), (_) {
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

            final level = math.pow(rms, 0.4).toDouble().clamp(0.1, 1.0);

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

      // WAV conversion succeeded — safe to delete PCM file now
      await _cleanupPcmFile();

      final transcript = await transcribeVoiceMessage(_wavFile!);
      _transcript = transcript;
      _state = VoiceRecorderState.transcribeSuccess;
      _isProcessing = false;
      notifyListeners();

      if (transcript.isNotEmpty) {
        _onTranscriptReady?.call(transcript);
        close();
      } else {
        Logger.debug('Empty transcript received, closing without error');
        close();
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
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.voiceFailedToTranscribe ?? 'Failed to transcribe audio',
      );
    }
  }

  void retry() {
    if (_wavFile != null && _wavFile!.existsSync()) {
      // Retry transcription with existing WAV file on disk (no re-encoding needed)
      _retryTranscription();
    } else if (_pcmFile != null && _pcmFile!.existsSync()) {
      // WAV conversion failed but PCM survived — retry from PCM
      processRecording();
    } else {
      startRecording();
    }
  }

  Future<void> _retryTranscription() async {
    if (_isProcessing) return;

    _state = VoiceRecorderState.transcribing;
    _isProcessing = true;
    notifyListeners();

    try {
      final transcript = await transcribeVoiceMessage(_wavFile!);
      _transcript = transcript;
      _state = VoiceRecorderState.transcribeSuccess;
      _isProcessing = false;
      notifyListeners();

      if (transcript.isNotEmpty) {
        _onTranscriptReady?.call(transcript);
        close();
      } else {
        Logger.debug('Empty transcript received on retry, closing without error');
        close();
      }
    } catch (e) {
      Logger.debug('Error retrying transcription: $e');
      _state = VoiceRecorderState.transcribeFailed;
      _isProcessing = false;
      notifyListeners();
      AppSnackbar.showSnackbarError(
        globalNavigatorKey.currentContext?.l10n.voiceFailedToTranscribe ?? 'Failed to transcribe audio',
      );
    }
  }

  /// Convert a PCM file on disk to a WAV file on disk.
  /// Reads and writes in chunks to avoid loading the entire file into memory.
  static Future<File> _convertPcmFileToWavFile(File pcmFile, int sampleRate, int channels) async {
    final pcmLength = await pcmFile.length();
    final wavHeader = WavBytesUtil.getWavHeader(pcmLength, sampleRate, channelCount: channels);

    final tempDir = await getTemporaryDirectory();
    final wavPath = '${tempDir.path}/voice_recording_${DateTime.now().millisecondsSinceEpoch}.wav';
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
