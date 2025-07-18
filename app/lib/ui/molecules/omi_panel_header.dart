import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/ui/atoms/omi_badge.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Generic header used inside side-panels, drawers, bottom-sheets, etc.
///
/// Layout:  [neutral icon-bubble]  [title]  (optional badge)  .............  (optional close button)
/// – Re-uses atom components so visual language is consistent with [OmiSectionHeader].
class OmiPanelHeader extends StatelessWidget {
  /// Leading icon for the panel (e.g. `FontAwesomeIcons.fileLines`).
  final IconData icon;

  /// Panel title.
  final String title;

  /// Optional grey badge shown next to the title.
  final String? badgeLabel;

  /// Called when the trailing close button is pressed. If `null`, close button is hidden.
  final VoidCallback? onClose;

  /// Alignment spacing between widgets.
  final double spacing;

  const OmiPanelHeader({
    super.key,
    required this.icon,
    required this.title,
    this.badgeLabel,
    this.onClose,
    this.spacing = 12,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
        border: Border(
          bottom: BorderSide(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          // Leading icon bubble – neutral style, non-interactive.
          OmiIconButton(
            icon: icon,
            style: OmiIconButtonStyle.neutral,
            size: 28,
            iconSize: 14,
            borderRadius: 8,
            onPressed: null,
          ),
          SizedBox(width: spacing),

          // Title.
          Text(
            title,
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),

          // Optional badge.
          if (badgeLabel != null) ...[
            SizedBox(width: spacing),
            OmiBadge(
              label: badgeLabel!,
              color: ResponsiveHelper.textTertiary,
              fontSize: 12,
              borderRadius: 12,
              backgroundColor: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
            ),
          ],

          // Spacer + optional close button.
          const Spacer(),
          if (onClose != null)
            OmiIconButton(
              icon: FontAwesomeIcons.xmark,
              style: OmiIconButtonStyle.outline,
              borderOpacity: 0.1,
              size: 28,
              iconSize: 12,
              borderRadius: 8,
              onPressed: onClose,
            ),
        ],
      ),
    );
  }
}
