import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

import 'package:omi/utils/l10n_extensions.dart';

class OnboardingCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;

  const OnboardingCompleteScreen({super.key, required this.onComplete});

  @override
  State<OnboardingCompleteScreen> createState() => _OnboardingCompleteScreenState();
}

class _OnboardingCompleteScreenState extends State<OnboardingCompleteScreen> with SingleTickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _scaleAnimation;
  late Animation<double> _slideAnimation;

  @override
  void initState() {
    super.initState();

    _fadeController = AnimationController(duration: const Duration(milliseconds: 800), vsync: this);

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _fadeController, curve: Curves.easeOut));

    _scaleAnimation = Tween<double>(
      begin: 0.5,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _fadeController, curve: Curves.elasticOut));

    _slideAnimation = Tween<double>(
      begin: 50.0,
      end: 0.0,
    ).animate(CurvedAnimation(parent: _fadeController, curve: Curves.easeOut));

    Future.delayed(const Duration(milliseconds: 200), () {
      if (mounted) _fadeController.forward();
    });
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: OmiColors.surface0,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: AnimatedBuilder(
          animation: _fadeController,
          builder: (context, child) {
            return FadeTransition(
              opacity: _fadeAnimation,
              child: Transform.translate(
                offset: Offset(0, _slideAnimation.value),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 40),
                  child: Column(
                    children: [
                      const Spacer(flex: 3),
                      ScaleTransition(
                        scale: _scaleAnimation,
                        child: Container(
                          width: 72,
                          height: 72,
                          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
                          child: const Icon(Icons.check_rounded, color: OmiColors.textPrimary, size: 36),
                        ),
                      ),
                      const SizedBox(height: OmiSpacing.xxl),
                      Semantics(
                        header: true,
                        child: Text(
                          context.l10n.onboardingYoureAllSet,
                          style: OmiType.title1.copyWith(height: 1.2),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      const SizedBox(height: OmiSpacing.md),
                      Text(
                        context.l10n.onboardingCompleteMessage,
                        textAlign: TextAlign.center,
                        style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.5),
                      ),
                      const Spacer(flex: 3),
                      OmiButton(
                        key: const Key('onboarding_complete_start'),
                        label: context.l10n.startUsingOmi,
                        expand: true,
                        onPressed: () {
                          OmiHaptics.success();
                          widget.onComplete();
                        },
                      ),
                      const SizedBox(height: OmiSpacing.xxl),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
