import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The body of a first-run step (v2): content from the top of the page under the progress bar,
/// left-aligned by default, and the step's buttons pinned to the bottom.
///
/// [content] scrolls when it does not fit (large text, small phones); [footer] (the step's
/// buttons) stays visible under it. The bottom system inset is reserved once, through [SafeArea].
///
/// ```dart
/// OnboardingStep(card: OnboardingCard(content: [...], footer: [OmiButton(...)]))
/// ```
class OnboardingCard extends StatelessWidget {
  const OnboardingCard({
    super.key,
    required this.content,
    this.footer = const [],
    this.padding = const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xs),
    this.crossAxisAlignment = CrossAxisAlignment.start,
  });

  /// v2 insets running text 4pt further than the cards, fields and buttons at the page edge
  /// (text at 20pt, controls at 16pt). [OnboardingHeader] applies it; wrap other text with it.
  static const EdgeInsets textInset = EdgeInsets.symmetric(horizontal: OmiSpacing.xxs);

  final List<Widget> content;
  final List<Widget> footer;
  final EdgeInsets padding;
  final CrossAxisAlignment crossAxisAlignment;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: padding,
      child: SafeArea(
        top: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
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

/// A first-run step's heading (v2): the title in [OmiType.display] and an optional subtitle, inset
/// by [OnboardingCard.textInset].
class OnboardingHeader extends StatelessWidget {
  const OnboardingHeader({super.key, required this.title, this.subtitle});

  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: OnboardingCard.textInset,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Semantics(header: true, child: Text(title, style: OmiType.display)),
          if (subtitle != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(subtitle!, style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.35)),
          ],
        ],
      ),
    );
  }
}

/// A first-run step: the page under the back button and progress bar, filled by [card].
class OnboardingStep extends StatelessWidget {
  const OnboardingStep({super.key, required this.card});

  final Widget card;

  @override
  Widget build(BuildContext context) {
    // Keep clear of the progress bar and back button drawn over the top of the step.
    return Padding(
      padding: EdgeInsets.only(top: MediaQuery.paddingOf(context).top + 56),
      child: card,
    );
  }
}
