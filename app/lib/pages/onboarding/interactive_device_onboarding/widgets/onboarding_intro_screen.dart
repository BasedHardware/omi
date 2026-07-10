import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
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
              SizedBox(
                height: 48,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: IconButton(
                    icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
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
                style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                context.l10n.deviceOnboardingIntroSubtitle,
                style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 16, height: 1.4),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.schedule, color: Color(0xFF9E9E9E), size: 16),
                  const SizedBox(width: 6),
                  Text(
                    context.l10n.deviceOnboardingIntroDuration,
                    style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 13),
                  ),
                ],
              ),
              const Spacer(flex: 3),
              OnboardingContinueButton(label: context.l10n.getStarted, onPressed: widget.onStart),
              const SizedBox(height: 8),
              TextButton(
                key: const Key('device_onboarding_skip_button'),
                onPressed: widget.onSkip ?? () => Navigator.of(context).maybePop(),
                child: Text(
                  context.l10n.skipForNow,
                  style: const TextStyle(color: Color(0xFF9E9E9E), fontSize: 15),
                ),
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
