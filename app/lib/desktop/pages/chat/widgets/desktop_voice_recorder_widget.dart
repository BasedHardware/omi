import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/file.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:shimmer/shimmer.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';

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

  // Platform channel for desktop permissions
  static const MethodChannel _screenCaptureChannel = MethodChannel('screenCapturePlatform');

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
      ServiceManager.instance().systemAudio.stop();
    }

    super.dispose();
  }

  Future<bool> _checkAndRequestMicrophonePermission() async {
    try {
      // Check microphone permission first
      String micStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');

      if (micStatus != 'granted') {
        if (micStatus == 'undetermined' || micStatus == 'unavailable') {
          bool micGranted = await _screenCaptureChannel.invokeMethod('requestMicrophonePermission');
          if (!micGranted) {
            AppSnackbar.showSnackbarError('Microphone permission is required for voice recording.');
            return false;
          }
        } else if (micStatus == 'denied') {
          AppSnackbar.showSnackbarError(
              'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.');
          return false;
        }
      }
      return true;
    } catch (e) {
      AppSnackbar.showSnackbarError('Failed to check Microphone permission: $e');
      return false;
    }
  }

  Future<void> _startRecording() async {
    // Check and request microphone permission using desktop platform channel
    if (!await _checkAndRequestMicrophonePermission()) {
      setState(() {
        _state = RecordingState.transcribeFailed;
      });
      return;
    }

    await ServiceManager.instance().systemAudio.start(
      onByteReceived: (bytes) {
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
            });
          }
        }
      },
      onFormatReceived: (format) {
        debugPrint('Audio format received: $format');
      },
      onRecording: () {
        debugPrint('Recording started');
        setState(() {
          _state = RecordingState.recording;
          _audioChunks = [];
          for (int i = 0; i < _audioLevels.length; i++) {
            _audioLevels[i] = 0.1;
          }
        });
      },
      onStop: () {
        debugPrint('Recording stopped');
      },
      onError: (error) {
        debugPrint('Recording error: $error');
        setState(() {
          _state = RecordingState.transcribeFailed;
        });
      },
    );
  }

  Future<void> _stopRecording() async {
    _waveformTimer?.cancel();
    ServiceManager.instance().systemAudio.stop();
  }

  void _cancelRecording() {
    // Stop recording and close widget without processing
    _waveformTimer?.cancel();
    ServiceManager.instance().systemAudio.stop();
    widget.onClose();
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
              Padding(
                padding: const EdgeInsets.all(8),
                child: OmiIconButton(
                  icon: Icons.close,
                  style: OmiIconButtonStyle.outline,
                  borderOpacity: 0.12,
                  size: 32,
                  iconSize: 14,
                  borderRadius: 8,
                  onPressed: _cancelRecording,
                ),
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
              Padding(
                padding: const EdgeInsets.all(8),
                child: OmiIconButton(
                  icon: Icons.check,
                  style: OmiIconButtonStyle.filled,
                  color: ResponsiveHelper.purplePrimary,
                  solid: true,
                  size: 32,
                  iconSize: 14,
                  borderRadius: 8,
                  onPressed: _processRecording,
                ),
              )
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
                child: const Text(
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
                style: const TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                OmiIconButton(
                  icon: Icons.close,
                  style: OmiIconButtonStyle.outline,
                  borderOpacity: 0.12,
                  size: 28,
                  iconSize: 12,
                  borderRadius: 8,
                  onPressed: widget.onClose,
                ),
                const SizedBox(width: 4),
                OmiIconButton(
                  icon: Icons.send,
                  style: OmiIconButtonStyle.filled,
                  color: ResponsiveHelper.purplePrimary,
                  solid: true,
                  size: 28,
                  iconSize: 12,
                  borderRadius: 8,
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
              const Flexible(
                child: Text(
                  'Transcription failed',
                  style: TextStyle(
                    color: Colors.redAccent,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 2,
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
                  OmiIconButton(
                    icon: Icons.refresh,
                    style: OmiIconButtonStyle.filled,
                    color: ResponsiveHelper.purplePrimary,
                    solid: true,
                    size: 28,
                    iconSize: 12,
                    borderRadius: 6,
                    onPressed: _retry,
                  ),
                  const SizedBox(width: 4),
                  OmiIconButton(
                    icon: Icons.close,
                    style: OmiIconButtonStyle.outline,
                    borderOpacity: 0.12,
                    size: 28,
                    iconSize: 12,
                    borderRadius: 8,
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
