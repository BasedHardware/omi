// Dev-only visual mocks of the onboarding steps for lib/dev/onboarding_preview_main.dart.
//
// These mirror the real production screens' copy and layout (see
// lib/pages/onboarding/*) closely enough to review flow, transitions, and
// graphics — but they hold their own local state instead of the real
// providers/backend/Firebase, so the whole flow runs hermetically on
// `flutter run -d chrome`. Nothing here is wired into the production app.

import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/widgets/omi_device_glow.dart';

const _kManrope = 'Manrope';

/// Backdrop behind a bottom black "drawer" card — the layout every real
/// collector step (name, language, consent, ...) uses. Pass [accentIcon] for
/// a generated backdrop (a large, softly pulsing watermark icon), or
/// [background] to use a real photo instead — exactly one of the two.
class PreviewDrawerScaffold extends StatefulWidget {
  final IconData? accentIcon;
  final AssetGenImage? background;
  final Widget child;
  final EdgeInsetsGeometry padding;

  const PreviewDrawerScaffold({
    super.key,
    this.accentIcon,
    this.background,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(32, 26, 32, 24),
  }) : assert(
          (accentIcon == null) != (background == null),
          'Pass exactly one of accentIcon or background',
        );

  @override
  State<PreviewDrawerScaffold> createState() => _PreviewDrawerScaffoldState();
}

class _PreviewDrawerScaffoldState extends State<PreviewDrawerScaffold> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(duration: const Duration(seconds: 4), vsync: this);
    if (widget.accentIcon != null) _pulse.repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  Widget _buildBackdrop() {
    final background = widget.background;
    if (background != null) {
      return Ink(
        decoration: BoxDecoration(
          image: DecorationImage(image: AssetImage(background.path), fit: BoxFit.cover),
        ),
        child: Container(color: Colors.black.withValues(alpha: 0.35)),
      );
    }

    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        gradient: RadialGradient(center: Alignment(0.2, -0.6), radius: 1.3, colors: [Color(0xFF1B1B1B), Colors.black]),
      ),
      child: Center(
        child: AnimatedBuilder(
          animation: _pulse,
          builder: (context, _) {
            final t = Curves.easeInOut.transform(_pulse.value);
            return Stack(
              alignment: Alignment.center,
              children: [
                Container(
                  width: 220 + 40 * t,
                  height: 220 + 40 * t,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [Colors.white.withValues(alpha: 0.10 + 0.05 * t), Colors.transparent],
                    ),
                  ),
                ),
                Icon(widget.accentIcon, size: 96, color: Colors.white.withValues(alpha: 0.22 + 0.08 * t)),
              ],
            );
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(child: _buildBackdrop()),
        Container(
          width: double.infinity,
          padding: widget.padding,
          decoration: const BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.only(topLeft: Radius.circular(40), topRight: Radius.circular(40)),
          ),
          child: SafeArea(top: false, child: widget.child),
        ),
      ],
    );
  }
}

/// Full-black centered layout — what the splash/speech-profile/complete
/// steps use instead of the drawer-over-photo pattern.
class PreviewCenteredScaffold extends StatelessWidget {
  final Widget child;

  const PreviewCenteredScaffold({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: Colors.black,
      child: SafeArea(child: Padding(padding: const EdgeInsets.symmetric(horizontal: 32), child: child)),
    );
  }
}

class PreviewContinueButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? trailingIcon;

  const PreviewContinueButton({super.key, required this.label, required this.onPressed, this.trailingIcon});

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: enabled ? Colors.white : Colors.grey[800],
          foregroundColor: enabled ? Colors.black : Colors.grey[600],
          disabledBackgroundColor: Colors.grey[800],
          disabledForegroundColor: Colors.grey[600],
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
          elevation: 0,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(label, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: _kManrope)),
            if (trailingIcon != null) ...[const SizedBox(width: 8), Icon(trailingIcon, size: 20)],
          ],
        ),
      ),
    );
  }
}

