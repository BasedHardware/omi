import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The black bottom card every first-run step sits in, pinned to the bottom of the step.
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
    this.padding = const EdgeInsets.fromLTRB(OmiSpacing.xxl, OmiSpacing.xxl, OmiSpacing.xxl, OmiSpacing.xs),
    this.crossAxisAlignment = CrossAxisAlignment.center,
  });

  final List<Widget> content;
  final List<Widget> footer;
  final EdgeInsets padding;
  final CrossAxisAlignment crossAxisAlignment;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: const BoxDecoration(
        color: OmiColors.surface0,
        borderRadius: BorderRadius.vertical(top: Radius.circular(OmiRadius.xl)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Flexible(
              child: SingleChildScrollView(
                child:
                    Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: crossAxisAlignment, children: content),
              ),
            ),
            ...footer,
          ],
        ),
      ),
    );
  }
}

/// A first-run step: the background shows through above, the [card] sits at the bottom and grows
/// up to the full height before its content scrolls.
class OnboardingStep extends StatelessWidget {
  const OnboardingStep({super.key, required this.card});

  final Widget card;

  @override
  Widget build(BuildContext context) {
    // Keep clear of the progress dots and back button drawn over the top of the step.
    return Padding(
      padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top + 64),
      child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [Flexible(child: card)]),
    );
  }
}
