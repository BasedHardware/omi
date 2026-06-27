import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Compact waveform pill that lives inside the chat input row, between the
/// stop button and the send button. Mirrors the visual treatment of the
/// regular text field so the input bar feels cohesive in voice mode.
class VoiceRecorderWidget extends StatefulWidget {
  final Function(String transcript, bool autoSend) onTranscriptReady;
  final VoidCallback onClose;

  const VoiceRecorderWidget({super.key, required this.onTranscriptReady, required this.onClose});

  @override
  State<VoiceRecorderWidget> createState() => _VoiceRecorderWidgetState();
}

class _VoiceRecorderWidgetState extends State<VoiceRecorderWidget> with SingleTickerProviderStateMixin {
  late AnimationController _animationController;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))
      ..repeat(reverse: true);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<VoiceRecorderProvider>();
      provider.setCallbacks(onTranscriptReady: widget.onTranscriptReady, onClose: widget.onClose);

      if (!provider.isRecording && !provider.hasPendingRecording) {
        provider.startRecording();
      }
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<VoiceRecorderProvider>(
      builder: (context, provider, child) {
        switch (provider.state) {
          case VoiceRecorderState.recording:
            return SizedBox(
              height: 44,
              child: CustomPaint(
                painter: AudioWavePainter(levels: provider.audioLevels),
                child: const SizedBox.expand(),
              ),
            );

          case VoiceRecorderState.transcribing:
            return SizedBox(
              height: 44,
              child: Center(
                child: ShimmerWithTimeout(
                  baseColor: const Color(0xFF35343B),
                  highlightColor: Colors.white,
                  child: Text(
                    context.l10n.transcribing,
                    style: const TextStyle(color: Colors.white, fontSize: 15),
                  ),
                ),
              ),
            );

          case VoiceRecorderState.transcribeFailed:
          case VoiceRecorderState.pendingRecovery:
            return SizedBox(
              height: 44,
              child: Row(
                children: [
                  Text(
                    provider.state == VoiceRecorderState.pendingRecovery
                        ? context.l10n.voiceRecordingFound
                        : context.l10n.error,
                    style: TextStyle(
                      color: provider.state == VoiceRecorderState.pendingRecovery ? Colors.white : Colors.redAccent,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: SizedBox(
                      height: 32,
                      child: CustomPaint(
                        painter: AudioWavePainter(levels: provider.audioLevels),
                        child: const SizedBox.expand(),
                      ),
                    ),
                  ),
                  GestureDetector(
                    onTap: provider.retry,
                    child: const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 8),
                      child: Icon(Icons.refresh, color: Colors.white, size: 20),
                    ),
                  ),
                ],
              ),
            );

          default:
            return const SizedBox(height: 44);
        }
      },
    );
  }
}

class AudioWavePainter extends CustomPainter {
  final List<double> levels;

  AudioWavePainter({required List<double> levels}) : levels = List<double>.from(levels);

  @override
  void paint(Canvas canvas, Size size) {
    if (levels.isEmpty || size.width <= 0 || size.height <= 0) return;

    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.85)
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round;

    final width = size.width;
    final height = size.height;
    final centerY = height / 2;
    // Even spacing across the full width regardless of level count.
    final spacing = width / levels.length;
    // Min bar = a small dot so silence still reads as "active".
    const minBarHeight = 3.0;
    final maxBarHeight = height * 0.92;

    for (int i = 0; i < levels.length; i++) {
      final x = spacing * (i + 0.5);
      final level = levels[i].clamp(0.0, 1.0);
      final barHeight = (minBarHeight + level * (maxBarHeight - minBarHeight)).clamp(minBarHeight, maxBarHeight);

      canvas.drawLine(
        Offset(x, centerY - barHeight / 2),
        Offset(x, centerY + barHeight / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant AudioWavePainter oldDelegate) {
    if (levels.length != oldDelegate.levels.length) return true;
    for (int i = 0; i < levels.length; i++) {
      if ((levels[i] - oldDelegate.levels[i]).abs() > 0.005) return true;
    }
    return false;
  }
}
