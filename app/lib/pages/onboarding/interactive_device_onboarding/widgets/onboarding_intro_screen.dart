import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OnboardingIntroScreen extends StatefulWidget {
  final VoidCallback onStart;
  final VoidCallback? onSkip;

  const OnboardingIntroScreen({super.key, required this.onStart, this.onSkip});

  @override
  State<OnboardingIntroScreen> createState() => _OnboardingIntroScreenState();
}

class _OnboardingIntroScreenState extends State<OnboardingIntroScreen> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 6))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 190.0;

    return Stack(
      children: [
        Positioned.fill(child: _buildAnimatedBackground()),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              // The tutorial floats over the app: it leaves by a trailing close X.
              SizedBox(
                height: 48,
                child: Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: OmiCloseButton(
                    key: const Key('device_onboarding_close_button'),
                    onPressed: widget.onSkip ?? () => Navigator.of(context).maybePop(),
                  ),
                ),
              ),
              const Spacer(flex: 2),
              SizedBox(
                width: 280,
                height: 280,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(
                      width: 240,
                      height: 240,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: RadialGradient(colors: [Colors.white.withValues(alpha: 0.10), Colors.transparent]),
                      ),
                    ),
                    Image.asset(
                      Assets.images.omiWithoutRope.path,
                      height: imageSize,
                      width: imageSize,
                      cacheHeight: (imageSize * pixelRatio).round(),
                      cacheWidth: (imageSize * pixelRatio).round(),
                    ),
                  ],
                ),
              ),
              const Spacer(flex: 2),
              Text(
                context.l10n.deviceOnboardingIntroTitle,
                style: OmiType.title1,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                context.l10n.deviceOnboardingIntroSubtitle,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const ExcludeSemantics(child: Icon(Icons.schedule, color: OmiColors.textSecondary, size: 16)),
                  const SizedBox(width: 6),
                  Text(
                    context.l10n.deviceOnboardingIntroDuration,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                  ),
                ],
              ),
              const Spacer(flex: 3),
              OnboardingContinueButton(label: context.l10n.getStarted, onPressed: widget.onStart),
              const SizedBox(height: 8),
              OmiButton.tertiary(
                key: const Key('device_onboarding_skip_button'),
                label: context.l10n.skip,
                onPressed: widget.onSkip ?? () => Navigator.of(context).maybePop(),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAnimatedBackground() {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final t = Curves.easeInOut.transform(_controller.value);
        return Stack(
          children: [
            _glowOrb(
              alignment: Alignment.lerp(const Alignment(-1.1, -0.9), const Alignment(0.2, -1.2), t)!,
              size: 380,
              alpha: 0.16 + 0.10 * t,
            ),
          ],
        );
      },
    );
  }

  Widget _glowOrb({required Alignment alignment, required double size, required double alpha}) {
    return Align(
      alignment: alignment,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              Colors.white.withValues(alpha: alpha),
              Colors.transparent,
            ],
          ),
        ),
      ),
    );
  }
}
