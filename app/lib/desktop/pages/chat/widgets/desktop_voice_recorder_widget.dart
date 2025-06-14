import 'dart:async';
import 'dart:math' as Math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/file.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shimmer/shimmer.dart';

enum RecordingState {
  notRecording,
  recording,
  transcribing,
  transcribeSuccess,
  transcribeFailed,
}

class DesktopVoiceRecorderWidget extends StatefulWidget {
  final Function(String) onTranscriptReady;
  final VoidCallback onClose;

  const DesktopVoiceRecorderWidget({
    super.key,
    required this.onTranscriptReady,
    required this.onClose,
  });

  @override
  State<DesktopVoiceRecorderWidget> createState() => _DesktopVoiceRecorderWidgetState();
}

class _DesktopVoiceRecorderWidgetState extends State<DesktopVoiceRecorderWidget> with SingleTickerProviderStateMixin {
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
      ServiceManager.instance().mic.stop();
    }

    super.dispose();
  }

  Future<void> _startRecording() async {
    await Permission.microphone.request();

    await ServiceManager.instance().mic.start(onByteReceived: (bytes) {
      if (_state == RecordingState.recording && mounted) {
        if (mounted) {
          setState(() {
            _audioChunks.add(bytes.toList());

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
                rms = Math.sqrt(rms / sampleCount) / 32768.0;
              } else {
                rms = 0;
              }

              final level = Math.pow(rms, 0.4).toDouble().clamp(0.1, 1.0);

              for (int i = 0; i < _audioLevels.length - 1; i++) {
                _audioLevels[i] = _audioLevels[i + 1];
              }

              _audioLevels[_audioLevels.length - 1] = level;
            }
          });
        }
      }
    }, onRecording: () {
      debugPrint('Recording started');
      setState(() {
        _state = RecordingState.recording;
        _audioChunks = [];
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
      _processRecording();
    }
  }

  @override
  Widget build(BuildContext context) {
    switch (_state) {
      case RecordingState.recording:
        return Container(
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              IconButton(
                icon: Icon(Icons.close, color: ResponsiveHelper.textSecondary),
                onPressed: widget.onClose,
              ),
              Expanded(
                child: SizedBox(
                  height: 40,
                  child: CustomPaint(
                    painter: DesktopAudioWavePainter(
                      levels: _audioLevels,
                      timestamp: DateTime.now(),
                    ),
                  ),
                ),
              ),
              GestureDetector(
                onTap: _processRecording,
                child: Container(
                  padding: const EdgeInsets.all(8),
                  margin: const EdgeInsets.only(top: 8, bottom: 8, right: 8, left: 12),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(
                    Icons.check,
                    color: Colors.white,
                    size: 16,
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
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Shimmer.fromColors(
                baseColor: ResponsiveHelper.textTertiary,
                highlightColor: ResponsiveHelper.textPrimary,
                child: Text(
                  'Transcribing...',
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
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
                color: ResponsiveHelper.backgroundTertiary,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                  width: 1,
                ),
              ),
              child: Text(
                _transcript,
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                IconButton(
                  icon: Icon(Icons.close, color: ResponsiveHelper.textSecondary),
                  onPressed: widget.onClose,
                ),
                IconButton(
                  icon: Icon(Icons.send, color: ResponsiveHelper.purplePrimary),
                  onPressed: () => widget.onTranscriptReady(_transcript),
                ),
              ],
            ),
          ],
        );

      case RecordingState.transcribeFailed:
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: Colors.red.withOpacity(0.3),
              width: 1,
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Error',
                style: TextStyle(
                  color: Colors.redAccent,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: SizedBox(
                  height: 40,
                  child: CustomPaint(
                    painter: DesktopAudioWavePainter(
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
                      padding: const EdgeInsets.all(6),
                      margin: const EdgeInsets.only(left: 8, right: 4),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.purplePrimary,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Icon(
                        Icons.refresh,
                        color: Colors.white,
                        size: 16,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close, color: ResponsiveHelper.textSecondary),
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

class DesktopAudioWavePainter extends CustomPainter {
  final List<double> levels;
  final DateTime timestamp;

  DesktopAudioWavePainter({
    required this.levels,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = ResponsiveHelper.purplePrimary
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final barWidth = width / levels.length / 2;

    for (int i = 0; i < levels.length; i++) {
      final x = i * (barWidth * 2) + barWidth;

      final level = levels[i];
      final barHeight = level * height * 0.8;

      final topY = height / 2 - barHeight / 2;
      final bottomY = height / 2 + barHeight / 2;

      canvas.drawLine(
        Offset(x, topY),
        Offset(x, bottomY),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant DesktopAudioWavePainter oldDelegate) {
    return true;
  }
}
