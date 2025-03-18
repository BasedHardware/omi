import 'dart:async';
import 'dart:collection' show Queue;
import 'dart:math' show Random;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:provider/provider.dart';

typedef OnTextRecognized = void Function(String text);

class SpeechToTextWidget extends StatefulWidget {
  final OnTextRecognized onTextRecognized;
  final double bottomPadding;
  final bool isPivotBottom;

  const SpeechToTextWidget({
    Key? key,
    required this.onTextRecognized,
    required this.bottomPadding,
    this.isPivotBottom = false,
  }) : super(key: key);

  @override
  State<SpeechToTextWidget> createState() => SpeechToTextWidgetState();
}

class SpeechToTextWidgetState extends State<SpeechToTextWidget> {
  bool _isRecording = false;
  String _recognizedText = '';
  Timer? _recordingTimer;
  int _recordingDuration = 0;
  double _currentSoundLevel = 0;
  bool _hasReconnected = false;
  Timer? _reconnectionTimer;

  bool get isRecording => _isRecording;

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _reconnectionTimer?.cancel();
    if (_isRecording) {
      _forceShowNavigationBar();
      final captureProvider = context.read<CaptureProvider>();
      captureProvider.stopStreamRecording();
    }
    super.dispose();
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  Widget _buildRecordingOverlay() {
    if (!_isRecording) return const SizedBox.shrink();
    
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, child) {
        final bool isActive = captureProvider.recordingState == RecordingState.record;
        
        // Update recognized text if available
        if (captureProvider.hasTranscripts && isActive) {
          _recognizedText = captureProvider.segments.isNotEmpty 
              ? captureProvider.segments.last.text 
              : '';
        }
        
        return Material(
          color: Colors.transparent,
          elevation: 100, // High elevation to ensure it appears above other elements
          child: Container(
            width: double.infinity,
            height: 120,
            decoration: BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: _hasReconnected 
                    ? Colors.orangeAccent.withOpacity(0.5) 
                    : (isActive ? Colors.greenAccent.withOpacity(0.3) : Colors.grey.withOpacity(0.3))
              ),
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white),
                      onPressed: () {
                        toggleVoiceRecording();
                      },
                    ),
                    Row(
                      children: [
                        Text(
                          _formatDuration(_recordingDuration),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                          ),
                        ),
                        const SizedBox(width: 8),
                        // Status indicator
                        Icon(
                          _hasReconnected ? Icons.refresh : Icons.mic, 
                          color: _hasReconnected
                              ? Colors.orangeAccent
                              : (isActive 
                                  ? (_recognizedText.isNotEmpty ? Colors.greenAccent : Colors.orange)
                                  : Colors.grey),
                          size: 16
                        ),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.check, color: Colors.white),
                      onPressed: () {
                        toggleVoiceRecording();
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                // Add status text
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: _recognizedText.isNotEmpty
                    ? Text(
                        _recognizedText.length > 30
                            ? '${_recognizedText.substring(0, 30)}...'
                            : _recognizedText,
                        style: TextStyle(
                          color: _hasReconnected ? Colors.orangeAccent : Colors.greenAccent, 
                          fontSize: 12,
                          fontStyle: FontStyle.italic,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      )
                    : Text(
                        isActive ? "Speak now..." : "Initializing...",
                        style: TextStyle(
                          color: isActive ? Colors.grey : Colors.orange, 
                          fontSize: 12,
                          fontStyle: FontStyle.italic,
                        ),
                        maxLines: 1,
                      ),
                ),
                const SizedBox(height: 6),
                Container(
                  height: 40,
                  margin: const EdgeInsets.symmetric(horizontal: 20),
                  child: CustomPaint(
                    painter: WaveformPainter(soundLevel: isActive ? _currentSoundLevel : 0),
                    size: Size.infinite,
                  ),
                ),
              ],
            ),
          ),
        );
      }
    );
  }

  Future<void> toggleVoiceRecording() async {
    final captureProvider = context.read<CaptureProvider>();
    
    if (!_isRecording) {
      if (MediaQuery.of(context).viewInsets.bottom > 0) {
        FocusScope.of(context).unfocus();
        await Future.delayed(const Duration(milliseconds: 100));
      }
      
      // Clear previous transcripts before starting new recording
      captureProvider.clearTranscripts();
      
      setState(() {
        _isRecording = true;
        _recognizedText = '';
        _recordingDuration = 0;
        _currentSoundLevel = 0;
      });
      
      // Don't request focus to prevent keyboard from appearing
      SystemChannels.textInput.invokeMethod('TextInput.hide');
      
      // Start the recording timer
      _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
        if (mounted) {
          setState(() {
            _recordingDuration++;
          });
          
          // Simulate sound level for waveform animation
          if (captureProvider.recordingState == RecordingState.record) {
            setState(() {
              _currentSoundLevel = (5 + Random().nextDouble() * 15).clamp(2.0, 40.0);
            });
          }
        }
      });
      
      // Initialize recording
      captureProvider.updateRecordingState(RecordingState.initialising);
      
      // Start streaming recording
      await captureProvider.streamRecording();
      
      // Set reconnected indicator to indicate we've started
      setState(() {
        _hasReconnected = true;
      });
      
      // Clear reconnection indicator after 3 seconds
      _reconnectionTimer = Timer(const Duration(seconds: 3), () {
        if (mounted) {
          setState(() {
            _hasReconnected = false;
          });
        }
      });
      
    } else {
      _recordingTimer?.cancel();
      _reconnectionTimer?.cancel();
      
      // Stop streaming recording
      await captureProvider.stopStreamRecording();
      
      _forceShowNavigationBar();
      
      final String finalText = _recognizedText;
      
      setState(() {
        _isRecording = false;
        _recordingDuration = 0;
        _currentSoundLevel = 0;
        _recognizedText = '';  // Clear recognized text
        
        if (finalText.isNotEmpty) {
          widget.onTextRecognized(finalText);
        } else if (_recordingDuration >= 1) {
          // Only show this message if they actually tried to record (over 1 second)
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('No speech detected. Please try again.'),
                  duration: Duration(seconds: 2),
                  backgroundColor: Colors.orange,
                ),
              );
            }
          });
        }
      });
      
      // Clear transcript data after handling the recognized text
      captureProvider.clearTranscripts();
    }
  }

  //Helper function for showing navBar
  void _forceShowNavigationBar() {
    // Use HomeProvider to properly manage focus
    if (mounted) {
      final homeProvider = context.read<HomeProvider>();
      homeProvider.chatFieldFocusNode.unfocus();
    }
    
    FocusScope.of(context).unfocus();
    Future.delayed(const Duration(milliseconds: 100), () {
      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isRecording) {
      return Positioned(
        bottom: 0,
        left: 0,
        right: 0,
        child: Padding(
          padding: EdgeInsets.only(
            left: 28, 
            right: 28, 
            bottom: widget.isPivotBottom ? 40 : widget.bottomPadding
          ),
          child: _buildRecordingOverlay(),
        ),
      );
    }
    return const SizedBox.shrink();
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
  bool shouldRepaint(covariant WaveformPainter oldDelegate) => 
    oldDelegate.soundLevel != soundLevel;
} 