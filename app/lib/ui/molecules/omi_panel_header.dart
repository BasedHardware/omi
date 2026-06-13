import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/atoms/omi_badge.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Generic header used inside side-panels, drawers, bottom-sheets, etc.
///
/// Layout:  [neutral icon-bubble]  [title]  (optional badge)  .............  (optional close button)
/// – Re-uses atom components so visual language is consistent with [OmiSectionHeader].
class OmiPanelHeader extends StatelessWidget {
  /// Leading icon for the panel (e.g. `FontAwesomeIcons.fileLines`).
  final FaIconData icon;

  /// Panel title.
  final String title;

  /// Optional grey badge shown next to the title.
  final String? badgeLabel;

  /// Called when the trailing close button is pressed. If `null`, close button is hidden.
  final VoidCallback? onClose;

  final Widget? action;

  /// Alignment spacing between widgets.
  final double spacing;

  const OmiPanelHeader({
    super.key,
    required this.icon,
    required this.title,
    this.badgeLabel,
    this.onClose,
    this.action,
    this.spacing = 12,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
        border: Border(bottom: BorderSide(color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3), width: 1)),
      ),
      child: Row(
        children: [
          // Leading icon bubble – neutral style, non-interactive.
          Container(
            height: 28,
            width: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(8),
            ),
            child: FaIcon(icon, color: ResponsiveHelper.textSecondary, size: 14),
          ),
          SizedBox(width: spacing),

          // Title.
          Text(
            title,
            style: const TextStyle(color: ResponsiveHelper.textPrimary, fontSize: 20, fontWeight: FontWeight.w600),
          ),

          // Optional badge.
          if (badgeLabel != null) ...[
            SizedBox(width: spacing),
            OmiBadge(
              label: badgeLabel!,
              color: ResponsiveHelper.textTertiary,
              fontSize: 12,
              borderRadius: 12,
              backgroundColor: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
            ),
          ],

          // Spacer + optional close button.
          const Spacer(),
          if (action != null) ...[action!, SizedBox(width: spacing)],
          if (onClose != null)
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: onClose,
                borderRadius: BorderRadius.circular(8),
                child: Container(
                  height: 28,
                  width: 28,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: ResponsiveHelper.textSecondary.withValues(alpha: 0.1), width: 1),
                  ),
                  child: FaIcon(FontAwesomeIcons.xmark, color: ResponsiveHelper.textSecondary, size: 12),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
