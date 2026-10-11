import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// The conversation page's inks (Omi v8 `--i80`, `--i55`, `--i14`): words at 80 % of the primary
/// ink, labels in the tertiary ink (55 %), hairlines at 14 %.
abstract final class ConversationDetailInk {
  static Color get words => OmiColors.textPrimary.withValues(alpha: 0.8);
  static Color get label => OmiColors.textTertiary;
  static Color get hairline => OmiColors.textPrimary.withValues(alpha: 0.14);
}

/// One fact or control on the conversation page (Omi v8 `.chipm`): a 34 pt capsule with a hairline
/// edge, a glyph and one line of text. Used under the title (when, folder, people, visibility) and
/// at the top of the transcript ("Transcript · 14 min · 2 speakers").
class ConversationDetailChip extends StatelessWidget {
  const ConversationDetailChip({
    super.key,
    required this.icon,
    required this.label,
    this.color,
    this.startPadding = 13,
  });

  final Widget icon;
  final String label;

  /// The text and glyph ink; [ConversationDetailInk.words] when null.
  final Color? color;

  /// Space before the glyph; less for a row of avatars, which fills its circle.
  final double startPadding;

  @override
  Widget build(BuildContext context) {
    final ink = color ?? ConversationDetailInk.words;
    return Container(
      constraints: const BoxConstraints(minHeight: 34),
      padding: EdgeInsetsDirectional.fromSTEB(startPadding, 6, 13, 6),
      decoration: BoxDecoration(
        borderRadius: OmiRadius.pillAll,
        border: Border.all(color: ConversationDetailInk.hairline),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconTheme.merge(data: IconThemeData(color: ink, size: 15), child: icon),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              label,
              style: OmiType.subhead.copyWith(color: ink, height: 1.2),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
