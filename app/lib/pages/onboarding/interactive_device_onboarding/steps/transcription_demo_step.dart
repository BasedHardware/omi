import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/live_transcript_display.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';

class TranscriptionDemoStep extends StatefulWidget {
  final VoidCallback onComplete;

  const TranscriptionDemoStep({super.key, required this.onComplete});

  @override
  State<TranscriptionDemoStep> createState() => _TranscriptionDemoStepState();
}

class _TranscriptionDemoStepState extends State<TranscriptionDemoStep> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  bool _showContinue = false;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(
      builder: (context, provider, _) {
        if (provider.transcriptionComplete && !_showContinue) {
          Future.delayed(const Duration(seconds: 2), () {
            if (mounted) setState(() => _showContinue = true);
          });
        }

        return OnboardingStepScaffold(
          title: 'Speak Into Your Omi',
          subtitle: 'Say a few words and watch them appear in real-time',
          currentStep: 0,
          content: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (!provider.transcriptionComplete) ...[
                _buildPulsingMic(),
                const SizedBox(height: 32),
              ],
              if (provider.transcriptionComplete) ...[
                const Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 64),
                const SizedBox(height: 16),
                const Text('Good job!', style: TextStyle(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold)),
                const SizedBox(height: 24),
              ],
              Expanded(
                child: LiveTranscriptDisplay(segments: provider.demoSegments),
              ),
            ],
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  Widget _buildPulsingMic() {
    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, child) {
        final scale = 1.0 + (_pulseController.value * 0.15);
        return Transform.scale(
          scale: scale,
          child: Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withValues(alpha: 0.1),
              border: Border.all(color: Colors.white.withValues(alpha: 0.3), width: 2),
            ),
            child: const Icon(Icons.mic, color: Colors.white, size: 40),
          ),
        );
      },
    );
  }
}
