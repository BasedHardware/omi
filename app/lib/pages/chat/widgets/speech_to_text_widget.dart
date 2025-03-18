import 'dart:async';
import 'dart:collection' show Queue;
import 'dart:math' show Random;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:provider/provider.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

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
  final stt.SpeechToText _speech = stt.SpeechToText();
  bool _isListening = false;
  bool _isRecording = false;
  String _recognizedText = '';
  Timer? _recordingTimer;
  int _recordingDuration = 0;
  double _currentSoundLevel = 0;
  bool _hasReconnected = false;
  Timer? _reconnectionTimer;

  bool get isRecording => _isRecording;

  @override
  void initState() {
    super.initState();
    // Just do a basic initialization, callback handlers are set in toggleVoiceRecording
    _speech.initialize().then((available) {
      if (!available && mounted) {
        debugPrint('Speech recognition not available during initial setup');
      }
    });
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _reconnectionTimer?.cancel();
    _speech.cancel();
    if (_isRecording || _isListening) {
      _forceShowNavigationBar();
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
    
    final bool isActive = _speech.isListening;
    
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
                    isActive ? "Speak now..." : "Reconnecting...",
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

  Future<void> toggleVoiceRecording() async {
    if (!_isListening) {
      // Only initialize if not already initialized or if we need to reinitialize
      if (!_speech.isAvailable) {
        bool available = await _speech.initialize(
          onError: (error) {
            debugPrint('Speech recognition error: $error');
            // Show error if it's a critical error
            if (error.errorMsg.contains('unavailable') || error.errorMsg.contains('permission')) {
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('Speech recognition error: ${error.errorMsg}'),
                    backgroundColor: Colors.red,
                    duration: const Duration(seconds: 3),
                  ),
                );
              }
            }
          },
          onStatus: (status) {
            debugPrint('Speech recognition status: $status');
            
            if (status == 'done' || status == 'notListening') {
              if (_isListening && mounted) {
                // If we're supposed to be listening but we got a status indicating we're not,
                // try to restart listening
                if (_isRecording && _recordingDuration < 300) {  // Don't auto-restart after 5 minutes
                  debugPrint('Attempting to restart speech recognition...');
                  _restartListening();
                } else {
                  setState(() {
                    _isListening = false;
                    _isRecording = false;
                    if (_recognizedText.isNotEmpty) {
                      widget.onTextRecognized(_recognizedText);
                    }
                  });
                  _forceShowNavigationBar();
                }
              }
            }
          },
        );
        
        if (!available) {
          debugPrint('Speech recognition not available');
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Speech recognition is not available on this device.'),
                backgroundColor: Colors.red,
              ),
            );
          }
          return;
        }
      }

      if (MediaQuery.of(context).viewInsets.bottom > 0) {
        FocusScope.of(context).unfocus();
        await Future.delayed(const Duration(milliseconds: 100));
      }
      
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _isListening = true;
            _isRecording = true;
            // Only reset recognizedText if we're starting a brand new recording
            // not if we're reconnecting
            _recognizedText = '';
            _recordingDuration = 0;
            _currentSoundLevel = 0;
          });
          // Don't request focus to prevent keyboard from appearing
          SystemChannels.textInput.invokeMethod('TextInput.hide');
        }
      });
      
      _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
        if (mounted) {
          setState(() {
            _recordingDuration++;
          });
          
          // Check if we're actually listening and try to restart if needed
          if (_isRecording && !_speech.isListening && _recordingDuration > 1) {
            debugPrint('Timer detected speech stopped listening, attempting to restart...');
            _restartListening();
          }
        }
      });
      
      try {
        // Clear any previous session
        await _speech.cancel();
        
        await _speech.listen(
          onResult: (result) {
            if (mounted) {
              setState(() {
                // For new recordings, we can just set the text directly
                // since we reset _recognizedText earlier
                _recognizedText = result.recognizedWords;
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
          cancelOnError: false,
        );
      } catch (e) {
        debugPrint('Error starting speech recognition: $e');
        _forceShowNavigationBar();
        setState(() {
          _isListening = false;
          _isRecording = false;
        });
      }
    } else {
      try {
        await _speech.stop();
      } catch (e) {
        debugPrint('Error stopping speech recognition: $e');
        // Even if there's an error, continue with cleanup
      } finally {
        _recordingTimer?.cancel();
        _forceShowNavigationBar();
        
        setState(() {
          _isListening = false;
          _isRecording = false;
          _recordingDuration = 0;
          _currentSoundLevel = 0;
          
          if (_recognizedText.isNotEmpty) {
            widget.onTextRecognized(_recognizedText);
          } else if (_recordingDuration >= 1) {
            // Only show this message if they actually tried to record (over 1 second)
            // This check prevents showing the message when they just tap and immediately cancel
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
      }
    }
  }
  
  // Helper method to restart listening if it stops unexpectedly
  Future<void> _restartListening() async {
    if (!mounted || !_isRecording) return;
    
    try {
      debugPrint('Auto-restarting speech recognition...');
      
      // Save the current recognized text before restarting
      final String currentText = _recognizedText;
      
      // Show reconnection indicator
      setState(() {
        _hasReconnected = true;
      });
      
      // Clear any previous reconnection timer
      _reconnectionTimer?.cancel();
      
      // Start a timer to clear the reconnection indicator after 3 seconds
      _reconnectionTimer = Timer(const Duration(seconds: 3), () {
        if (mounted) {
          setState(() {
            _hasReconnected = false;
          });
        }
      });
      
      await _speech.cancel();
      await Future.delayed(const Duration(milliseconds: 300));
      
      if (mounted && _isRecording) {
        await _speech.listen(
          onResult: (result) {
            if (mounted) {
              setState(() {
                // Append new text if there's anything new
                if (result.recognizedWords.isNotEmpty) {
                  // Only append if the new text is different and not already a subset of current text
                  if (!currentText.contains(result.recognizedWords) &&
                      result.recognizedWords != currentText) {
                    
                    // If new text is completely different, determine whether to append or replace
                    if (result.recognizedWords.length < 5 || 
                        !_recognizedText.endsWith(result.recognizedWords.substring(0, 5))) {
                      // Add a space if we're appending and there's existing text
                      _recognizedText = currentText.isEmpty 
                          ? result.recognizedWords 
                          : "$currentText ${result.recognizedWords}";
                    } else {
                      // New text has overlap with existing text, just use the new text
                      _recognizedText = result.recognizedWords;
                    }
                  } else if (result.recognizedWords.length > currentText.length) {
                    // The new text is more complete than the old text, use it
                    _recognizedText = result.recognizedWords;
                  }
                }
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
          cancelOnError: false,
        );
      }
    } catch (e) {
      debugPrint('Error restarting speech recognition: $e');
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