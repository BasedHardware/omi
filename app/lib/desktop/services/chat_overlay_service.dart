import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/file.dart';

enum ChatRecordingState {
  notRecording,
  recording,
  transcribing,
  transcribeSuccess,
  transcribeFailed,
}

class ChatOverlayService {
  static final ChatOverlayService _instance = ChatOverlayService._internal();
  factory ChatOverlayService() => _instance;
  ChatOverlayService._internal();

  MethodChannel? _overlayChannel;
  static const _permissionChannel = MethodChannel('screenCapturePlatform');
  
  ChatRecordingState _state = ChatRecordingState.notRecording;
  List<List<int>> _audioChunks = [];
  String _transcript = '';
  bool _isProcessing = false;
  bool _isOverlayVisible = false;
  
  // Audio visualization
  final List<double> _audioLevels = List.generate(20, (_) => 0.1);
  Timer? _waveformTimer;
  
  // Callbacks
  Function(String)? onTranscriptReady;
  VoidCallback? onClose;

  static Future<void> initialize() async {
    final instance = ChatOverlayService();
    if (instance._overlayChannel == null) {
      final channel = const MethodChannel('overlayPlatform');
      instance.setOverlayChannel(channel);
      
      // Notify the native side that the channel is connected
      try {
        await channel.invokeMethod('setChatOverlayChannel');
        debugPrint('🔧 ChatOverlayService: Initialized and connected to native channel');
      } catch (e) {
        debugPrint('❌ ChatOverlayService: Failed to connect to native channel: $e');
      }
    }
  }

  void setOverlayChannel(MethodChannel channel) {
    _overlayChannel = channel;
    _overlayChannel?.setMethodCallHandler(_handleMethodCall);
    debugPrint('🔧 ChatOverlayService: Overlay channel set and handler registered');
  }

  ChatRecordingState get state => _state;
  String get transcript => _transcript;
  bool get isOverlayVisible => _isOverlayVisible;

  Future<void> _handleMethodCall(MethodCall call) async {
    debugPrint('🔧 ChatOverlayService received method call: ${call.method}');
    
    switch (call.method) {
      case 'onChatCheck':
        debugPrint('🔵 CHAT CHECK RECEIVED - Processing recording...');
        await processRecording();
        break;
        
      case 'onChatSend':
        final args = call.arguments as Map<String, dynamic>?;
        final transcript = args?['transcript'] as String? ?? _transcript;
        debugPrint('🔵 CHAT SEND RECEIVED - Transcript: "$transcript"');
        await sendTranscript();
        break;
        
      case 'onChatRetry':
        debugPrint('🔵 CHAT RETRY RECEIVED - Retrying recording...');
        await retryRecording();
        break;
        
      case 'onChatOverlayHidden':
        debugPrint('🔵 CHAT OVERLAY HIDDEN - Marking as hidden...');
        markOverlayHidden();
        break;
        
      case 'setChatOverlayChannel':
        debugPrint('🔧 CHAT OVERLAY CHANNEL SETUP - Channel connection confirmed');
        // Channel is already set up, this is just a confirmation
        break;
        
      default:
        debugPrint('❌ Unknown method call: ${call.method}');
    }
  }

  Future<void> toggleOverlay() async {
    if (_isOverlayVisible) {
      await hideOverlay();
    } else {
      await showOverlay();
    }
  }

  Future<void> showOverlay() async {
    try {
      // Ensure the service is initialized with the proper channel
      await initialize();
      
      debugPrint('');
      debugPrint('🟢 ================================================');
      debugPrint('🟢 SHOWING OVERLAY: Starting recording...');
      debugPrint('🟢 ================================================');
      
      await _overlayChannel?.invokeMethod('showChatOverlay');
      _isOverlayVisible = true;
      // Auto-start recording when overlay is shown
      await startRecording();
    } catch (e) {
      debugPrint('❌ Error showing chat overlay: $e');
    }
  }

  Future<void> hideOverlay() async {
    try {
      await stopRecording();
      await _overlayChannel?.invokeMethod('hideChatOverlay');
      _isOverlayVisible = false;
    } catch (e) {
      print('Error hiding chat overlay: $e');
    }
  }

