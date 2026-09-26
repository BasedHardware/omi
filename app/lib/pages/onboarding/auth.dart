import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AuthComponent extends StatefulWidget {
  final VoidCallback onSignIn;

  const AuthComponent({super.key, required this.onSignIn});

  @override
  State<AuthComponent> createState() => _AuthComponentState();
}

class _AuthComponentState extends State<AuthComponent> {
  /// v2: Welcome first (Get Started), then Sign in. Back from Sign in returns to Welcome.
  bool _showSignIn = false;

  void _setSignIn(bool value) {
    OmiHaptics.selection();
    setState(() => _showSignIn = value);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthenticationProvider>(
      builder: (context, provider, child) {
        return PopScope(
          // System back and the iOS swipe on Sign in step back to Welcome, like the on-screen back.
          canPop: !_showSignIn,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop && _showSignIn) _setSignIn(false);
          },
          // Rev 3 Welcome: one memory, any device. The brand card sits above the words; on Sign in
          // it shrinks and the back button returns to Welcome.
          child: SafeArea(
            // Fills a tall screen; scrolls on a short one (iPhone SE, landscape) instead of clipping.
            child: CustomScrollView(
              slivers: [
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xs),
                  sliver: SliverFillRemaining(
                    hasScrollBody: false,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SizedBox(
                          height: OmiSize.minTap,
                          child: _showSignIn
                              ? Align(
                                  alignment: Alignment.centerLeft,
                                  child: OmiBackButton(key: const Key('auth_back'), onPressed: () => _setSignIn(false)),
                                )
                              : null,
                        ),
                        Expanded(
                          child: Center(
                            child: AnimatedContainer(
                              duration: OmiMotion.of(context).emphasized,
                              curve: OmiMotion.springCurve,
                              height: _showSignIn ? 150 : 220,
                              child: _BrandCard(compact: _showSignIn),
                            ),
                          ),
                        ),
                        AnimatedSwitcher(
                          duration: OmiMotion.of(context).standard,
                          child: _showSignIn ? _signIn(context, provider) : _welcome(context),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _welcome(BuildContext context) {
    final l10n = context.l10n;
    // Every device the app records from today (Rev 3: "the device list is real").
    final devices = [
      'Omi',
      'OmiGlass',
      if (!Platform.isAndroid) 'Apple Watch',
      'Ray-Ban Meta',
      'Plaud',
      'Bee',
      'Limitless',
      'Fieldy',
      'Friend',
      Platform.isIOS ? l10n.memoryThisIphone : l10n.memoryThisPhone,
    ];
    return Column(
      key: const ValueKey('welcome'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: OmiSpacing.lg),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Semantics(header: true, child: Text(l10n.welcomeRememberTitle, style: OmiType.serifDisplay)),
              const SizedBox(height: OmiSpacing.sm),
              Text(
                l10n.welcomeRememberSubtitle,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
              const SizedBox(height: 18),
              Wrap(
                key: const Key('welcome_devices'),
                spacing: 6,
                runSpacing: 6,
                children: [for (final name in devices) _DeviceChip(name)],
              ),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiButton(
          key: const Key('auth_get_started'),
          label: l10n.getStarted,
          expand: true,
          onPressed: () => _setSignIn(true),
        ),
        const SizedBox(height: OmiSpacing.xs),
        Semantics(
          button: true,
          label: '${l10n.alreadyHaveAccount} ${l10n.signInButton}',
          excludeSemantics: true,
          onTap: () => _setSignIn(true),
          child: GestureDetector(
            key: const Key('auth_have_account'),
            behavior: HitTestBehavior.opaque,
            onTap: () => _setSignIn(true),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: OmiSize.minTap),
              child: Center(
                child: Text.rich(
                  TextSpan(
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                    children: [
                      TextSpan(text: '${l10n.alreadyHaveAccount} '),
                      TextSpan(
                        text: l10n.signInButton,
                        style: TextStyle(color: OmiColors.textPrimary, fontWeight: FontWeight.w700),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _signIn(BuildContext context, AuthenticationProvider provider) {
    final l10n = context.l10n;
    final link = OmiType.footnote.copyWith(color: OmiColors.textPrimary, decoration: TextDecoration.underline);
    return Column(
      key: const ValueKey('sign_in'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          header: true,
          child: Text(l10n.signInToOmi, style: OmiType.title1, textAlign: TextAlign.center),
        ),
        const SizedBox(height: OmiSpacing.sm),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
          child: Text(
            l10n.signInSubtitle,
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.4),
          ),
        ),
        const SizedBox(height: OmiSpacing.xl),
        SizedBox(
          height: 20,
          child: provider.loading ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small)) : null,
        ),
        const SizedBox(height: OmiSpacing.md),
        if (Platform.isIOS || Platform.isAndroid) ...[
          OmiButton(
            key: const Key('auth_apple'),
            label: l10n.signInWithApple,
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              provider.onAppleSignIn(widget.onSignIn);
            },
          ),
          const SizedBox(height: OmiSpacing.sm),
        ],
        OmiButton.secondary(
          key: const Key('auth_google'),
          label: l10n.continueWithGoogle,
          expand: true,
          onPressed: () {
            OmiHaptics.selection();
            provider.onGoogleSignIn(widget.onSignIn);
          },
        ),
        // Local development sign-in. Only rendered for a local_dev build: community builds cannot
        // complete a real OAuth flow, because provider OAuth clients are bound to the official
        // bundle id and a community build is signed with a suffixed one. Never shown in a
        // production-family build.
        if (provider.isLocalDevProfile) ...[
          const SizedBox(height: OmiSpacing.sm),
          OmiButton.tertiary(
            label: 'Sign in (local dev)', // omi-ux-allow: hardcoded-text -- local_dev builds only, never shipped
            expand: true,
            onPressed: () {
              OmiHaptics.selection();
              provider.onLocalDevSignIn(widget.onSignIn);
            },
          ),
        ],
        const SizedBox(height: OmiSpacing.md),
        RichText(
          textAlign: TextAlign.center,
          text: TextSpan(
            style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            children: [
              TextSpan(text: l10n.byContinuingAgree),
              TextSpan(
                text: l10n.termsOfService,
                style: link,
                recognizer: TapGestureRecognizer()..onTap = provider.openTermsOfService,
              ),
              TextSpan(text: l10n.and),
              TextSpan(
                text: l10n.privacyPolicy,
                style: link,
                recognizer: TapGestureRecognizer()..onTap = provider.openPrivacyPolicy,
              ),
              const TextSpan(text: '.'),
            ],
          ),
        ),
        const SizedBox(height: OmiSpacing.xs),
      ],
    );
  }
}

/// The brand on a card (Rev 3 Welcome): the Omi mark turning once and the wordmark, no device.
class _BrandCard extends StatelessWidget {
  const _BrandCard({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    return OmiCard(
      radius: OmiRadius.cardLarge,
      child: Center(
        child: ExcludeSemantics(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              OmiRingLogo(size: compact ? 36 : 48, mode: OmiRingMode.orbit, loops: 1),
              const SizedBox(width: OmiSpacing.sm),
              Image.asset(Assets.images.logoTextWhite.path, height: compact ? 28 : 38, color: OmiColors.textPrimary),
            ],
          ),
        ),
      ),
    );
  }
}

/// One supported device, named (not a button: choosing comes after sign-in).
class _DeviceChip extends StatelessWidget {
  const _DeviceChip(this.name);

  final String name;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 30,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: OmiColors.surface1,
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: OmiColors.border, width: 0.5),
      ),
      // Centred on its own width: a Container with an alignment would stretch to the row.
      child: Center(
        widthFactor: 1,
        child:
            Text(name, style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textSecondary)),
      ),
    );
  }
}
