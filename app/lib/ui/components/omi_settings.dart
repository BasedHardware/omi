import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The on/off control for a setting. Neutral colours (INV-UI-1): on is a white track.
///
/// Adaptive: a [CupertinoSwitch] on Apple platforms (black thumb on the white track), a Material
/// [Switch] elsewhere (styled by the app theme). Checkboxes are only for picking items out of a
/// list, never for a setting. Platform switches give their own haptic feedback.
///
/// Inside a settings row use `OmiSettingsRow.toggle`, which makes the whole row the target.
class OmiSwitch extends StatelessWidget {
  const OmiSwitch({super.key, required this.value, required this.onChanged});

  final bool value;

  /// Null disables the switch.
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    switch (Theme.of(context).platform) {
      case TargetPlatform.iOS:
      case TargetPlatform.macOS:
        return CupertinoSwitch(
          value: value,
          onChanged: onChanged,
          activeTrackColor: OmiColors.accent,
          thumbColor: OmiColors.onAccent,
          inactiveThumbColor: OmiColors.textPrimary,
          inactiveTrackColor: OmiColors.surface3,
        );
      case TargetPlatform.android:
      case TargetPlatform.fuchsia:
      case TargetPlatform.linux:
      case TargetPlatform.windows:
        return Switch(value: value, onChanged: onChanged);
    }
  }
}

/// A section title above a group of rows or cards: 20pt semibold, optional supporting line and a
/// trailing control (e.g. a compact "Add" button).
class OmiSectionHeader extends StatelessWidget {
  const OmiSectionHeader(this.title, {super.key, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: OmiSpacing.xxs, right: OmiSpacing.xxs, bottom: OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Semantics(header: true, child: Text(title, style: OmiType.title3))),
              if (trailing != null) trailing!,
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: 6),
            Text(subtitle!, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

/// A rounded [OmiColors.surface1] card holding [OmiSettingsRow]s, separated by hairlines.
///
/// ```dart
/// OmiSettingsGroup(
///   header: l10n.account,
///   children: [
///     OmiSettingsRow(leading: const Icon(Icons.person), title: l10n.name, value: name, onTap: _editName),
///     OmiSettingsRow.toggle(title: l10n.autoSync, value: autoSync, onChanged: _setAutoSync),
///   ],
/// )
/// ```
class OmiSettingsGroup extends StatelessWidget {
  const OmiSettingsGroup({super.key, required this.children, this.header, this.headerSubtitle, this.footer});

  final List<Widget> children;

  /// Optional [OmiSectionHeader] title drawn above the card.
  final String? header;
  final String? headerSubtitle;

  /// Optional explanatory text under the card.
  final String? footer;

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(const Divider(height: 1, thickness: 1, color: OmiColors.border));
      rows.add(children[i]);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (header != null) OmiSectionHeader(header!, subtitle: headerSubtitle),
        ClipRRect(
          borderRadius: OmiRadius.lgAll,
          child: Material(color: OmiColors.surface1, child: Column(mainAxisSize: MainAxisSize.min, children: rows)),
        ),
        if (footer != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
            child: Text(footer!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
          ),
      ],
    );
  }
}

/// One settings row: leading icon, title, optional subtitle, and one trailing element — a chevron
/// (navigates), a switch ([OmiSettingsRow.toggle]), a value text, or a custom widget.
///
/// The whole row is the touch target (at least 48pt tall) and one accessibility node. A row with
/// [onTap] and no other trailing element shows a chevron.
///
/// Place rows in an [OmiSettingsGroup]; a lone row paints no background of its own.
class OmiSettingsRow extends StatelessWidget {
  const OmiSettingsRow({
    super.key,
    required this.title,
    this.leading,
    this.subtitle,
    this.value,
    this.trailing,
    this.onTap,
    this.showChevron,
    this.isDestructive = false,
  })  : toggleValue = null,
        onToggle = null;

  /// A row whose trailing element is an [OmiSwitch]; tapping anywhere on the row flips it.
  const OmiSettingsRow.toggle({
    super.key,
    required this.title,
    required bool value,
    required ValueChanged<bool>? onChanged,
    this.leading,
    this.subtitle,
  })  : toggleValue = value,
        onToggle = onChanged,
        value = null,
        trailing = null,
        onTap = null,
        showChevron = false,
        isDestructive = false;

  final String title;

  /// Usually an [Icon] (20pt [OmiColors.textTertiary] by default through [IconTheme]); an app
  /// avatar (32pt) also fits.
  final Widget? leading;

  final String? subtitle;

  /// Current value shown trailing in secondary text ("English", "Off"). Ellipsized so the title
  /// always keeps at least 40% of the row.
  final String? value;

  /// Custom trailing widget; wins over [value].
  final Widget? trailing;

  final VoidCallback? onTap;

  /// Force the chevron on or off. Defaults to on when the row has [onTap] and no [trailing].
  final bool? showChevron;

  /// Red title and icon, for rows like "Delete Account" or "Sign Out".
  final bool isDestructive;

  final bool? toggleValue;
  final ValueChanged<bool>? onToggle;

  bool get _isToggle => toggleValue != null;

  @override
  Widget build(BuildContext context) {
    final titleColor = isDestructive ? OmiColors.danger : OmiColors.textPrimary;
    final chevron = showChevron ?? (onTap != null && trailing == null);

    Widget? trailingWidget;
    if (_isToggle) {
      trailingWidget = ExcludeSemantics(child: OmiSwitch(value: toggleValue!, onChanged: onToggle));
    } else if (trailing != null) {
      trailingWidget = trailing;
    }

    final row = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 48),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.md),
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Row(
              children: [
                if (leading != null) ...[
                  IconTheme.merge(
                    data: IconThemeData(
                      size: 20,
                      color: isDestructive ? OmiColors.danger : OmiColors.textTertiary,
                    ),
                    // At least 24pt wide so icons line up; an avatar may be wider.
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(minWidth: 24),
                      child: Center(widthFactor: 1, child: leading),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.md),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(title, style: OmiType.body.copyWith(color: titleColor)),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(subtitle!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                      ],
                    ],
                  ),
                ),
                if (value != null && trailingWidget == null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: constraints.maxWidth * 0.6),
                    child: Text(
                      value!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.end,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                    ),
                  ),
                ],
                if (trailingWidget != null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  trailingWidget,
                ],
                if (chevron) ...[
                  const SizedBox(width: OmiSpacing.xxs),
                  const ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary)),
                ],
              ],
            );
          },
        ),
      ),
    );

    if (_isToggle) {
      final enabled = onToggle != null;
      return MergeSemantics(
        child: Semantics(
          toggled: toggleValue,
          enabled: enabled,
          child: InkWell(onTap: enabled ? () => onToggle!(!toggleValue!) : null, child: row),
        ),
      );
    }
    if (onTap == null) return MergeSemantics(child: row);
    return MergeSemantics(
      child: Semantics(button: true, child: InkWell(onTap: onTap, child: row)),
    );
  }
}
