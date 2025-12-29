import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

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
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);

    // Set up callbacks and start recording
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<VoiceRecorderProvider>();
      provider.setCallbacks(
        onTranscriptReady: widget.onTranscriptReady,
        onClose: widget.onClose,
      );
      
      // Only start recording if not already recording
      if (!provider.isRecording) {
        provider.startRecording();
      }
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    // Don't stop recording on dispose - let it continue across page navigation
    // The provider will handle cleanup when close() is called
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<VoiceRecorderProvider>(
      builder: (context, provider, child) {
        switch (provider.state) {
          case VoiceRecorderState.recording:
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
                    onPressed: provider.close,
                  ),
                  Expanded(
                    child: SizedBox(
                      height: 40,
                      child: CustomPaint(
                        painter: AudioWavePainter(
                          levels: provider.audioLevels,
                          timestamp: DateTime.now(),
                        ),
                      ),
                    ),
                  ),
                  GestureDetector(
                    onTap: provider.processRecording,
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

          case VoiceRecorderState.transcribing:
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
                    baseColor: Color(0xFF35343B),
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

          case VoiceRecorderState.transcribeSuccess:
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
                    provider.transcript,
                    style: const TextStyle(color: Colors.white),
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white),
                      onPressed: provider.close,
                    ),
                    IconButton(
                      icon: const Icon(Icons.send, color: Colors.white),
                      onPressed: () => widget.onTranscriptReady(provider.transcript),
                    ),
                  ],
                ),
              ],
            );

          case VoiceRecorderState.transcribeFailed:
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
                          levels: provider.audioLevels,
                          timestamp: DateTime.now(),
                        ),
                      ),
                    ),
                  ),
                  Row(
                    children: [
                      GestureDetector(
                          onTap: provider.retry,
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
                        onTap: provider.close,
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
      },
    );
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
