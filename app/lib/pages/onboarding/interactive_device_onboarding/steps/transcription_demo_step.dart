import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/l10n_extensions.dart';

class TranscriptionDemoStep extends StatefulWidget {
  final VoidCallback onComplete;

  const TranscriptionDemoStep({super.key, required this.onComplete});

  @override
  State<TranscriptionDemoStep> createState() => _TranscriptionDemoStepState();
}

class _TranscriptionDemoStepState extends State<TranscriptionDemoStep>
    with SingleTickerProviderStateMixin, DeviceTutorialNativeArtwork {
  late AnimationController _pulseController;
  bool _showContinue = false;
  bool _continueScheduled = false;

  @override
  void initState() {
    super.initState();
    // The pulse runs only while the classic step is mounted ([DeviceTutorialClassicAnimations]).
    _pulseController = AnimationController(vsync: this, duration: const Duration(seconds: 4));
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
        if (provider.transcriptionComplete && !_continueScheduled) {
          _continueScheduled = true;
          Future.delayed(const Duration(seconds: 1), () {
            if (mounted) setState(() => _showContinue = true);
          });
        }

        final classic = DeviceTutorialClassicAnimations(
            onMount: _pulseController.repeat,
            onUnmount: _pulseController.stop,
            child: OnboardingStepScaffold(
              title: context.l10n.deviceOnboardingTranscriptionTitle,
              subtitle: provider.transcriptionComplete ? '' : context.l10n.deviceOnboardingTranscriptionSubtitle,
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
            ));
        if (!deviceTutorialNative(context)) return classic;
        return _nativeSurface(provider, classic);
      },
    );
  }

  /// The pulse rings are decorative; static device art and the same copy replace them natively.
  Widget _nativeSurface(DeviceOnboardingProvider provider, Widget classic) {
    final l10n = context.l10n;
    final transcript = provider.demoSegments.map((s) => s.text).join(' ');
    return IosNativeSurface(title: l10n.deviceOnboardingTranscriptionTitle, fallback: classic, sections: [
      NativeSection('dev_tut_transcription', [
        if (provider.transcriptionComplete)
          NativeRow('dev_tut_transcription_done', l10n.deviceOnboardingGoodJob,
              kind: 'label', symbol: 'checkmark.circle.fill')
        else
          NativeRow('dev_tut_transcription_status', l10n.deviceOnboardingTranscriptionSubtitle,
              kind: 'label', imageUri: nativeArtwork(Assets.images.omiWithoutRope.path)),
        if (provider.demoSegments.isNotEmpty)
          NativeRow('dev_tut_transcript', deviceTutorialNativeText(transcript), kind: 'label'),
      ]),
      if (_showContinue) NativeSection('dev_tut_actions', [deviceTutorialContinueRow(context, widget.onComplete)]),
    ]);
  }

  Widget _buildSuccessCard() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
      decoration: BoxDecoration(
        color: const Color(0xFF4CAF50).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.check_circle, color: Color(0xFF4CAF50), size: 24),
          const SizedBox(width: 12),
          Text(
            context.l10n.deviceOnboardingGoodJob,
            style: const TextStyle(color: Color(0xFF4CAF50), fontSize: 20, fontWeight: FontWeight.w600),
          ),
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
        border: Border.all(color: OmiColors.textPrimary.withValues(alpha: opacity), width: 1.5),
      ),
    );
  }

  Widget _buildTranscriptCard(DeviceOnboardingProvider provider) {
    final text = provider.demoSegments.map((s) => s.text).join(' ');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: BorderRadius.circular(20)),
      child: Text(
        text,
        style: TextStyle(color: OmiColors.textPrimary, fontSize: 17, height: 1.5),
        textAlign: TextAlign.left,
      ),
    );
  }
}