  void markOverlayHidden() {
    _isOverlayVisible = false;
  }

  Future<void> startRecording() async {
    try {
      // Request microphone permission using existing custom system
      final hasPermission = await _requestMicrophonePermission();
      if (!hasPermission) {
        print('Microphone permission denied');
        _setState(ChatRecordingState.transcribeFailed);
        return;
      }
      
      _setState(ChatRecordingState.recording);
      _audioChunks = [];
      
      // Reset audio levels
      for (int i = 0; i < _audioLevels.length; i++) {
        _audioLevels[i] = 0.1;
      }
      
      // Start waveform timer with higher frequency for more responsive display
      _waveformTimer = Timer.periodic(const Duration(milliseconds: 50), (_) {
        if (_state == ChatRecordingState.recording) {
          _sendWaveformUpdate();
        }
      });

      // Use systemAudio for macOS desktop recording
      await ServiceManager.instance().systemAudio.start(
        onByteReceived: (bytes) {
          if (_state == ChatRecordingState.recording) {
            _audioChunks.add(bytes.toList());
            _processAudioBytes(bytes);
          }
        },
        onFormatReceived: (format) {
          // Audio format received, could be used for debugging
          print('Audio format: $format');
        },
        onRecording: () {
          print('Chat overlay recording started');
        },
        onStop: () {
          print('Chat overlay recording stopped');
        },
        onError: (error) {
          print('Chat overlay recording error: $error');
          _setState(ChatRecordingState.transcribeFailed);
        },
      );
    } catch (e) {
      print('Error starting chat recording: $e');
      _setState(ChatRecordingState.transcribeFailed);
    }
  }

  Future<void> stopRecording() async {
    try {
      _waveformTimer?.cancel();
      ServiceManager.instance().systemAudio.stop();
    } catch (e) {
      print('Error stopping recording: $e');
    }
  }

  Future<void> processRecording() async {
    print('🔄 PROCESS RECORDING CALLED');
    
    if (_audioChunks.isEmpty) {
      debugPrint('❌ No audio chunks to process, closing overlay');
      hideOverlay();
      return;
    }

    debugPrint('🔄 Starting transcription process...');
    debugPrint('🔄 Audio chunks collected: ${_audioChunks.length}');
    
    _setState(ChatRecordingState.transcribing);
    await stopRecording();

    List<int> flattenedBytes = [];
    for (var chunk in _audioChunks) {
      flattenedBytes.addAll(chunk);
    }

    final audioFile = await FileUtils.convertPcmToWavFile(
      Uint8List.fromList(flattenedBytes),
      16000,
      1,
    );

    try {
      debugPrint('🔄 Calling transcription API...');
      final transcriptResult = await transcribeVoiceMessage(audioFile);
      _transcript = transcriptResult;
      
      if (transcriptResult.isNotEmpty) {
        _setState(ChatRecordingState.transcribeSuccess);
        await _updateTranscript(transcriptResult);
        
        // Prominent debug output for transcription completion
        debugPrint('');
        debugPrint('🎯 ================================================');
        debugPrint('🎯 TRANSCRIPTION SUCCESS!');
        debugPrint('🎯 RESULT: "$transcriptResult"');
        debugPrint('🎯 ================================================');
        debugPrint('');
        
        // Show transcript for longer before auto-close
        debugPrint('⏳ Showing transcript for 3 seconds before closing...');
        await Future.delayed(const Duration(milliseconds: 3000));
        
        debugPrint('🔄 Auto-closing overlay...');
        await hideOverlay();
      } else {
        _setState(ChatRecordingState.transcribeFailed);
        debugPrint('');
        debugPrint('❌ ================================================');
        debugPrint('❌ TRANSCRIPTION FAILED: Empty result');
        debugPrint('❌ ================================================');
        debugPrint('');
        
        // Auto-close on failure after showing error briefly
        debugPrint('⏳ Showing error for 2 seconds before closing...');
        await Future.delayed(const Duration(milliseconds: 2000));
        debugPrint('🔄 Auto-closing overlay after failure...');
        await hideOverlay();
      }
    } catch (e) {
      debugPrint('');
      debugPrint('❌ ================================================');
      debugPrint('❌ TRANSCRIPTION ERROR: $e');
      debugPrint('❌ ================================================');
      debugPrint('');
      _setState(ChatRecordingState.transcribeFailed);
      
      // Auto-close on error after showing error briefly
      debugPrint('⏳ Showing error for 2 seconds before closing...');
      await Future.delayed(const Duration(milliseconds: 2000));
      debugPrint('🔄 Auto-closing overlay after error...');
      await hideOverlay();
    }
  }

