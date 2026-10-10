import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The voice row of the composer, in the field's place: the live waveform while recording, a
/// shimmer while transcribing, and after a failure the reason in words with the kept recording's
/// waveform dimmed beside it. The actions (discard, try again) live in the composer's button row
/// underneath, where the mic and Send sit, so a failed recording asks nothing new of the thumb.
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
      if (!mounted) return;
      final provider = context.read<VoiceRecorderProvider>();
      provider.setCallbacks(onTranscriptReady: widget.onTranscriptReady, onClose: widget.onClose);

      if (provider.state == VoiceRecorderState.idle) {
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
                  baseColor: OmiColors.surface3,
                  highlightColor: OmiColors.textPrimary,
                  child: Text(
                    context.l10n.transcribing,
                    style: OmiType.subhead,
                  ),
                ),
              ),
            );

          case VoiceRecorderState.transcribeFailed:
          case VoiceRecorderState.pendingRecovery:
            // The reason in plain words, in the ink, never red: the recording is kept and Try
            // Again sits in the button row below.
            final recovered = provider.state == VoiceRecorderState.pendingRecovery;
            return SizedBox(
              height: 44,
              child: Row(
                children: [
                  Text(
                    key: const Key('chat_voice_status'),
                    recovered ? context.l10n.voiceRecordingFound : context.l10n.voiceFailedToTranscribe,
                    style: OmiType.callout.copyWith(color: OmiColors.textSecondary),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: SizedBox(
                      height: 28,
                      child: CustomPaint(
                        painter: AudioWavePainter(levels: provider.audioLevels, color: AudioWavePainter.restingInk),
                        child: const SizedBox.expand(),
                      ),
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

  /// The bars' colour; the ink while recording, [restingInk] for a kept recording.
  final Color color;

  AudioWavePainter({required List<double> levels, Color? color})
      : levels = List<double>.from(levels),
        color = color ?? liveInk;

  /// The waveform while it is being drawn.
  static Color get liveInk => OmiColors.textPrimary.withValues(alpha: 0.85);

  /// The waveform of a recording that is waiting (a failed or recovered one).
  static Color get restingInk => OmiColors.textPrimary.withValues(alpha: 0.32);

  @override
  void paint(Canvas canvas, Size size) {
    if (levels.isEmpty || size.width <= 0 || size.height <= 0) return;

    final paint = Paint()
      ..color = color
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
    if (color != oldDelegate.color) return true;
    if (levels.length != oldDelegate.levels.length) return true;
    for (int i = 0; i < levels.length; i++) {
      if ((levels[i] - oldDelegate.levels[i]).abs() > 0.005) return true;
    }
    return false;
  }
}
