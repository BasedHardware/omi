import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';

class VoiceRecorderWidget extends StatefulWidget {
  final Function(String) onTranscriptReady;
  final VoidCallback onClose;

  const VoiceRecorderWidget({super.key, required this.onTranscriptReady, required this.onClose});

  @override
  State<VoiceRecorderWidget> createState() => _VoiceRecorderWidgetState();
}

class _VoiceRecorderWidgetState extends State<VoiceRecorderWidget> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
      ..repeat(reverse: true);

    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<VoiceRecorderProvider>();
      provider.setCallbacks(onTranscriptReady: widget.onTranscriptReady, onClose: widget.onClose);
      if (!provider.isRecording) {
        provider.startRecording();
      }
    });
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  String _formatDuration(Duration d) {
    final minutes = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<VoiceRecorderProvider>(
      builder: (context, provider, child) {
        switch (provider.state) {
          case VoiceRecorderState.recording:
            return _buildRecordingState(provider);
          case VoiceRecorderState.transcribing:
            return _buildTranscribingState(context);
          case VoiceRecorderState.transcribeSuccess:
            return _buildSuccessState(context, provider);
          case VoiceRecorderState.transcribeFailed:
            return _buildFailedState(context, provider);
          case VoiceRecorderState.pendingRecovery:
            return _buildRecoveryState(context, provider);
          default:
            return const SizedBox.shrink();
        }
      },
    );
  }

  Widget _buildRecordingState(VoiceRecorderProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1E),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFF2A2A2E), width: 0.5),
      ),
      child: Row(
        children: [
          // Pulsing red recording indicator
          AnimatedBuilder(
            animation: _pulseController,
            builder: (context, child) {
              return Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color.lerp(
                    const Color(0xFFFF3B30),
                    const Color(0xFFFF3B30).withValues(alpha: 0.4),
                    _pulseController.value,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFFFF3B30).withValues(alpha: 0.3 * (1 - _pulseController.value)),
                      blurRadius: 8,
                      spreadRadius: 2,
                    ),
                  ],
                ),
              );
            },
          ),
          const SizedBox(width: 10),
          // Recording duration
          Text(
            _formatDuration(provider.recordingDuration),
            style: const TextStyle(
              color: Color(0xFF8E8E93),
              fontSize: 13,
              fontWeight: FontWeight.w500,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(width: 12),
          // Waveform
          Expanded(
            child: SizedBox(
              height: 32,
              child: CustomPaint(painter: AudioWavePainter(levels: provider.audioLevels)),
            ),
          ),
          const SizedBox(width: 8),
          // Cancel button
          GestureDetector(
            onTap: provider.close,
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(Icons.close_rounded, color: Color(0xFF8E8E93), size: 20),
            ),
          ),
          const SizedBox(width: 4),
          // Stop & send button
          GestureDetector(
            onTap: provider.processRecording,
            child: Container(
              width: 36,
              height: 36,
              decoration: const BoxDecoration(color: Color(0xFF34C759), shape: BoxShape.circle),
              child: const Icon(Icons.stop_rounded, color: Colors.white, size: 20),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTranscribingState(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1E),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFF2A2A2E), width: 0.5),
      ),
      child: Row(
        children: [
          const SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF8E8E93)),
          ),
          const SizedBox(width: 12),
          Text(
            context.l10n.transcribing,
            style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 14, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  Widget _buildSuccessState(BuildContext context, VoiceRecorderProvider provider) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF2A2A2E), width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(provider.transcript, style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.4)),
          const SizedBox(height: 10),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              GestureDetector(
                onTap: provider.close,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                  decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(16)),
                  child: Text(
                    context.l10n.cancel,
                    style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () => widget.onTranscriptReady(provider.transcript),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                  decoration: BoxDecoration(color: const Color(0xFF0A84FF), borderRadius: BorderRadius.circular(16)),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.send_rounded, color: Colors.white, size: 14),
                      const SizedBox(width: 6),
                      Text(
                        context.l10n.send,
                        style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFailedState(BuildContext context, VoiceRecorderProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1E),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFF3A2020), width: 0.5),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: Color(0xFFFF453A), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              context.l10n.voiceFailedToTranscribe,
              style: const TextStyle(color: Color(0xFFFF453A), fontSize: 13, fontWeight: FontWeight.w500),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: provider.retry,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(color: const Color(0xFF2A2A2E), borderRadius: BorderRadius.circular(14)),
              child: Text(
                context.l10n.retry,
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
              ),
            ),
          ),
          const SizedBox(width: 6),
          GestureDetector(
            onTap: provider.close,
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(Icons.close_rounded, color: Color(0xFF8E8E93), size: 18),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecoveryState(BuildContext context, VoiceRecorderProvider provider) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1E),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0xFF2A3A2A), width: 0.5),
      ),
      child: Row(
        children: [
          const Icon(Icons.mic_rounded, color: Color(0xFF34C759), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              context.l10n.voiceRecordingFound,
              style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: provider.retry,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(color: const Color(0xFF34C759), borderRadius: BorderRadius.circular(14)),
              child: Text(
                context.l10n.retry,
                style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          const SizedBox(width: 6),
          GestureDetector(
            onTap: provider.close,
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(Icons.close_rounded, color: Color(0xFF8E8E93), size: 18),
            ),
          ),
        ],
      ),
    );
  }
}

class AudioWavePainter extends CustomPainter {
  final List<double> levels;

  AudioWavePainter({required List<double> levels}) : levels = List<double>.from(levels);

  @override
  void paint(Canvas canvas, Size size) {
    if (levels.isEmpty) return;

    final width = size.width;
    final height = size.height;
    final barCount = levels.length;
    final totalBarWidth = width / barCount;
    final barWidth = 3.0;
    final gap = totalBarWidth - barWidth;

    for (int i = 0; i < barCount; i++) {
      final x = i * totalBarWidth + gap / 2;
      final level = levels[i];
      final barHeight = (level * height * 0.85).clamp(3.0, height);
      final topY = (height - barHeight) / 2;

      final paint = Paint()
        ..color = Color.lerp(const Color(0xFF3A3A3E), const Color(0xFF34C759), level.clamp(0.0, 1.0))!
        ..strokeWidth = barWidth
        ..strokeCap = StrokeCap.round;

      canvas.drawLine(Offset(x, topY), Offset(x, topY + barHeight), paint);
    }
  }

  @override
  bool shouldRepaint(covariant AudioWavePainter oldDelegate) {
    if (levels.length != oldDelegate.levels.length) return true;
    for (int i = 0; i < levels.length; i++) {
      if ((levels[i] - oldDelegate.levels[i]).abs() > 0.01) return true;
    }
    return false;
  }
}
