import 'dart:async';
import 'dart:collection' show Queue;
import 'dart:math' show Random;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class VoiceRecorder extends StatefulWidget {
  final Function(String) onTextRecognized;
  final Function() onRecordingStarted;
  final Function() onRecordingStopped;
  final bool isRecording;

  const VoiceRecorder({
    Key? key,
    required this.onTextRecognized,
    required this.onRecordingStarted,
    required this.onRecordingStopped,
    required this.isRecording,
  }) : super(key: key);

  @override
  State<VoiceRecorder> createState() => _VoiceRecorderState();
}

class _VoiceRecorderState extends State<VoiceRecorder> {
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _isListening = false;
  String _recognizedText = '';
  Timer? _recordingTimer;
  int _recordingDuration = 0;
  double _currentSoundLevel = 0;
  bool _speechInitialized = false;

  @override
  void initState() {
    super.initState();
    // Initialize speech recognition and start recording when ready
    _initSpeechAndStartRecording();
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _speech.cancel();
    super.dispose();
  }

  Future<void> _initSpeechAndStartRecording() async {
    bool available = await _speech.initialize(
      onError: (error) => debugPrint('Speech recognition error: $error'),
      onStatus: (status) {
        debugPrint('Speech status: $status');
        if (status == 'done' || status == 'notListening') {
          if (mounted) {
            setState(() {
              _isListening = false;
              if (_recognizedText.isNotEmpty) {
                widget.onTextRecognized(_recognizedText);
              }
            });
          }
          widget.onRecordingStopped();
        }
      },
    );

    if (available) {
      _speechInitialized = true;
      // Give a small delay to ensure initialization is complete
      await Future.delayed(const Duration(milliseconds: 200));
      if (mounted) {
        startRecording();
      }
    } else {
      debugPrint('Speech recognition not available');
    }
  }

  Future<void> startRecording() async {
    if (_isListening) return;
    
    // Ensure speech is initialized
    if (!_speechInitialized) {
      bool available = await _speech.initialize();
      if (!available) {
        debugPrint('Could not initialize speech recognition');
        return;
      }
      _speechInitialized = true;
    }
    
    // Hide keyboard if visible
    if (MediaQuery.of(context).viewInsets.bottom > 0) {
      FocusScope.of(context).unfocus();
      await Future.delayed(const Duration(milliseconds: 100));
    }
    
    // Prevent keyboard from appearing
    SystemChannels.textInput.invokeMethod('TextInput.hide');
    
    // Start the timer
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() {
          _recordingDuration++;
        });
      }
    });
    
    // Set up recording state
    setState(() {
      _isListening = true;
      _recognizedText = '';
      _recordingDuration = 0;
      _currentSoundLevel = 0;
    });
    
    try {
      // Notify parent that recording started
      widget.onRecordingStarted();

      // Start the actual speech recognition
      await _speech.listen(
        onResult: (result) {
          if (mounted) {
            setState(() {
              _recognizedText = result.recognizedWords;
              debugPrint('Recognized: ${result.recognizedWords}');
            });
          }
        },
        onSoundLevelChange: (level) {
          if (mounted) {
            setState(() {
              _currentSoundLevel = level * 2;
            });
          }
        },
        listenFor: const Duration(minutes: 5),
        partialResults: true,
        listenMode: stt.ListenMode.deviceDefault,
        cancelOnError: true,
      );
    } catch (e) {
      debugPrint('Error starting speech recognition: $e');
      _cleanup();
    }
  }

  Future<void> stopRecording() async {
    try {
      if (_isListening) {
        await _speech.stop();
      }
    } catch (e) {
      debugPrint('Error stopping speech recognition: $e');
    } finally {
      _cleanup();
    }
  }
  
  void _cleanup() {
    _recordingTimer?.cancel();
    
    if (mounted) {
      setState(() {
        _isListening = false;
        if (_recognizedText.isNotEmpty) {
          widget.onTextRecognized(_recognizedText);
        }
      });
    }
    
    widget.onRecordingStopped();
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isRecording) return const SizedBox.shrink();
    
    return Material(
      color: Colors.transparent,
      elevation: 100, // High elevation to ensure it appears above other elements
      child: Container(
        width: double.infinity,
        height: 120,
        decoration: BoxDecoration(
          color: Colors.black,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.grey.withOpacity(0.3)),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: stopRecording,
                ),
                Text(
                  _formatDuration(_recordingDuration),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.check, color: Colors.white),
                  onPressed: stopRecording,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Container(
              height: 40,
              margin: const EdgeInsets.symmetric(horizontal: 20),
              child: CustomPaint(
                painter: WaveformPainter(soundLevel: _currentSoundLevel),
                size: Size.infinite,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class WaveformPainter extends CustomPainter {
  final double soundLevel;
  static final Queue<double> waveHistory = Queue<double>();
  static const int maxPoints = 50;
  static final _random = Random();
  static bool _initialized = false;

  WaveformPainter({this.soundLevel = 0}) {
    if (!_initialized) {
      for (int i = 0; i < maxPoints; i++) {
        waveHistory.add(2.0);
      }
      _initialized = true;
    }
    
    if (soundLevel > 0) {
      waveHistory.removeFirst();
      waveHistory.addLast(soundLevel.clamp(2.0, 40.0));
    } else {
      // Add some animation even when there's no sound
      waveHistory.removeFirst();
      waveHistory.addLast(2.0 + _random.nextDouble() * 3.0);
    }
  }

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final centerY = height / 2;
    
    // Draw waveform bars
    final barWidth = (width / maxPoints).floor();
    int i = 0;
    
    for (final level in waveHistory) {
      final x = i * barWidth.toDouble();
      
      // Add some randomness for natural movement
      final jitter = _random.nextDouble() * 2.0;
      final amplitude = (level + jitter).clamp(2.0, height / 2);
      
      canvas.drawLine(
        Offset(x, centerY - amplitude),
        Offset(x, centerY + amplitude),
        paint,
      );
      
      i++;
    }
  }

  @override
  bool shouldRepaint(covariant WaveformPainter oldDelegate) => true; // Always repaint to ensure animation
} 