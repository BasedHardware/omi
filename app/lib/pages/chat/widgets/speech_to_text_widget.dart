import 'dart:async';
import 'dart:collection' show Queue;
import 'dart:math' show Random;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/utils/enums.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

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

class SpeechToTextWidgetState extends State<SpeechToTextWidget> with SingleTickerProviderStateMixin {
  // Recording state
  bool _isRecording = false;
  String _recognizedText = '';
  int _recordingDuration = 0;
  bool _hasReconnected = false;

  // Animation state
  double _currentSoundLevel = 0;
  final Random _random = Random();
  
  // Timers
  Timer? _recordingTimer;
  Timer? _waveTimer;
  Timer? _reconnectionTimer;

  // Parent notification
  bool get isRecording => _isRecording;

  @override
  void dispose() {
    _cleanupTimers();
    if (_isRecording) {
      _forceShowNavigationBar();
      _stopRecording();
    }
    super.dispose();
  }

  void _cleanupTimers() {
    _recordingTimer?.cancel();
    _waveTimer?.cancel();
    _reconnectionTimer?.cancel();
    
    _recordingTimer = null;
    _waveTimer = null;
    _reconnectionTimer = null;
  }

  String _formatDuration(int seconds) {
    final minutes = seconds ~/ 60;
    final remainingSeconds = seconds % 60;
    return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
  }

