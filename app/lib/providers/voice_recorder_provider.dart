import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/file.dart';
import 'package:permission_handler/permission_handler.dart';

enum VoiceRecorderState {
  idle,
  recording,
  transcribing,
  transcribeSuccess,
  transcribeFailed,
}

class VoiceRecorderProvider extends ChangeNotifier {
  VoiceRecorderState _state = VoiceRecorderState.idle;
  List<List<int>> _audioChunks = [];
  String _transcript = '';
  bool _isProcessing = false;

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

  void setCallbacks({
    Function(String transcript)? onTranscriptReady,
    VoidCallback? onClose,
  }) {
    _onTranscriptReady = onTranscriptReady;
    _onClose = onClose;
  }

  void clearCallbacks() {
    _onTranscriptReady = null;
    _onClose = null;
  }

  Future<void> startRecording() async {
    if (_state == VoiceRecorderState.recording) return;

    _state = VoiceRecorderState.recording;
    _audioChunks = [];
    _transcript = '';

    // Reset audio levels
    for (int i = 0; i < _audioLevels.length; i++) {
      _audioLevels[i] = 0.1;
    }
    notifyListeners();

    await Permission.microphone.request();

    // Setup timer to update the wave visualization every second
    _waveformTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_state == VoiceRecorderState.recording) {
        notifyListeners();
      }
    });

    await ServiceManager.instance().mic.start(
      onByteReceived: (bytes) {
        if (_state == VoiceRecorderState.recording) {
          _audioChunks.add(bytes.toList());

          // Update audio visualization based on actual audio levels
          if (bytes.isNotEmpty) {
            // Calculate RMS (Root Mean Square) for PCM16 audio data
            double rms = 0;

            // Process bytes as 16-bit samples (2 bytes per sample)
            for (int i = 0; i < bytes.length - 1; i += 2) {
              // Convert two bytes to a 16-bit signed integer
              // PCM16 is little-endian: LSB first, then MSB
              int sample = bytes[i] | (bytes[i + 1] << 8);

              // Convert to signed value (if high bit is set)
              if (sample > 32767) {
                sample = sample - 65536;
              }

              // Square the sample and add to sum
              rms += sample * sample;
            }

            // Calculate RMS and normalize to 0.0-1.0 range
            // 32768 is max absolute value for 16-bit audio
            int sampleCount = bytes.length ~/ 2;
            if (sampleCount > 0) {
              rms = math.sqrt(rms / sampleCount) / 32768.0;
            } else {
              rms = 0;
            }

            // Apply non-linear scaling to make quiet sounds more visible
            // and loud sounds more dramatic
            final level = math.pow(rms, 0.4).toDouble().clamp(0.1, 1.0);

            // Shift all values left
            for (int i = 0; i < _audioLevels.length - 1; i++) {
              _audioLevels[i] = _audioLevels[i + 1];
            }

            // Add new level at the end
            _audioLevels[_audioLevels.length - 1] = level;
          }
        }
      },
      onRecording: () {
        debugPrint('VoiceRecorderProvider: Recording started');
        _state = VoiceRecorderState.recording;
        _audioChunks = [];
        // Reset audio levels
        for (int i = 0; i < _audioLevels.length; i++) {
          _audioLevels[i] = 0.1;
        }
        notifyListeners();
      },
      onStop: () {
        debugPrint('VoiceRecorderProvider: Recording stopped');
      },
      onInitializing: () {
        debugPrint('VoiceRecorderProvider: Initializing');
      },
    );
  }

  void stopRecording() {
    _waveformTimer?.cancel();
    ServiceManager.instance().mic.stop();
  }

  Future<void> processRecording() async {
    if (_audioChunks.isEmpty) {
      close();
      return;
    }

    _state = VoiceRecorderState.transcribing;
    _isProcessing = true;
    notifyListeners();

    stopRecording();

    // Flatten audio chunks into a single list
    List<int> flattenedBytes = [];
    for (var chunk in _audioChunks) {
      flattenedBytes.addAll(chunk);
    }

    // Convert PCM to WAV file
    final audioFile = await FileUtils.convertPcmToWavFile(
      Uint8List.fromList(flattenedBytes),
      16000, // Sample rate
      1, // Mono channel
    );

    try {
      final transcript = await transcribeVoiceMessage(audioFile);
      _transcript = transcript;
      _state = VoiceRecorderState.transcribeSuccess;
      _isProcessing = false;
      notifyListeners();

      if (transcript.isNotEmpty) {
        _onTranscriptReady?.call(transcript);
        // Auto-close after successful transcription
        close();
      }
    } catch (e) {
      debugPrint('Error processing recording: $e');
      _state = VoiceRecorderState.transcribeFailed;
      _isProcessing = false;
      notifyListeners();
      AppSnackbar.showSnackbarError('Failed to transcribe audio');
    }
  }

  void retry() {
    if (_audioChunks.isEmpty) {
      startRecording();
    } else {
      // Retry transcription with existing audio data
      processRecording();
    }
  }

  void close() {
    if (_state == VoiceRecorderState.recording) {
      stopRecording();
    }
    _waveformTimer?.cancel();
    _state = VoiceRecorderState.idle;
    _audioChunks = [];
    _transcript = '';
    _isProcessing = false;
    
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
    if (_state == VoiceRecorderState.recording) {
      ServiceManager.instance().mic.stop();
    }
    super.dispose();
  }
}

