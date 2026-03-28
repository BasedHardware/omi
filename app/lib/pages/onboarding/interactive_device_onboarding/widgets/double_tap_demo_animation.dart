import 'dart:math';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';

class DoubleTapDemoAnimation extends StatefulWidget {
  const DoubleTapDemoAnimation({super.key});

  @override
  State<DoubleTapDemoAnimation> createState() => _DoubleTapDemoAnimationState();
}

class _DoubleTapDemoAnimationState extends State<DoubleTapDemoAnimation> {
  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        switch (provider.selectedDoubleTapAction) {
          case 0:
            return EndConversationDemo(key: const ValueKey(0), doublePressCount: provider.doublePressCount);
          case 1:
            return MuteUnmuteDemo(key: const ValueKey(1), doublePressCount: provider.doublePressCount);
          case 2:
            return StarConversationDemo(key: const ValueKey(2), doublePressCount: provider.doublePressCount);
          default:
            return const SizedBox.shrink();
        }
      },
    );
  }
}

// --- Waveform painter ---

class _WaveformPainter extends CustomPainter {
  final double phase;
  final Color color;
  final double amplitude;

  _WaveformPainter({required this.phase, required this.color, this.amplitude = 1.0});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2.0
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final path = Path();
    final midY = size.height / 2;

    for (double x = 0; x < size.width; x += 1) {
      final normalized = x / size.width;
      final wave = sin((normalized * 4 * pi) + phase) * (8 * amplitude);
      final noise = sin((normalized * 11 * pi) + phase * 1.7) * (4 * amplitude);
      if (x == 0) {
        path.moveTo(x, midY + wave + noise);
      } else {
        path.lineTo(x, midY + wave + noise);
      }
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_WaveformPainter oldDelegate) =>
      phase != oldDelegate.phase || amplitude != oldDelegate.amplitude || color != oldDelegate.color;
}

// --- Conversation card ---

class _ConversationCard extends StatelessWidget {
  final double wavePhase;
  final double waveAmplitude;
  final Color waveColor;
  final bool showStar;
  final bool isMuted;
  final double opacity;

  const _ConversationCard({
    required this.wavePhase,
    this.waveAmplitude = 1.0,
    this.waveColor = Colors.white,
    this.showStar = false,
    this.isMuted = false,
    this.opacity = 1.0,
  });

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: opacity,
      child: Container(
        height: 64,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isMuted ? const Color(0xFFEF5350) : const Color(0xFF4CAF50),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: CustomPaint(
                painter: _WaveformPainter(
                  phase: wavePhase,
                  color: isMuted ? const Color(0xFFEF5350).withValues(alpha: 0.4) : waveColor.withValues(alpha: 0.6),
                  amplitude: isMuted ? 0.1 : waveAmplitude,
                ),
                size: const Size(double.infinity, 32),
              ),
            ),
            if (showStar) ...[
              const SizedBox(width: 12),
              const Icon(Icons.star, color: Color(0xFFFFD700), size: 22),
            ],
            if (isMuted) ...[
              const SizedBox(width: 12),
              const Icon(Icons.mic_off, color: Color(0xFFEF5350), size: 18),
            ],
          ],
        ),
      ),
    );
  }
}

// --- End Conversation Demo ---

class EndConversationDemo extends StatefulWidget {
  final int doublePressCount;

  const EndConversationDemo({super.key, required this.doublePressCount});

  @override
  State<EndConversationDemo> createState() => _EndConversationDemoState();
}

class _EndConversationDemoState extends State<EndConversationDemo> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  double _cutPhase = 0;
  double _splitPosition = 0.5;
  bool _isSplit = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  }

  @override
  void didUpdateWidget(EndConversationDemo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.doublePressCount > oldWidget.doublePressCount) {
      _cutPhase = _controller.value * 2 * pi * 3;
      _splitPosition = 0.35 + (_controller.value * 0.3);
      setState(() => _isSplit = true);
      // Reset after 2 seconds to allow another split
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) setState(() => _isSplit = false);
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final phase = _controller.value * 2 * pi * 3;
        return Container(
          height: 64,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
          ),
          child: Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFF4CAF50)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _isSplit
                    ? _buildSplitWaveform(phase)
                    : CustomPaint(
                        painter: _WaveformPainter(phase: phase, color: Colors.white.withValues(alpha: 0.6)),
                        size: const Size(double.infinity, 32),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildSplitWaveform(double livePhase) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final totalWidth = constraints.maxWidth;
        final leftWidth = totalWidth * _splitPosition;
        const gapWidth = 12.0;
        final rightWidth = totalWidth - leftWidth - gapWidth;

        return Row(
          children: [
            SizedBox(
              width: leftWidth,
              height: 32,
              child: CustomPaint(
                painter: _WaveformPainter(phase: _cutPhase, color: Colors.white.withValues(alpha: 0.2)),
              ),
            ),
            SizedBox(
              width: gapWidth,
              child: Center(
                child: Container(
                  width: 2,
                  height: 24,
                  decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.3), borderRadius: BorderRadius.circular(1)),
                ),
              ),
            ),
            SizedBox(
              width: rightWidth > 0 ? rightWidth : 0,
              height: 32,
              child: CustomPaint(
                painter: _WaveformPainter(phase: livePhase, color: const Color(0xFF81C784).withValues(alpha: 0.7)),
              ),
            ),
          ],
        );
      },
    );
  }
}

// --- Mute/Unmute Demo ---

class MuteUnmuteDemo extends StatefulWidget {
  final int doublePressCount;

  const MuteUnmuteDemo({super.key, required this.doublePressCount});

  @override
  State<MuteUnmuteDemo> createState() => _MuteUnmuteDemoState();
}

class _MuteUnmuteDemoState extends State<MuteUnmuteDemo> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isMuted = widget.doublePressCount.isOdd;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final phase = _controller.value * 2 * pi * 3;
        return _ConversationCard(
          wavePhase: phase,
          isMuted: isMuted,
        );
      },
    );
  }
}

// --- Star Conversation Demo ---

class StarConversationDemo extends StatefulWidget {
  final int doublePressCount;

  const StarConversationDemo({super.key, required this.doublePressCount});

  @override
  State<StarConversationDemo> createState() => _StarConversationDemoState();
}

class _StarConversationDemoState extends State<StarConversationDemo> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isStarred = widget.doublePressCount.isOdd;
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final phase = _controller.value * 2 * pi * 3;
        return _ConversationCard(
          wavePhase: phase,
          waveAmplitude: 1.0,
          showStar: isStarred,
        );
      },
    );
  }
}
