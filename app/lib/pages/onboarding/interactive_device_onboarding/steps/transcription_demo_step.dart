import 'dart:math';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

class TranscriptionDemoStep extends StatefulWidget {
  final VoidCallback onComplete;

  const TranscriptionDemoStep({super.key, required this.onComplete});

  @override
  State<TranscriptionDemoStep> createState() => _TranscriptionDemoStepState();
}

class _TranscriptionDemoStepState extends State<TranscriptionDemoStep> with SingleTickerProviderStateMixin {
  late AnimationController _waveController;
  bool _showContinue = false;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
  }

  @override
  void dispose() {
    _waveController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        if (provider.transcriptionComplete && !_showContinue) {
          Future.delayed(const Duration(seconds: 1), () {
            if (mounted) setState(() => _showContinue = true);
          });
        }

        return OnboardingStepScaffold(
          title: 'Speak Into Your Omi',
          subtitle: provider.transcriptionComplete ? '' : 'Say a few words and watch them appear in real-time',
          currentStep: 0,
          content: Column(
            children: [
              const Spacer(flex: 1),
              // Status card
              _buildStatusCard(provider),
              const SizedBox(height: 16),
              // Transcript card
              if (provider.demoSegments.isNotEmpty) _buildTranscriptCard(provider),
              const Spacer(flex: 2),
            ],
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  Widget _buildStatusCard(DeviceOnboardingProvider provider) {
    if (provider.transcriptionComplete) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        decoration: BoxDecoration(
          color: const Color(0xFF4CAF50).withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(20),
        ),
        child: const Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 24),
            SizedBox(width: 12),
            Text('Good job!', style: TextStyle(color: Color(0xFF4CAF50), fontSize: 20, fontWeight: FontWeight.w600)),
          ],
        ),
      );
    }

    // Listening state with waveform
    return AnimatedBuilder(
      animation: _waveController,
      builder: (context, _) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            children: [
              const Icon(Icons.mic, color: Colors.white, size: 22),
              const SizedBox(width: 14),
              Expanded(
                child: CustomPaint(
                  painter: _LiveWavePainter(
                    phase: _waveController.value * 2 * pi * 3,
                    color: Colors.white.withValues(alpha: 0.4),
                  ),
                  size: const Size(double.infinity, 28),
                ),
              ),
              const SizedBox(width: 14),
              Text(
                '${provider.wordCount}/5',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.5),
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildTranscriptCard(DeviceOnboardingProvider provider) {
    final text = provider.demoSegments.map((s) => s.text).join(' ');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        text,
        style: const TextStyle(color: Colors.white, fontSize: 17, height: 1.5),
        textAlign: TextAlign.left,
      ),
    );
  }
}

class _LiveWavePainter extends CustomPainter {
  final double phase;
  final Color color;

  _LiveWavePainter({required this.phase, required this.color});

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
      final n = x / size.width;
      final y = midY + sin((n * 4 * pi) + phase) * 8 + sin((n * 11 * pi) + phase * 1.7) * 4;
      if (x == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_LiveWavePainter oldDelegate) => phase != oldDelegate.phase;
}
