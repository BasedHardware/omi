import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/env_flags.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';
import 'package:nooto_v2/providers/auth_provider.dart';
import 'package:nooto_v2/services/auth_service.dart';
import 'package:nooto_v2/theme/app_theme.dart';

class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({super.key});

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _signInGoogle() async {
    if (!kEnableFirebaseAuth) {
      context.read<AuthChangeProvider>().devSignIn();
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await AuthService.instance.signInWithGoogle();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _signInApple() async {
    if (!kEnableFirebaseAuth) {
      context.read<AuthChangeProvider>().devSignIn();
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await AuthService.instance.signInWithApple();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    return Scaffold(
      backgroundColor: const Color(0xFF08080A),
      body: SafeArea(
        child: Stack(
          children: [
            // Soft brand glow
            Positioned.fill(
              child: IgnorePointer(
                child: Container(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      center: const Alignment(0, -0.2),
                      radius: 0.9,
                      colors: [
                        AppColors.brandPrimary.withValues(alpha: 0.10),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(28, 60, 28, 28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Spacer(),
                  const _OrbHalo(),
                  const SizedBox(height: 36),
                  RichText(
                    text: TextSpan(
                      style: const TextStyle(fontSize: 30, height: 1.18, color: AppColors.textPrimary, fontWeight: FontWeight.w600),
                      children: [
                        TextSpan(text: l.welcomeTaglinePrefix),
                        TextSpan(
                          text: l.welcomeTaglineEmphasis,
                          style: brandSerif(fontSize: 30, color: AppColors.brandLight, height: 1.18),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  RichText(
                    text: TextSpan(
                      style: const TextStyle(fontSize: 17, color: AppColors.textTertiary, height: 1.4),
                      children: [
                        const TextSpan(text: 'Welcome to '),
                        TextSpan(
                          text: l.appName,
                          style: brandSerif(fontSize: 17, color: AppColors.textPrimary),
                        ),
                        const TextSpan(text: '.'),
                      ],
                    ),
                  ),
                  const Spacer(),
                  if (_error != null) ...[
                    Text(_error!, style: const TextStyle(color: AppColors.errorColor, fontSize: 13)),
                    const SizedBox(height: 12),
                  ],
                  if (Platform.isIOS || Platform.isMacOS)
                    _AuthButton(
                      label: l.welcomeContinueWithApple,
                      icon: Icons.apple,
                      onTap: _busy ? null : _signInApple,
                      busy: _busy,
                      style: _AuthButtonStyle.outline,
                    ),
                  if (Platform.isIOS || Platform.isMacOS) const SizedBox(height: 12),
                  _AuthButton(
                    label: l.welcomeContinueWithGoogle,
                    iconAssetEmoji: 'G',
                    onTap: _busy ? null : _signInGoogle,
                    busy: _busy,
                    style: _AuthButtonStyle.solid,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    l.welcomeAgreeFooter,
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 12, color: AppColors.textQuaternary, height: 1.4),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

enum _AuthButtonStyle { solid, outline }

class _AuthButton extends StatelessWidget {
  final String label;
  final IconData? icon;
  final String? iconAssetEmoji;
  final VoidCallback? onTap;
  final bool busy;
  final _AuthButtonStyle style;
  const _AuthButton({
    required this.label,
    this.icon,
    this.iconAssetEmoji,
    required this.onTap,
    required this.busy,
    required this.style,
  });

  @override
  Widget build(BuildContext context) {
    final isOutline = style == _AuthButtonStyle.outline;
    return SizedBox(
      height: 52,
      width: double.infinity,
      child: Material(
        color: isOutline ? Colors.white.withValues(alpha: 0.04) : Colors.white,
        borderRadius: BorderRadius.circular(AppStyles.radiusPill),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppStyles.radiusPill),
          onTap: onTap,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppStyles.radiusPill),
              border: isOutline ? Border.all(color: Colors.white.withValues(alpha: 0.18)) : null,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (icon != null) Icon(icon, color: isOutline ? Colors.white : Colors.black, size: 22),
                if (iconAssetEmoji != null)
                  Container(
                    width: 22,
                    height: 22,
                    alignment: Alignment.center,
                    decoration: const BoxDecoration(shape: BoxShape.circle, color: Color(0xFF4285F4)),
                    child: Text(iconAssetEmoji!,
                        style: const TextStyle(fontWeight: FontWeight.w700, color: Colors.white, fontSize: 13)),
                  ),
                const SizedBox(width: 10),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: isOutline ? Colors.white : Colors.black,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _OrbHalo extends StatefulWidget {
  const _OrbHalo();

  @override
  State<_OrbHalo> createState() => _OrbHaloState();
}

class _OrbHaloState extends State<_OrbHalo> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (context, _) {
        final t = _ctrl.value;
        return Center(
          child: Container(
            width: 130,
            height: 130,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [
                  Colors.white.withValues(alpha: 0.65 - 0.10 * t),
                  AppColors.brandLight.withValues(alpha: 0.45 - 0.10 * t),
                  AppColors.brandPrimary.withValues(alpha: 0.25),
                  Colors.transparent,
                ],
                stops: const [0.0, 0.45, 0.75, 1.0],
              ),
            ),
          ),
        );
      },
    );
  }
}
