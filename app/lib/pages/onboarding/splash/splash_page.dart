import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/omi_device_glow.dart';

class OnboardingSplashPage extends StatefulWidget {
  final VoidCallback goNext;

  const OnboardingSplashPage({super.key, required this.goNext});

  @override
  State<OnboardingSplashPage> createState() => _OnboardingSplashPageState();
}

class _OnboardingSplashPageState extends State<OnboardingSplashPage> with TickerProviderStateMixin {
  // Plays once on entry: staggers the image, wordmark, tagline, and button in.
  late final AnimationController _entrance;
  // Plays once on "Get Started": the device shrinks slightly (no glow —
  // the sign-in page grows it back and glows in, so the two hand off
  // without the glow resetting mid-crossfade).
  late final AnimationController _exit;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(duration: const Duration(milliseconds: 1100), vsync: this)..forward();
    _exit = AnimationController(duration: const Duration(milliseconds: 500), vsync: this);
  }

  @override
  void dispose() {
    _entrance.dispose();
    _exit.dispose();
    super.dispose();
  }

  Animation<double> _stagger(double start, double end) {
    return CurvedAnimation(parent: _entrance, curve: Interval(start, end, curve: Curves.easeOutCubic));
  }

  Widget _reveal(Animation<double> animation, {double dy = 18, required Widget child}) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return Opacity(
          opacity: animation.value,
          child: Transform.translate(offset: Offset(0, dy * (1 - animation.value)), child: child),
        );
      },
      child: child,
    );
  }

  Future<void> _handleGetStarted() async {
    await _exit.forward();
    if (mounted) widget.goNext();
  }

  @override
  Widget build(BuildContext context) {
    final imageReveal = _stagger(0.0, 0.55);
    final titleReveal = _stagger(0.35, 0.75);
    final taglineReveal = _stagger(0.45, 0.85);
    final buttonReveal = _stagger(0.6, 1.0);

    return Container(
      width: double.infinity,
      height: double.infinity,
      color: Colors.black,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            children: [
              const Spacer(flex: 2),
              _reveal(
                imageReveal,
                dy: 24,
                child: SizedBox(
                  width: 320,
                  height: 320,
                  child: AnimatedBuilder(
                    animation: _exit,
                    builder: (context, _) {
                      // No glow here — the sign-in page owns growing the
                      // glow in, so the handoff doesn't reset mid-crossfade.
                      final scaleT = Curves.easeOut.transform(_exit.value);
                      return Transform.scale(scale: 1.0 - 0.15 * scaleT, child: const OmiDeviceGlow(glowIntensity: 0));
                    },
                  ),
                ),
              ),
              const SizedBox(height: 32),
              _reveal(
                titleReveal,
                child: const Text(
                  'Omi',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 40,
                    fontWeight: FontWeight.bold,
                    fontFamily: 'Manrope',
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 8),
              _reveal(
                taglineReveal,
                child: Text(
                  context.l10n.onboardingSplashTagline,
                  style: const TextStyle(color: Colors.white70, fontSize: 18, fontFamily: 'Manrope'),
                  textAlign: TextAlign.center,
                ),
              ),
              const Spacer(flex: 4),
              _reveal(
                buttonReveal,
                child: SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: ElevatedButton(
                    onPressed: _handleGetStarted,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                      elevation: 0,
                    ),
                    child: Text(
                      context.l10n.getStarted,
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