/// A glowing icon badge shared by the graphic-forward steps, so the flow
/// reads as one visual language instead of a different accent per screen.
// ---------------------------------------------------------------------------
// Sign in
// ---------------------------------------------------------------------------

class PreviewSignInStep extends StatelessWidget {
  final VoidCallback goNext;

  const PreviewSignInStep({super.key, required this.goNext});

  @override
  Widget build(BuildContext context) {
    return PreviewDrawerScaffold(
      background: Assets.images.onboardingBg2,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Speak. Transcribe. Summarize.',
            style: TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold, fontFamily: _kManrope),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 56,
            child: ElevatedButton(
              onPressed: goNext,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  FaIcon(FontAwesomeIcons.apple, size: 24),
                  SizedBox(width: 8),
                  Text('Sign in with Apple', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            height: 56,
            child: ElevatedButton(
              onPressed: goNext,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  FaIcon(FontAwesomeIcons.google, size: 20),
                  SizedBox(width: 8),
                  Text('Sign in with Google', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'By continuing, you agree to our Privacy Policy & Terms of Use.',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 11, fontFamily: _kManrope),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Data privacy
// ---------------------------------------------------------------------------

class PreviewConsentStep extends StatelessWidget {
  final VoidCallback goNext;

  const PreviewConsentStep({super.key, required this.goNext});

  @override
  Widget build(BuildContext context) {
    return PreviewDrawerScaffold(
      accentIcon: Icons.privacy_tip_rounded,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Your data & privacy',
            style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold, fontFamily: _kManrope),
          ),
          const SizedBox(height: 16),
          const Text(
            'Omi listens to your conversations to build your memory and help you get things done. '
            'You control what gets recorded, and can delete anything at any time.',
            style: TextStyle(color: Colors.white, fontSize: 15, height: 1.5, fontFamily: _kManrope),
          ),
          const SizedBox(height: 24),
          PreviewContinueButton(label: 'Agree & Continue', onPressed: goNext),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Name
// ---------------------------------------------------------------------------

class PreviewNameStep extends StatefulWidget {
  final VoidCallback goNext;

  const PreviewNameStep({super.key, required this.goNext});

  @override
  State<PreviewNameStep> createState() => _PreviewNameStepState();
}

class _PreviewNameStepState extends State<PreviewNameStep> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PreviewDrawerScaffold(
      background: Assets.images.onboardingBg4,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final canContinue = _controller.text.trim().isNotEmpty;
          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                "What's your name?",
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  fontFamily: _kManrope,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 28),
              Container(
                decoration: BoxDecoration(
                  color: Colors.grey[900],
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.grey[700]!),
                ),
                child: TextField(
                  controller: _controller,
                  style: const TextStyle(color: Colors.white, fontSize: 18, fontFamily: _kManrope),
                  textAlign: TextAlign.center,
                  decoration: InputDecoration(
                    hintText: 'Enter your name',
                    hintStyle: TextStyle(color: Colors.grey[500], fontSize: 18),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                  ),
                ),
              ),
              const SizedBox(height: 32),
              PreviewContinueButton(label: 'Continue', onPressed: canContinue ? widget.goNext : null),
            ],
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Found us
// ---------------------------------------------------------------------------

class PreviewFoundUsStep extends StatefulWidget {
  final VoidCallback goNext;

  const PreviewFoundUsStep({super.key, required this.goNext});

  @override
  State<PreviewFoundUsStep> createState() => _PreviewFoundUsStepState();
}

class _PreviewFoundUsStepState extends State<PreviewFoundUsStep> {
  String? _selected;

  static const _sources = [
    ('TikTok', FontAwesomeIcons.tiktok),
    ('YouTube', FontAwesomeIcons.youtube),
    ('Instagram', FontAwesomeIcons.instagram),
    ('Friend / word of mouth', FontAwesomeIcons.userGroup),
    ('Google', FontAwesomeIcons.google),
  ];

  @override
  Widget build(BuildContext context) {
    return PreviewDrawerScaffold(
      accentIcon: Icons.travel_explore_rounded,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'How did you find us?',
            style: TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold, fontFamily: _kManrope),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),
          ..._sources.map((source) {
            final (label, icon) = source;
            final isSelected = _selected == label;
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: GestureDetector(
                onTap: () => setState(() => _selected = isSelected ? null : label),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  decoration: BoxDecoration(
                    color: isSelected ? Colors.white : Colors.grey[900],
                    borderRadius: BorderRadius.circular(40),
                    border: Border.all(color: isSelected ? Colors.white : Colors.grey[700]!),
                  ),
                  child: Row(
                    children: [
                      FaIcon(icon, size: 18, color: isSelected ? Colors.black : Colors.white),
                      const SizedBox(width: 14),
                      Text(
                        label,
                        style: TextStyle(
                          color: isSelected ? Colors.black : Colors.white,
                          fontWeight: FontWeight.w500,
                          fontFamily: _kManrope,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          PreviewContinueButton(label: 'Continue', onPressed: _selected == null ? null : widget.goNext),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Permissions
// ---------------------------------------------------------------------------

class PreviewPermissionsStep extends StatefulWidget {
  final VoidCallback goNext;

  const PreviewPermissionsStep({super.key, required this.goNext});

  @override
  State<PreviewPermissionsStep> createState() => _PreviewPermissionsStepState();
}

class _PreviewPermissionsStepState extends State<PreviewPermissionsStep> {
  bool _location = false;
  bool _notifications = false;

  Widget _tile({required bool value, required String title, required String subtitle, required VoidCallback onTap}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.grey[700]!),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(subtitle, style: TextStyle(color: Colors.white.withValues(alpha: 0.6), fontSize: 12)),
              ],
            ),
          ),
          Checkbox(value: value, onChanged: (_) => onTap(), activeColor: Colors.white, checkColor: Colors.black),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PreviewDrawerScaffold(
      accentIcon: Icons.verified_user_rounded,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'Grant permissions',
            style: TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold, fontFamily: _kManrope),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 28),
          _tile(
            value: _location,
            title: 'Location access',
            subtitle: 'Tag memories with where they happened.',
            onTap: () => setState(() => _location = !_location),
          ),
          _tile(
            value: _notifications,
            title: 'Notifications',
            subtitle: 'Get nudged about action items and follow-ups.',
            onTap: () => setState(() => _notifications = !_notifications),
          ),
          const SizedBox(height: 8),
          PreviewContinueButton(label: 'Continue', onPressed: widget.goNext),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// You're all set
// ---------------------------------------------------------------------------

class PreviewCompleteStep extends StatefulWidget {
  final VoidCallback onComplete;

  const PreviewCompleteStep({super.key, required this.onComplete});

  @override
  State<PreviewCompleteStep> createState() => _PreviewCompleteStepState();
}

class _PreviewCompleteStepState extends State<PreviewCompleteStep> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(duration: const Duration(milliseconds: 800), vsync: this);
    Future.delayed(const Duration(milliseconds: 150), () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PreviewCenteredScaffold(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return FadeTransition(
            opacity: _controller,
            child: Column(
              children: [
                const Spacer(flex: 2),
                const OmiDeviceGlow(imageSize: 180, glowIntensity: 1),
                const SizedBox(height: 28),
                const Text(
                  'You are all set',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 30,
                    fontWeight: FontWeight.bold,
                    fontFamily: _kManrope,
                  ),
                  textAlign: TextAlign.center,
                ),
                const Spacer(flex: 3),
                PreviewContinueButton(
                  label: 'Start using Omi',
                  onPressed: widget.onComplete,
                ),
                const SizedBox(height: 16),
              ],
            ),
          );
        },
      ),
    );
  }
}
