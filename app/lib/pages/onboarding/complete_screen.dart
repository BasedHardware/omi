import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';

import 'package:omi/utils/l10n_extensions.dart';

class OnboardingCompleteScreen extends StatefulWidget {
  final VoidCallback onComplete;

  const OnboardingCompleteScreen({super.key, required this.onComplete});

  @override
  State<OnboardingCompleteScreen> createState() => _OnboardingCompleteScreenState();
}

class _OnboardingCompleteScreenState extends State<OnboardingCompleteScreen> with SingleTickerProviderStateMixin {
  // v2 entrance: content rises 12pt and fades in (a plain fade under Reduce Motion).
  late final AnimationController _entrance =
      AnimationController(duration: const Duration(milliseconds: 620), vsync: this);
  late final Animation<double> _fade = CurvedAnimation(parent: _entrance, curve: OmiMotion.springCurve);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) {
        _entrance.value = 1;
      } else {
        _entrance.forward();
      }
    });
  }

  @override
  void dispose() {
    _entrance.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final name = SharedPreferencesUtil().givenName.trim();
    return ColoredBox(
      color: OmiColors.surface0,
      child: LayoutBuilder(
        builder: (context, constraints) {
          // Rev 3 (any device): the Omi mark turning in its halo, not a pendant; the title starts
          // under it and the button stays at the bottom.
          final hero = (constraints.maxHeight * 0.34).clamp(180.0, 300.0);
          final textTop = (hero - MediaQuery.paddingOf(context).top + OmiSpacing.lg).clamp(0.0, constraints.maxHeight);
          return Stack(
            fit: StackFit.expand,
            children: [
              Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  height: hero,
                  child: const Center(child: OmiRingLogo(size: 72, mode: OmiRingMode.orbit, loops: 1)),
                ),
              ),
              Positioned.fill(
                child: SafeArea(
                  child: Padding(
                    // The step layout's insets: Start using Omi sits exactly where Continue does on
                    // every other step (16pt sides, 8pt above the bottom safe area).
                    padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
                    child: AnimatedBuilder(
                      animation: _fade,
                      builder: (context, child) => Opacity(
                        opacity: _fade.value,
                        child: Transform.translate(offset: Offset(0, 12 * (1 - _fade.value)), child: child),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          SizedBox(height: textTop),
                          Expanded(
                            child: SingleChildScrollView(
                              padding: OnboardingCard.textInset,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Semantics(
                                    header: true,
                                    child: Text(
                                      name.isEmpty
                                          ? context.l10n.onboardingYoureAllSet
                                          : context.l10n.onboardingAllSetName(name),
                                      style: OmiType.serifDisplay,
                                    ),
                                  ),
                                  const SizedBox(height: OmiSpacing.lg),
                                  // v2: three things to know, a label and one line each.
                                  _Tip(
                                      label: context.l10n.completeListeningTitle,
                                      text: context.l10n.completeListeningBody),
                                  _Tip(label: context.l10n.today, text: context.l10n.completeHomeBody),
                                  _Tip(label: context.l10n.completeAskTitle, text: context.l10n.completeAskAnyBody),
                                  _Tip(label: context.l10n.devices, text: context.l10n.completeDevicesBody),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: OmiSpacing.md),
                          OmiButton(
                            key: const Key('onboarding_complete_start'),
                            label: context.l10n.startUsingOmi,
                            expand: true,
                            onPressed: () {
                              OmiHaptics.success();
                              widget.onComplete();
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Tip extends StatelessWidget {
  const _Tip({required this.label, required this.text});

  final String label;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: OmiSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 96, child: Text(label, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w700))),
          Expanded(
              child:
                  OmiBalancedText(text, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.35))),
        ],
      ),
    );
  }
}
