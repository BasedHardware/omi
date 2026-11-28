// Terms of Use and Privacy Policy links for every purchase surface (trial paywall, free Plans sheet).
// Owns the 44pt targets and link semantics App Store guideline 3.1.2 asks for; callers own where the links open.
import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Terms of Use and Privacy Policy beside a purchase button (App Store 3.1.2), each a 44pt target.
class OmiLegalLinks extends StatelessWidget {
  const OmiLegalLinks({
    super.key,
    required this.onTerms,
    required this.onPrivacy,
    this.color,
    this.termsKey,
    this.privacyKey,
  });

  final VoidCallback onTerms;
  final VoidCallback onPrivacy;

  /// Defaults to [OmiColors.textTertiary] (4.5:1 or more on surface1 in light and dark); a fixed-palette page
  /// passes its own.
  final Color? color;
  final Key? termsKey;
  final Key? privacyKey;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final color = this.color ?? OmiColors.textTertiary;
    final style = OmiType.caption.copyWith(color: color);
    Widget link(Key? key, String label, VoidCallback onTap) => Semantics(
          link: true,
          child: InkWell(
            key: key,
            onTap: onTap,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
                child: Center(
                  widthFactor: 1,
                  child: Text(
                    label,
                    textAlign: TextAlign.center,
                    style: style.copyWith(decoration: TextDecoration.underline, decorationColor: color),
                  ),
                ),
              ),
            ),
          ),
        );
    return Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        link(termsKey, l10n.termsOfUse, onTerms),
        ExcludeSemantics(child: Text(' · ', style: style)),
        link(privacyKey, l10n.privacyPolicy, onPrivacy),
      ],
    );
  }
}
