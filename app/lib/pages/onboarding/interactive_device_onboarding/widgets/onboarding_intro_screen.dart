import 'package:flutter/material.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/widgets/onboarding_step_scaffold.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OnboardingIntroScreen extends StatelessWidget {
  final VoidCallback onStart;
  final bool allowExit;

  const OnboardingIntroScreen({super.key, required this.onStart, this.allowExit = false});

  @override
  Widget build(BuildContext context) {
    final pixelRatio = MediaQuery.of(context).devicePixelRatio;
    const imageSize = 190.0;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          SizedBox(
            height: 48,
            child: allowExit
                ? Align(
                    alignment: Alignment.centerLeft,
                    child: IconButton(
                      icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                  )
                : null,
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
                    gradient: RadialGradient(
                      colors: [Colors.white.withValues(alpha: 0.10), Colors.transparent],
                    ),
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
          OnboardingContinueButton(label: context.l10n.getStarted, onPressed: onStart),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
