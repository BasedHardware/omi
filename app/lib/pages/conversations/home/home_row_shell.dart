import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// The one shape every Home row uses: an 8pt gap above, 16pt sides, a `surface1` card with
/// `OmiRadius.xl`, 14pt padding, a 36pt tile, a one-line title and subtitle, and an optional
/// trailing control. Conversation rows draw the same geometry themselves ([ConversationListItem]).
class HomeRowShell extends StatelessWidget {
  const HomeRowShell({
    super.key,
    required this.tile,
    required this.title,
    this.subtitle,
    this.subtitleWidget,
    this.subtitleColor,
    this.trailing,
    this.onTap,
    this.semanticsLabel,
    this.semanticsHint,
    this.border,
    this.actionTrailing = false,
  });

  final Widget tile;
  final String title;
  final String? subtitle;

  /// Replaces [subtitle] when the line is more than text (a chip, a live preview).
  final Widget? subtitleWidget;

  /// A subtitle that names a problem uses `OmiColors.warning` or `OmiColors.danger`.
  final Color? subtitleColor;
  final Widget? trailing;
  final VoidCallback? onTap;
  final String? semanticsLabel;
  final String? semanticsHint;

  /// The live row's outline; null for every other row.
  final BorderSide? border;

  /// [trailing] is its own button (Retry, play): screen readers reach it separately. Otherwise
  /// the row reads as one button with [semanticsLabel].
  final bool actionTrailing;

  /// The subtitle style of every Home row, the conversation meta line included.
  static TextStyle get subtitleStyle => OmiType.subhead.copyWith(color: OmiColors.textTertiary);

  static const double tileExtent = 36;

  /// The least height of a row's content: one tap target, the height of its tallest action.
  static const double contentExtent = kOmiMinTapTarget;

  /// The chevron a prompt card (not a Home row) ends with.
  static Widget chevron() => Icon(Icons.chevron_right_rounded, color: OmiColors.textDisabled);

  @override
  Widget build(BuildContext context) {
    final line = subtitleWidget ??
        (subtitle == null || subtitle!.isEmpty
            ? null
            : Text(
                subtitle!,
                style: subtitleColor == null ? subtitleStyle : subtitleStyle.copyWith(color: subtitleColor),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ));
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Semantics(
        button: onTap != null,
        label: semanticsLabel ?? [title, if (subtitle != null) subtitle].join(', '),
        hint: semanticsHint,
        excludeSemantics: !actionTrailing,
        child: Material(
          color: OmiColors.surface1,
          shape: RoundedRectangleBorder(borderRadius: OmiRadius.xlAll, side: border ?? BorderSide.none),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(14),
              // Every row's content is one tap target tall, so a row with an action is the same height
              // as one without.
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: contentExtent),
                child: Row(
                  children: [
                    tile,
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(title,
                              style: Theme.of(context).textTheme.titleMedium,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          if (line != null) ...[const SizedBox(height: 3), line],
                        ],
                      ),
                    ),
                    if (trailing != null) ...[const SizedBox(width: 8), trailing!],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The 36pt rounded tile at a row's start, holding an emoji, an icon, a dot or a ring.
class HomeRowTile extends StatelessWidget {
  const HomeRowTile({super.key, required this.child, this.outline});

  final Widget child;
  final Color? outline;

  @override
  Widget build(BuildContext context) => Container(
        width: HomeRowShell.tileExtent,
        height: HomeRowShell.tileExtent,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: OmiColors.surface2,
          borderRadius: OmiRadius.mdAll,
          border: outline == null ? null : Border.all(color: outline!, width: 1.5),
        ),
        child: child,
      );
}

/// A row's compact trailing action (Retry, Reconnect, Unlock): at least 44pt tall.
class HomeRowAction extends StatelessWidget {
  const HomeRowAction({super.key, required this.label, required this.onPressed, this.busy = false});

  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) => SizedBox(
        height: HomeRowShell.contentExtent,
        child: OmiButton.secondary(
          label: label,
          size: OmiButtonSize.compact,
          pill: true,
          isLoading: busy,
          onPressed: busy ? null : onPressed,
        ),
      );
}