  Future<void> _startRecording() async {
    final captureProvider = context.read<CaptureProvider>();
    
    // Clear previous transcripts
    captureProvider.clearTranscripts();
    
    // Initialize recording state
    setState(() {
      _isRecording = true;
      _recognizedText = '';
      _recordingDuration = 0;
      _currentSoundLevel = 0;
    });
    
    // Ensure keyboard and text input are hidden 
    // by unfocusing and hiding the keyboard
    final homeProvider = context.read<HomeProvider>();
    homeProvider.chatFieldFocusNode.unfocus();
    await SystemChannels.textInput.invokeMethod('TextInput.hide');
    
    // Start the recording timer for duration tracking
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        setState(() => _recordingDuration++);
      }
    });
    
    // Start animation timer
    _waveTimer = Timer.periodic(const Duration(milliseconds: 60), (timer) {
      if (!mounted || !_isRecording) return;
      
      final isActive = captureProvider.recordingState == RecordingState.record;
      if (isActive && mounted) {
        setState(() {
          _currentSoundLevel = (5 + _random.nextDouble() * 15).clamp(2.0, 40.0);
        });
      }
    });
    
    // Initialize and start backend recording
    captureProvider.updateRecordingState(RecordingState.initialising);
    await captureProvider.streamRecording();
    
    // Show reconnection indicator briefly to indicate we've started
    if (mounted) {
      setState(() => _hasReconnected = true);
      _reconnectionTimer = Timer(const Duration(seconds: 3), () {
        if (mounted) setState(() => _hasReconnected = false);
      });
    }
  }

  Future<void> _stopRecording() async {
    final captureProvider = context.read<CaptureProvider>();
    await captureProvider.stopStreamRecording();
    captureProvider.clearTranscripts();
  }

  Future<void> toggleVoiceRecording() async {
    if (!_isRecording) {
      // Starting a new recording
      if (MediaQuery.of(context).viewInsets.bottom > 0) {
        FocusScope.of(context).unfocus();
        await Future.delayed(const Duration(milliseconds: 100));
      }
      
      await _startRecording();
    } else {
      // Stopping current recording
      _cleanupTimers();
      
      // Stop streaming recording
      await _stopRecording();
      
      _forceShowNavigationBar();
      
      final String finalText = _recognizedText;
      
      setState(() {
        _isRecording = false;
        _recordingDuration = 0;
        _currentSoundLevel = 0;
        _recognizedText = '';
      });
      
      // Handle recognized text
      if (finalText.isNotEmpty) {
        widget.onTextRecognized(finalText);
      } else if (_recordingDuration >= 1) {
        // Only show this message if they actually tried to record
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('No speech detected. Please try again.'),
                duration: const Duration(seconds: 2),
                backgroundColor: Colors.orange.shade700,
              ),
            );
          }
        });
      }
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
      if (mounted) setState(() {});
    });
  }

  Widget _buildRecordingOverlay() {
    return Consumer<CaptureProvider>(
      builder: (context, captureProvider, child) {
        final bool isActive = captureProvider.recordingState == RecordingState.record;
        
        // Update recognized text if available
        if (captureProvider.hasTranscripts && isActive) {
          _recognizedText = captureProvider.segments.isNotEmpty 
              ? captureProvider.segments.last.text 
              : '';
        }
        
        final theme = Theme.of(context);
        
        // Define gradient colors based on state
        List<Color> gradientColors;
        if (_hasReconnected) {
          gradientColors = [Colors.orangeAccent.withOpacity(0.7), Colors.orange.withOpacity(0.3)];
        } else if (isActive) {
          gradientColors = [Colors.greenAccent.withOpacity(0.5), Colors.green.withOpacity(0.2)];
        } else {
          gradientColors = [Colors.grey.shade600.withOpacity(0.5), Colors.grey.shade800.withOpacity(0.2)];
        }
        
        return Material(
          color: Colors.transparent,
          elevation: 100,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: gradientColors,
              ),
              borderRadius: BorderRadius.circular(14.0),
            ),
            padding: const EdgeInsets.all(1.5), // Border width
            child: Container(
              width: double.infinity,
              height: 120,
              decoration: BoxDecoration(
                color: Colors.grey.shade900,
                borderRadius: BorderRadius.circular(12.0),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(left: 8.0),
                        child: IconButton(
                          icon: const Icon(Icons.close, color: Colors.white, size: 20),
                          onPressed: toggleVoiceRecording,
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.grey.shade800.withOpacity(0.4),
                            padding: const EdgeInsets.all(8),
                          ),
                        ),
                      ),
                      Row(
                        children: [
                          Text(
                            _formatDuration(_recordingDuration),
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w500,
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
                      Padding(
                        padding: const EdgeInsets.only(right: 8.0),
                        child: IconButton(
                          icon: const Icon(Icons.check, color: Colors.white, size: 20),
                          onPressed: toggleVoiceRecording,
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.grey.shade800.withOpacity(0.4),
                            padding: const EdgeInsets.all(8),
                          ),
                        ),
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
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: _hasReconnected ? Colors.orangeAccent : Colors.greenAccent, 
                            fontStyle: FontStyle.italic,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        )
                      : isActive ? 
                          Text(
                            "Speak now...",
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: Colors.grey.shade400,
                              fontStyle: FontStyle.italic,
                            ),
                            maxLines: 1,
                          )
                        : Shimmer.fromColors(
                            baseColor: Colors.white70,
                            highlightColor: Colors.grey.shade700,
                            child: Text(
                              "Initializing...",
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: Colors.orange.shade300,
                                fontStyle: FontStyle.italic,
                              ),
                              maxLines: 1,
                            ),
                          ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    height: 40,
                    margin: const EdgeInsets.symmetric(horizontal: 20),
                    child: RepaintBoundary(
                      child: CustomPaint(
                        painter: WaveformPainter(
                          soundLevel: isActive ? _currentSoundLevel : 0,
                          activeColor: Colors.white,
                        ),
                        size: Size.infinite,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      }
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_isRecording) return const SizedBox.shrink();
    
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
}

class WaveformPainter extends CustomPainter {
  final double soundLevel;
  final Color activeColor;
  static final Queue<double> waveHistory = Queue<double>();
  static const int maxPoints = 50;
  static final _random = Random();
  static bool _initialized = false;

  WaveformPainter({
    this.soundLevel = 0,
    this.activeColor = Colors.white,
  }) {
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
      ..color = activeColor
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final centerY = height / 2;
    
    // Draw waveform bars
    final barWidth = (width / maxPoints).floor();
    int i = 0;
    
    for (final level in waveHistory) {
      final x = i * barWidth.toDouble();
      
      // Add subtle randomness for natural movement
      final jitter = _random.nextDouble() * 1.5;
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
    oldDelegate.soundLevel != soundLevel || oldDelegate.activeColor != activeColor;
} 