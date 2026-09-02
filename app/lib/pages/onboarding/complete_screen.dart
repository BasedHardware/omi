import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/omi_device_glow.dart';
import 'package:omi/widgets/onboarding_page_transition.dart';

class OnboardingCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;

  const OnboardingCompleteScreen({super.key, required this.onComplete});

  @override
  State<OnboardingCompleteScreen> createState() => _OnboardingCompleteScreenState();
}

class _OnboardingCompleteScreenState extends State<OnboardingCompleteScreen> with SingleTickerProviderStateMixin {
  late final AnimationController _fadeController;
  late final Animation<double> _fadeAnimation;
  bool _exiting = false;

  @override
  void initState() {
    super.initState();
    // Page transition owns the entrance fade. Start fully visible so we do
    // not stack a second delayed fade on top of the incoming step.
    _fadeController = AnimationController(
      duration: kOnboardingPageFadeDuration,
      vsync: this,
      value: 1,
    );
    _fadeAnimation = CurvedAnimation(parent: _fadeController, curve: Curves.easeOut);
  }

  @override
  void dispose() {
    _fadeController.dispose();
    super.dispose();
  }

  Future<void> _handleStartUsingOmi() async {
    if (_exiting) return;
    setState(() => _exiting = true);
    await _fadeController.reverse();
    if (mounted) widget.onComplete();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Column(
              children: [
                const Spacer(flex: 2),
                const SizedBox(
                  width: 180,
                  height: 180,
                  child: OverflowBox(
                    maxWidth: 460,
                    maxHeight: 460,
                    child: OmiDeviceGlow(imageSize: 180, glowIntensity: 1),
                  ),
                ),
                const SizedBox(height: 28),
                Text(
                  context.l10n.youreAllSet,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    fontWeight: FontWeight.bold,
                    height: 1.2,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),
                const Spacer(flex: 3),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _exiting ? null : _handleStartUsingOmi,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      disabledBackgroundColor: Colors.white,
                      disabledForegroundColor: Colors.black,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.startUsingOmi,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        fontFamily: 'Manrope',
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 32),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