  Future<void> retryRecording() async {
    if (_audioChunks.isEmpty) {
      await startRecording();
    } else {
      await processRecording();
    }
  }

  Future<void> sendTranscript() async {
    if (_transcript.isNotEmpty) {
      onTranscriptReady?.call(_transcript);
      hideOverlay();
    }
  }

  void _processAudioBytes(Uint8List bytes) {
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

      // Use more linear scaling to preserve dynamic range better
      // Apply gentler compression and wider range for more visible variation
      final level = math.pow(rms, 0.8).toDouble().clamp(0.01, 1.0);

      // Debug audio processing every 500ms to verify data flow
      if (DateTime.now().millisecondsSinceEpoch % 500 < 100) {
        debugPrint('🎤 AUDIO DEBUG: ${bytes.length} bytes, RMS: ${rms.toStringAsFixed(4)}, Level: ${level.toStringAsFixed(4)}');
      }

      // Shift audio levels and add new level
      for (int i = 0; i < _audioLevels.length - 1; i++) {
        _audioLevels[i] = _audioLevels[i + 1];
      }
      _audioLevels[_audioLevels.length - 1] = level;
    }
  }

  Future<void> _setState(ChatRecordingState newState) async {
    _state = newState;
    
    String stateString;
    switch (newState) {
      case ChatRecordingState.recording:
        stateString = 'recording';
        break;
      case ChatRecordingState.transcribing:
        stateString = 'transcribing';
        break;
      case ChatRecordingState.transcribeSuccess:
        stateString = 'transcribeSuccess';
        break;
      case ChatRecordingState.transcribeFailed:
        stateString = 'transcribeFailed';
        break;
      default:
        stateString = 'recording';
    }
    
    try {
      await _overlayChannel?.invokeMethod('updateChatOverlayState', {
        'state': stateString,
      });
    } catch (e) {
      print('Error updating chat overlay state: $e');
    }
  }

  Future<void> _sendWaveformUpdate() async {
    try {
      // Debug waveform data every 1 second to verify levels are being sent
      if (DateTime.now().millisecondsSinceEpoch % 1000 < 50) {
        final sampledLevels = _audioLevels.take(5).map((l) => l.toStringAsFixed(2)).join(', ');
        debugPrint('🎵 WAVEFORM UPDATE: [$sampledLevels...] (first 5 of ${_audioLevels.length})');
      }
      
      await _overlayChannel?.invokeMethod('updateChatWaveform', {
        'levels': _audioLevels,
      });
    } catch (e) {
      debugPrint('❌ Error sending waveform update: $e');
    }
  }

  Future<void> _updateTranscript(String transcript) async {
    try {
      await _overlayChannel?.invokeMethod('setChatOverlayTranscript', {
        'transcript': transcript,
      });
    } catch (e) {
      print('Error updating transcript: $e');
    }
  }

  Future<bool> _requestMicrophonePermission() async {
    try {
      // Check current permission status first
      final currentStatus = await _permissionChannel.invokeMethod('checkMicrophonePermission');
      if (currentStatus == 'granted') {
        return true;
      }
      
      // Request permission if not already granted
      final granted = await _permissionChannel.invokeMethod('requestMicrophonePermission');
      return granted as bool? ?? false;
    } catch (e) {
      print('Error requesting microphone permission: $e');
      return false;
    }
  }

  void dispose() {
    _waveformTimer?.cancel();
    if (_state == ChatRecordingState.recording) {
      ServiceManager.instance().systemAudio.stop();
    }
  }
}