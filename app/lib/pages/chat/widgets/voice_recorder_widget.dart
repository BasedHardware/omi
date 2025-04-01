import 'dart:async';
import 'dart:math' as Math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/file.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shimmer/shimmer.dart';

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

    // Setup timer to update the wave visualization every second
    _waveformTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_state == RecordingState.recording && mounted) {
        setState(() {
          // Just trigger a repaint
        });
      }
    });

    _startRecording();
  }

  @override
  void dispose() {
    _animationController.dispose();
    _waveformTimer?.cancel();

    // Make sure to stop recording when widget is disposed
    if (_state == RecordingState.recording) {
      // Use a synchronous call to stop recording to avoid any async issues
      ServiceManager.instance().mic.stop();
    }

    super.dispose();
  }

  Future<void> _startRecording() async {
    await Permission.microphone.request();

    await ServiceManager.instance().mic.start(onByteReceived: (bytes) {
      if (_state == RecordingState.recording && mounted) {
        // Check if widget is still mounted before calling setState
        if (mounted) {
          setState(() {
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
                rms = Math.sqrt(rms / sampleCount) / 32768.0;
              } else {
                rms = 0;
              }

              // Apply non-linear scaling to make quiet sounds more visible
              // and loud sounds more dramatic
              final level = Math.pow(rms, 0.4).toDouble().clamp(0.1, 1.0);

              // Shift all values left
              for (int i = 0; i < _audioLevels.length - 1; i++) {
                _audioLevels[i] = _audioLevels[i + 1];
              }

              // Add new level at the end
              _audioLevels[_audioLevels.length - 1] = level;

              // We don't force setState here anymore - the timer will handle updates
            }
          });
        }
      }
    }, onRecording: () {
      debugPrint('Recording started');
      setState(() {
        _state = RecordingState.recording;
        _audioChunks = [];
        // Reset audio levels
        for (int i = 0; i < _audioLevels.length; i++) {
          _audioLevels[i] = 0.1;
        }
      });
    }, onStop: () {
      debugPrint('Recording stopped');
    }, onInitializing: () {
      debugPrint('Initializing');
    });
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
      1, // Mono channel
    );

    try {
      final transcript = await transcribeVoiceMessage(audioFile);
      if (mounted) {
        setState(() {
          _transcript = transcript;
          _state = RecordingState.transcribeSuccess;
          _isProcessing = false;
        });
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
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: widget.onClose,
              ),
              Expanded(
                child: SizedBox(
                  height: 40,
                  child: CustomPaint(
                    painter: AudioWavePainter(
                      levels: _audioLevels,
                      timestamp: DateTime.now(),
                    ),
                  ),
                ),
              ),
              GestureDetector(
                onTap: _processRecording,
                child: Container(
                  padding: const EdgeInsets.all(4),
                  margin: const EdgeInsets.only(top: 10, bottom: 10, right: 6, left: 16),
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.check,
                    color: Colors.black,
                    size: 20.0,
                  ),
                ),
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
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Shimmer.fromColors(
                baseColor: Colors.grey.shade800,
                highlightColor: Colors.white,
                child: const Text(
                  'Transcribing...',
                  style: TextStyle(
                    color: Colors.white,
                  ),
                ),
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
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 0),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Error',
                style: TextStyle(color: Colors.redAccent, fontSize: 14, fontWeight: FontWeight.w700),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: SizedBox(
                  height: 40,
                  child: CustomPaint(
                    painter: AudioWavePainter(
                      levels: _audioLevels,
                      timestamp: DateTime.now(),
                    ),
                  ),
                ),
              ),
              Row(
                children: [
                  GestureDetector(
                      onTap: _retry,
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        margin: const EdgeInsets.only(left: 10, right: 0, top: 10, bottom: 10),
                        decoration: const BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          color: Colors.black,
                          Icons.refresh,
                          size: 20.0,
                        ),
                      )),
                  GestureDetector(
                    onTap: widget.onClose,
                    child: Container(
                      padding: const EdgeInsets.only(left: 14, right: 0, top: 14, bottom: 14),
                      child: const Icon(
                        Icons.close,
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
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
  // Add timestamp to control repaint frequency
  final DateTime timestamp;

  AudioWavePainter({
    required this.levels,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white
      ..strokeWidth = 4 // Slightly thicker for better visibility
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final barWidth = width / levels.length / 2;

    for (int i = 0; i < levels.length; i++) {
      final x = i * (barWidth * 2) + barWidth;

      // Use the level directly for more accurate RMS representation
      final level = levels[i];
      final barHeight = level * height * 0.8;

      final topY = height / 2 - barHeight / 2;
      final bottomY = height / 2 + barHeight / 2;

      // Draw only the individual bars with rounded caps
      canvas.drawLine(
        Offset(x, topY),
        Offset(x, bottomY),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant AudioWavePainter oldDelegate) {
    return true;
  }
}
