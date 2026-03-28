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
            return EndConversationDemo(key: const ValueKey(0), doubleTapped: provider.doublePressDetected);
          case 1:
            return MuteUnmuteDemo(key: const ValueKey(1), doubleTapped: provider.doublePressDetected);
          case 2:
            return StarConversationDemo(key: const ValueKey(2), doubleTapped: provider.doublePressDetected);
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
                color: isMuted ? const Color(0xFF9E9E9E) : const Color(0xFF4CAF50),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: CustomPaint(
                painter: _WaveformPainter(
                  phase: wavePhase,
                  color: isMuted ? const Color(0xFF555555) : waveColor.withValues(alpha: 0.6),
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
              const Icon(Icons.mic_off, color: Color(0xFF9E9E9E), size: 18),
            ],
          ],
        ),
      ),
    );
  }
}

// --- End Conversation Demo ---

class EndConversationDemo extends StatefulWidget {
  final bool doubleTapped;

  const EndConversationDemo({super.key, required this.doubleTapped});

  @override
  State<EndConversationDemo> createState() => _EndConversationDemoState();
}

class _EndConversationDemoState extends State<EndConversationDemo> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  bool _showNewConversation = false;
  double _cutPhase = 0;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  }

  @override
  void didUpdateWidget(EndConversationDemo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.doubleTapped && !oldWidget.doubleTapped) {
      _cutPhase = _controller.value * 2 * pi * 3;
      setState(() => _showNewConversation = false);
      Future.delayed(const Duration(milliseconds: 600), () {
        if (mounted) setState(() => _showNewConversation = true);
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
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // First conversation - fades out after double tap
            AnimatedOpacity(
              duration: const Duration(milliseconds: 400),
              opacity: widget.doubleTapped ? 0.3 : 1.0,
              child: _ConversationCard(
                wavePhase: widget.doubleTapped ? _cutPhase : phase,
                waveAmplitude: widget.doubleTapped ? 0.0 : 1.0,
              ),
            ),
            if (_showNewConversation) ...[
              const SizedBox(height: 8),
              _ConversationCard(
                wavePhase: phase,
                waveAmplitude: 0.3 + (_controller.value * 0.7),
                waveColor: const Color(0xFF81C784),
              ),
            ],
          ],
        );
      },
    );
  }
}

// --- Mute/Unmute Demo ---

class MuteUnmuteDemo extends StatefulWidget {
  final bool doubleTapped;

  const MuteUnmuteDemo({super.key, required this.doubleTapped});

  @override
  State<MuteUnmuteDemo> createState() => _MuteUnmuteDemoState();
}

class _MuteUnmuteDemoState extends State<MuteUnmuteDemo> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  bool _isMuted = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  }

  @override
  void didUpdateWidget(MuteUnmuteDemo oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.doubleTapped && !oldWidget.doubleTapped) {
      setState(() => _isMuted = !_isMuted);
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
        return _ConversationCard(
          wavePhase: phase,
          isMuted: _isMuted,
        );
      },
    );
  }
}

// --- Star Conversation Demo ---

class StarConversationDemo extends StatefulWidget {
  final bool doubleTapped;

  const StarConversationDemo({super.key, required this.doubleTapped});

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
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final phase = _controller.value * 2 * pi * 3;
        return Stack(
          children: [
            // Bottom card (oldest)
            Padding(
              padding: const EdgeInsets.only(top: 16, left: 16, right: 16),
              child: _ConversationCard(
                wavePhase: 0,
                waveAmplitude: 0,
                opacity: 0.3,
              ),
            ),
            // Middle card
            Padding(
              padding: const EdgeInsets.only(top: 8, left: 8, right: 8),
              child: _ConversationCard(
                wavePhase: 0,
                waveAmplitude: 0,
                opacity: 0.5,
              ),
            ),
            // Top card (active) with live waveform
            _ConversationCard(
              wavePhase: phase,
              waveAmplitude: 1.0,
              showStar: widget.doubleTapped,
            ),
          ],
        );
      },
    );
  }
}
