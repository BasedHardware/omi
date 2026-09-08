import 'package:flutter/material.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One row of the Profile settings list: icon, title (optionally with a BETA
/// tag and a subtitle), an optional value chip, and a chevron.
///
/// The title and its tag sit in a `Wrap` so the title wraps by word instead of
/// pushing the tag off the row, and the chip is capped to [chipMaxWidthFraction] of the
/// row so a long value cannot squeeze the title into mid-word breaks. Both
/// overflowed with enlarged or bold system text (issue #12898: "Transcribe
/// Later" + BETA + "Off" painted the debug overflow stripes).
class ProfileSettingsTile extends StatelessWidget {
  const ProfileSettingsTile({
    super.key,
    required this.title,
    required this.icon,
    required this.onTap,
    this.subtitle,
    this.chipValue,
    this.showSubtitle = true,
    this.showBetaTag = false,
    this.showChevron = true,
    this.useInkWell = false,
  });

  final String title;
  final Widget icon;
  final VoidCallback? onTap;
  final String? subtitle;
  final String? chipValue;
  final bool showSubtitle;
  final bool showBetaTag;
  final bool showChevron;

  /// Ripple feedback instead of a plain tap target (used by rows that open a
  /// sheet rather than push a page).
  final bool useInkWell;

  /// Largest share of the width left for title and chip (after the icon, the
  /// chevron, and their gaps) that the chip may take before its text is
  /// ellipsized; the title always keeps the rest.
  static const double chipMaxWidthFraction = 0.6;

  static const double _iconWidth = 24;
  static const double _iconGap = 16;
  static const double _chipGap = 8;
  static const double _chevronWidth = 20;
  static const double _chevronGap = 8;

  /// Width the chip may take in a row whose content area is [rowWidth] wide.
  static double chipMaxWidth(double rowWidth, {required bool showChevron}) {
    final fixed = _iconWidth + _iconGap + _chipGap + (showChevron ? _chevronGap + _chevronWidth : 0);
    final shared = (rowWidth - fixed).clamp(0.0, double.infinity);
    return shared * chipMaxWidthFraction;
  }

  static const Color _tileColor = Color(0xFF1C1C1E);
  static const Color _chipColor = Color(0xFF2A2A2E);
  static const Color _chevronColor = Color(0xFF3C3C43);

  @override
  Widget build(BuildContext context) {
    final row = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      child: LayoutBuilder(
        builder: (context, constraints) {
          return Row(
            children: [
              SizedBox(width: _iconWidth, height: 24, child: icon),
              const SizedBox(width: _iconGap),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Wrap, not Row: the title gets the full column width and
                    // wraps by word, while the tag sits beside it when there is
                    // room and drops below it otherwise. A Row with a Flexible
                    // title breaks the title per character once the tag steals
                    // width, and a rigid Row overflows to the right (#12898).
                    Wrap(
                      crossAxisAlignment: WrapCrossAlignment.center,
                      spacing: 8,
                      runSpacing: 4,
                      children: [
                        Text(
                          title,
                          style: const TextStyle(color: Colors.white, fontSize: 17, fontWeight: FontWeight.w400),
                        ),
                        if (showBetaTag)
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                            decoration: BoxDecoration(
                              color: Colors.orange.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              context.l10n.beta,
                              style: const TextStyle(
                                color: Colors.orange,
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                      ],
                    ),
                    if (showSubtitle && subtitle != null && chipValue == null) ...[
                      const SizedBox(height: 2),
                      Text(
                        subtitle!,
                        style: const TextStyle(color: Color(0xFF8E8E93), fontSize: 12, fontWeight: FontWeight.w400),
                      ),
                    ],
                  ],
                ),
              ),
              if (chipValue != null) ...[
                const SizedBox(width: _chipGap),
                ConstrainedBox(
                  constraints: BoxConstraints(
                    maxWidth: chipMaxWidth(constraints.maxWidth, showChevron: showChevron),
                  ),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(color: _chipColor, borderRadius: BorderRadius.circular(100)),
                    child: Text(
                      chipValue!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
              ],
              if (showChevron) ...[
                const SizedBox(width: _chevronGap),
                const Icon(Icons.chevron_right, color: _chevronColor, size: _chevronWidth),
              ],
            ],
          );
        },
      ),
    );

    if (useInkWell) {
      return InkWell(onTap: onTap, child: row);
    }
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(color: _tileColor, borderRadius: BorderRadius.circular(20)),
        child: row,
      ),
    );
  }
}
