import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
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
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat();
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
              if (!provider.transcriptionComplete) ...[
                const Spacer(flex: 1),
                _buildOmiWithPulse(),
                const SizedBox(height: 32),
              ],
              if (provider.transcriptionComplete) ...[
                const SizedBox(height: 16),
                _buildSuccessCard(),
                const SizedBox(height: 16),
              ],
              if (provider.demoSegments.isNotEmpty) _buildTranscriptCard(provider),
              const Spacer(flex: 2),
            ],
          ),
          bottomAction: _showContinue ? OnboardingContinueButton(onPressed: widget.onComplete) : null,
        );
      },
    );
  }

  Widget _buildSuccessCard() {
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

  Widget _buildOmiWithPulse() {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 160.0;
    const containerSize = imageSize + 160.0;

    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, child) {
        return SizedBox(
          width: containerSize,
          height: containerSize,
          child: Stack(
            alignment: Alignment.center,
            children: [
              for (int i = 0; i < 3; i++) _buildPulseCircle(i, imageSize, containerSize),
              Image.asset(
                Assets.images.omiWithoutRope.path,
                height: imageSize,
                width: imageSize,
                cacheHeight: (imageSize * pixelRatio).round(),
                cacheWidth: (imageSize * pixelRatio).round(),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildPulseCircle(int index, double imageSize, double containerSize) {
    final progress = (_pulseController.value + index * 0.33) % 1.0;
    final diameter = imageSize + (containerSize - imageSize) * progress;
    final opacity = (1.0 - progress).clamp(0.0, 0.25);

    return Container(
      width: diameter,
      height: diameter,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: Colors.white.withValues(alpha: opacity),
          width: 1.5,
        ),
      ),
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
