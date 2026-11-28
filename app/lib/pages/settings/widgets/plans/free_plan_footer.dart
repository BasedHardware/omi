// The free Plans sheet's purchase footer: error, charge line, Upgrade, renewal terms and Terms/Privacy.
// The sheet resolves the offer (planForCheckout) and runs checkout; this only lays the footer out.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/ui.dart';

class FreePlanFooter extends StatelessWidget {
  const FreePlanFooter({
    super.key,
    this.contentKey,
    required this.error,
    required this.chargeLine,
    required this.renewalTerms,
    required this.upgrade,
    required this.locked,
    required this.pinned,
  });

  /// On the content column, which has the same width pinned or inline, so the sheet can measure it.
  final Key? contentKey;
  final String? error;

  /// The charge line, Upgrade and renewal terms show together, or not at all (no resolved offer).
  final String? chargeLine;
  final String? renewalTerms;
  final Widget? upgrade;

  /// A checkout is pending: the links ignore taps, like the plan cards.
  final bool locked;

  /// Pinned under the list: side padding and the bottom safe area. Inline it sits in the list's own padding.
  final bool pinned;

  @override
  Widget build(BuildContext context) {
    final content = Column(
      key: contentKey,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (error != null) ...[
          Text(
            error!,
            key: const ValueKey('plans_sheet_purchase_error'),
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.danger),
          ),
          const SizedBox(height: OmiSpacing.sm),
        ],
        if (chargeLine != null && upgrade != null) ...[
          Text(
            chargeLine!,
            key: const ValueKey('plans_sheet_charge_line'),
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: OmiSpacing.sm),
          upgrade!,
          if (renewalTerms != null) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(
              renewalTerms!,
              key: const ValueKey('plans_sheet_renewal_terms'),
              textAlign: TextAlign.center,
              style: OmiType.caption.copyWith(color: OmiColors.textTertiary),
            ),
          ],
        ],
        IgnorePointer(
          ignoring: locked,
          child: OmiLegalLinks(
            termsKey: const ValueKey('plans_sheet_terms'),
            privacyKey: const ValueKey('plans_sheet_privacy'),
            onTerms: () => context.read<AuthenticationProvider>().openTermsOfService(),
            onPrivacy: () => context.read<AuthenticationProvider>().openPrivacyPolicy(),
          ),
        ),
      ],
    );
    final keyed = KeyedSubtree(key: const ValueKey('plans_sheet_free_footer'), child: content);
    if (!pinned) return keyed;
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.only(bottom: OmiSpacing.xs),
      child: Padding(padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.sm, OmiSpacing.xl, 0), child: keyed),
    );
  }
}
