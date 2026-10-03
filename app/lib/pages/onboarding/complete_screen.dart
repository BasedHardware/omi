import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/services/siri_integration.dart';
import 'package:omi/ui/ui.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

class OnboardingCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;

  /// Overrides the iOS 16 App Shortcuts gate for tests; null defers to the platform.
  final bool? showSiriHint;
  @visibleForTesting
  final Future<bool> Function()? appShortcutsAvailabilityProbe;

  const OnboardingCompleteScreen({
    super.key,
    required this.onComplete,
    this.showSiriHint,
    this.appShortcutsAvailabilityProbe,
  });

  @override
  State<OnboardingCompleteScreen> createState() => _OnboardingCompleteScreenState();
}

class _OnboardingCompleteScreenState extends State<OnboardingCompleteScreen> with SingleTickerProviderStateMixin {
  late AnimationController _fadeController;
  late Animation<double> _fadeAnimation;
  late Animation<double> _scaleAnimation;
  late Animation<double> _slideAnimation;

  // App Shortcuts phrases require iOS 16 and a Siri-enabled app build.
  late final bool _siriHintVersionSupported = widget.showSiriHint ?? PlatformService.isIOSAtLeast(16);
  bool _appShortcutsAvailable = false;

  Future<void> _loadAppShortcutsAvailability() async {
    try {
      final available =
          await (widget.appShortcutsAvailabilityProbe ?? SiriIntegration.instance.appShortcutsAvailable)();
      if (mounted) setState(() => _appShortcutsAvailable = available);
    } catch (_) {
      // Fail closed: keep the hint hidden when the bridge cannot answer.
    }
  }

  @override
  void initState() {
    super.initState();

    if (_siriHintVersionSupported) _loadAppShortcutsAvailability();

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
                  // Scrollable so large text scales never push the CTA off-screen; the
                  // ConstrainedBox+IntrinsicHeight pair keeps the centered Spacer layout
                  // when content is shorter than the viewport (ux-contract §16).
                  child: LayoutBuilder(
                    builder: (context, constraints) => SingleChildScrollView(
                      child: ConstrainedBox(
                        constraints: BoxConstraints(minHeight: constraints.maxHeight),
                        child: IntrinsicHeight(
                          child: Column(
                            children: [
                              const Spacer(flex: 3),
                              ScaleTransition(
                                scale: _scaleAnimation,
                                child: Container(
                                  width: 72,
                                  height: 72,
                                  decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
                                  child: Icon(Icons.check_rounded, color: OmiColors.textPrimary, size: 36),
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
                              if (_siriHintVersionSupported && _appShortcutsAvailable) ...[
                                const SizedBox(height: OmiSpacing.md),
                                Text(
                                  context.l10n.siriShortcutsSetupHint('Ask Omi', 'Question for Omi'),
                                  key: const Key('onboarding_siri_hint'),
                                  textAlign: TextAlign.center,
                                  style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                                ),
                              ],
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
                    ),
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
