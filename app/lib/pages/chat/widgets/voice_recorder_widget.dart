import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/file.dart';
import 'package:permission_handler/permission_handler.dart';

enum RecordingState {
  notRecording,
  recording,
  transcribing,
  transcribeSuccess,
  transcribeFailed,
}

class VoiceRecorderWidget extends StatefulWidget {
  final Function(String) onTranscriptReady;
  final VoidCallback onClose;

  const VoiceRecorderWidget({
    super.key,
    required this.onTranscriptReady,
    required this.onClose,
  });

  @override
  State<VoiceRecorderWidget> createState() => _VoiceRecorderWidgetState();
}

class _VoiceRecorderWidgetState extends State<VoiceRecorderWidget> with SingleTickerProviderStateMixin {
  RecordingState _state = RecordingState.recording;
  List<List<int>> _audioChunks = [];
  String _transcript = '';
  bool _isProcessing = false;
  
  // Audio visualization
  final List<double> _audioLevels = List.generate(20, (_) => 0.1);
  late AnimationController _animationController;
  Timer? _waveformTimer;
  
  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);
    
    _startRecording();
  }
  
  @override
  void dispose() {
    _animationController.dispose();
    _waveformTimer?.cancel();
    if (_state == RecordingState.recording) {
      _stopRecording();
    }
    super.dispose();
  }
  
  Future<void> _startRecording() async {
    // Request microphone permission
    var status = await Permission.microphone.request();
    if (status != PermissionStatus.granted) {
      AppSnackbar.showSnackbarError('Microphone permission is required to record audio');
      widget.onClose();
      return;
    }
    
    setState(() {
      _state = RecordingState.recording;
      _audioChunks = [];
      // Reset audio levels
      for (int i = 0; i < _audioLevels.length; i++) {
        _audioLevels[i] = 0.1;
      }
    });
    
    // Start the waveform animation
    _waveformTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (_state == RecordingState.recording) {
        setState(() {
          for (int i = 0; i < _audioLevels.length; i++) {
            _audioLevels[i] = 0.1 + 0.9 * (0.2 + 0.8 * (i % 3 == 0 ? 0.8 : 0.5)) * (0.5 + 0.5 * _animationController.value);
          }
        });
      }
    });
    
    try {
      await ServiceManager.instance().mic.start(
        onByteReceived: (bytes) {
          if (_state == RecordingState.recording) {
            setState(() {
              _audioChunks.add(bytes.toList());
              
              // Update audio visualization based on actual audio levels
              if (bytes.isNotEmpty) {
                final sum = bytes.fold<int>(0, (sum, value) => sum + value.abs());
                final avg = sum / bytes.length;
                final level = (avg / 128).clamp(0.1, 1.0); // Normalize to 0.1-1.0 range
                
                // Shift values in the array instead of removing/adding
                for (int i = 0; i < _audioLevels.length - 1; i++) {
                  _audioLevels[i] = _audioLevels[i + 1];
                }
                _audioLevels[_audioLevels.length - 1] = level;
              }
            });
          }
        },
        onRecording: () {
          debugPrint('Recording started');
        },
        onStop: () {
          debugPrint('Recording stopped');
        },
      );
    } catch (e) {
      debugPrint('Error starting recording: $e');
      setState(() {
        _state = RecordingState.transcribeFailed;
      });
      AppSnackbar.showSnackbarError('Failed to start recording: $e');
    }
  }
  
  Future<void> _stopRecording() async {
    _waveformTimer?.cancel();
    ServiceManager.instance().mic.stop();
  }
  
  Future<void> _processRecording() async {
    if (_audioChunks.isEmpty) {
      widget.onClose();
      return;
    }
    
    setState(() {
      _state = RecordingState.transcribing;
      _isProcessing = true;
    });
    
    try {
      await _stopRecording();
      
      // Flatten audio chunks into a single list
      List<int> flattenedBytes = [];
      for (var chunk in _audioChunks) {
        flattenedBytes.addAll(chunk);
      }
      
      // Convert PCM to WAV file
      final audioFile = await FileUtils.convertPcmToWavFile(
        Uint8List.fromList(flattenedBytes),
        16000, // Sample rate
        1,     // Mono channel
      );
      
      // Send to API for transcription
      final transcript = await transcribeVoiceMessage(audioFile);
      
      if (mounted) {
        setState(() {
          _transcript = transcript;
          _state = RecordingState.transcribeSuccess;
          _isProcessing = false;
        });
        
        // If we have a transcript, send it to the parent widget
        if (transcript.isNotEmpty) {
          widget.onTranscriptReady(transcript);
        }
      }
    } catch (e) {
      debugPrint('Error processing recording: $e');
      if (mounted) {
        setState(() {
          _state = RecordingState.transcribeFailed;
          _isProcessing = false;
        });
      }
      AppSnackbar.showSnackbarError('Failed to transcribe audio');
    }
  }
  
  void _retry() {
    if (_audioChunks.isEmpty) {
      // If no audio chunks are available, start a new recording
      _startRecording();
    } else {
      // Retry transcription with existing audio data
      _processRecording();
    }
  }
  
  @override
  Widget build(BuildContext context) {
    switch (_state) {
      case RecordingState.recording:
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              const Icon(Icons.mic, color: Colors.red),
              const SizedBox(width: 8),
              Expanded(
                child: SizedBox(
                  height: 40,
                  child: CustomPaint(
                    painter: AudioWavePainter(levels: _audioLevels),
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.check_circle, color: Colors.white),
                onPressed: _processRecording,
              ),
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: widget.onClose,
              ),
            ],
          ),
        );
        
      case RecordingState.transcribing:
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(16),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  strokeWidth: 2,
                ),
              ),
              SizedBox(width: 16),
              Text(
                'Transcribing...',
                style: TextStyle(color: Colors.white),
              ),
            ],
          ),
        );
        
      case RecordingState.transcribeSuccess:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(
                _transcript,
                style: const TextStyle(color: Colors.white),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: widget.onClose,
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: Colors.white),
                  onPressed: () => widget.onTranscriptReady(_transcript),
                ),
              ],
            ),
          ],
        );
        
      case RecordingState.transcribeFailed:
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Transcription failed',
                style: TextStyle(color: Colors.white),
              ),
              Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.refresh, color: Colors.white),
                    onPressed: _retry,
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: widget.onClose,
                  ),
                ],
              ),
            ],
          ),
        );
        
      default:
        return const SizedBox.shrink();
    }
  }
}

class AudioWavePainter extends CustomPainter {
  final List<double> levels;
  
  AudioWavePainter({required this.levels});
  
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    
    final width = size.width;
    final height = size.height;
    final barWidth = width / levels.length / 2;
    
    for (int i = 0; i < levels.length; i++) {
      final x = i * (barWidth * 2) + barWidth;
      final barHeight = levels[i] * height * 0.8;
      final y = height / 2 - barHeight / 2;
      
      canvas.drawLine(
        Offset(x, y),
        Offset(x, y + barHeight),
        paint,
      );
    }
  }
  
  @override
  bool shouldRepaint(covariant AudioWavePainter oldDelegate) {
    return true; // Always repaint to show animation
  }
}
