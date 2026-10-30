import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/ui/ui.dart';

/// Space between every onboarding step's primary button and the bottom safe area: high enough to
/// sit under the thumb, the same on every step so the button never moves between steps.
const double kOnboardingButtonBottomGap = OmiSpacing.xl;

/// The bottom block of a first-run step (title, text, buttons), pinned to the bottom of the step.
/// No card: it sits straight on the onboarding surface, under the Omi pendant.
///
/// [content] scrolls when they do not fit (large text, small phones); [footer] (the step's
/// buttons) stays visible under them. The card reserves the bottom system inset once, through its
/// [SafeArea], not twice.
///
/// ```dart
/// OnboardingStep(card: OnboardingCard(content: [...], footer: [OmiButton(...)]))
/// ```
class OnboardingCard extends StatelessWidget {
  const OnboardingCard({
    super.key,
    required this.content,
    this.footer = const [],
    this.padding =
        const EdgeInsets.fromLTRB(OmiSpacing.xxl, OmiSpacing.xxl, OmiSpacing.xxl, kOnboardingButtonBottomGap),
    this.crossAxisAlignment = CrossAxisAlignment.center,
    this.reserveBottomInset = true,
  });

  final List<Widget> content;
  final List<Widget> footer;
  final EdgeInsets padding;
  final CrossAxisAlignment crossAxisAlignment;

  /// False when the footer lays out the home-indicator area itself (e.g. a fine-print line under
  /// the button that sits in the space the other steps leave below theirs).
  final bool reserveBottomInset;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      child: SafeArea(
        top: false,
        bottom: reserveBottomInset,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Flexible(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: crossAxisAlignment,
                  children: content,
                ),
              ),
            ),
            ...footer,
          ],
        ),
      ),
    );
  }
}

/// A first-run step: the pendant shows above, the [card] block sits at the bottom and grows
/// up to the full height before its content scrolls.
class OnboardingStep extends StatelessWidget {
  const OnboardingStep({super.key, required this.card});

  final Widget card;

  @override
  Widget build(BuildContext context) {
    // The top padding already includes the progress dots and back button when the wrapper draws
    // them (OnboardingStepLayout), so this only adds a small gap above a full-height card.
    return Padding(
      padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top + OmiSpacing.md),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [Flexible(child: card)],
      ),
    );
  }
}

/// How sign-in and the data & privacy step look: the Omi pendant on the light onboarding surface
/// (default), or the launch film full-screen under white type. The film is a design comparison for
/// now: `--dart-define=OMI_ONBOARDING_HERO=video`, honoured in debug and local_dev builds only.
abstract final class OnboardingHero {
  static const _flag = String.fromEnvironment('OMI_ONBOARDING_HERO');

  static bool get video => (kDebugMode || Env.profile == AppEnvironmentProfile.localDev) && _flag == 'video';

  /// Type and buttons: white over the film, the theme's own over the pendant.
  static OmiPalette get palette => video ? OmiPalette.dark : OmiColors.active;
}

/// Sign-in and data & privacy: the hero (pendant or film) above, [headline] centred in the space
/// between it and the buttons, and [buttons] pinned exactly where every other step's Continue sits
/// (24pt in, 48pt tall, ending [kOnboardingButtonBottomGap] above the safe area) with [legal] in the space below.
class OnboardingHeroStep extends StatelessWidget {
  const OnboardingHeroStep({super.key, required this.headline, required this.buttons, required this.legal});

  final Widget headline;
  final List<Widget> buttons;
  final Widget legal;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final belowButton = media.padding.bottom + kOnboardingButtonBottomGap;
    // The pendant's body ends around 40% down; the film fills the screen, so its type sits lower.
    final heroBottom = media.size.height * (OnboardingHero.video ? 0.46 : 0.42);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(height: heroBottom),
          // The headline sits low, just above the button(s).
          Expanded(
            child: Align(alignment: Alignment.bottomCenter, child: SingleChildScrollView(child: headline)),
          ),
          const SizedBox(height: OmiSpacing.xxl),
          ...buttons,
          SizedBox(
            height: belowButton,
            child: Padding(padding: const EdgeInsets.only(top: OmiSpacing.xs), child: legal),
          ),
        ],
      ),
    );
  }
}

/// The onboarding action button in the hero steps: the same 48pt pill as the other steps' Continue,
/// coloured from [OnboardingHero.palette] so it inverts over the film.
class OnboardingHeroButton extends StatelessWidget {
  const OnboardingHeroButton(
      {super.key, required this.label, required this.onPressed, this.icon, this.outlined = false});

  final String label;
  final VoidCallback onPressed;
  final Widget? icon;
  final bool outlined;

  @override
  Widget build(BuildContext context) {
    final p = OnboardingHero.palette;
    final style = OmiType.headline.copyWith(color: outlined ? p.textPrimary : p.onAccent);
    final child = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          IconTheme(data: IconThemeData(color: style.color, size: 20), child: icon!),
          const SizedBox(width: OmiSpacing.xs),
        ],
        Flexible(child: Text(label, style: style, overflow: TextOverflow.ellipsis)),
      ],
    );
    return SizedBox(
      height: 48,
      child: outlined
          ? OutlinedButton(
              onPressed: onPressed,
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: p.textPrimary.withValues(alpha: 0.4)),
                shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
              ),
              child: child,
            )
          : ElevatedButton(
              onPressed: onPressed,
              style: ElevatedButton.styleFrom(
                backgroundColor: p.accent,
                foregroundColor: p.onAccent,
                elevation: 0,
                shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
              ),
              child: child,
            ),
    );
  }
}
