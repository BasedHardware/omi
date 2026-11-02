import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The end of a day group on Home when the server folded noise clips away: one quiet line,
/// aligned with the day header, that reveals them in place and folds them back.
class NoiseFoldLine extends StatelessWidget {
  const NoiseFoldLine({super.key, required this.count, required this.revealed, required this.onTap});

  final int count;
  final bool revealed;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final summary = l10n.homeNoiseFoldHidden(count);
    final action = revealed ? l10n.homeNoiseFoldHide(count) : l10n.homeNoiseFoldShow;
    final quiet = OmiType.footnote.copyWith(color: OmiColors.textTertiary);
    return Semantics(
      button: true,
      label: revealed ? action : '$summary, $action',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.mdAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 16, 0),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: Text.rich(
                TextSpan(children: [
                  TextSpan(text: revealed ? '' : '$summary · '),
                  TextSpan(
                    text: action,
                    style: quiet.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
                  ),
                ]),
                style: quiet,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
