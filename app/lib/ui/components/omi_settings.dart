import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/components/omi_glyph.dart';
import 'package:omi/ui/components/omi_surface.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The on/off control for a setting: on is an [OmiColors.selection] track with a light thumb.
///
/// Adaptive: a [CupertinoSwitch] on Apple platforms, a Material [Switch] elsewhere (styled by the
/// app theme with the same colours). Checkboxes are only for picking items out of a
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
          // v2: midnight when on, the strong fill when off, a white knob.
          activeTrackColor: OmiColors.selection,
          thumbColor: Colors.white,
          inactiveThumbColor: Colors.white,
          inactiveTrackColor: OmiColors.surface4,
        );
      case TargetPlatform.android:
      case TargetPlatform.fuchsia:
      case TargetPlatform.linux:
      case TargetPlatform.windows:
        return Switch(value: value, onChanged: onChanged);
    }
  }
}

/// A section title above a group of rows or cards: 20pt semibold (v2 section heading), optional
/// supporting line and a trailing control (a "See All" link, a compact "Add" button).
class OmiSectionHeader extends StatelessWidget {
  const OmiSectionHeader(this.title, {super.key, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: OmiSpacing.xxs, right: OmiSpacing.xxs, bottom: 10),
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

/// A v2 [OmiCard] (radius 26) holding [OmiSettingsRow]s, separated by 0.5 pt hairlines that start
/// where the row text starts (after the icon tile when the next row has one).
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
      // v2 hairlines start where the row text starts: 58 after a 30pt icon tile, else 16.
      if (i > 0) {
        final child = children[i];
        final tiled = child is OmiSettingsRow && child.leading != null;
        rows.add(Divider(height: 0.5, thickness: 0.5, indent: tiled ? 58 : OmiSpacing.md, color: OmiColors.border));
      }
      rows.add(children[i]);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (header != null) OmiSectionHeader(header!, subtitle: headerSubtitle),
        OmiCard(
          clip: true,
          child:
              Material(type: MaterialType.transparency, child: Column(mainAxisSize: MainAxisSize.min, children: rows)),
        ),
        if (footer != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
            child: Text(footer!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
          ),
      ],
    );
  }
}

/// One settings row: leading icon, title, optional subtitle, and one trailing element — a chevron
/// (navigates), a switch ([OmiSettingsRow.toggle]), a value text, or a custom widget.
///
/// The whole row is the touch target (at least 52pt tall, v2 `rowMinHeight`) and one accessibility
/// node. An icon leading sits in a 30pt tile ([OmiColors.surface2]); an avatar stands alone. A row with
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

  static Color get _cellPressed => OmiColors.cellPressed;

  /// A plain icon (Material, FontAwesome or a v2 glyph) gets the tile; anything else is an avatar.
  static bool _isGlyph(Widget w) => w is Icon || w is FaIcon || w is OmiGlyph;

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
      constraints: const BoxConstraints(minHeight: OmiSize.rowMinHeight),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Row(
              children: [
                if (leading != null) ...[
                  IconTheme.merge(
                    data: IconThemeData(
                      size: 18,
                      color: isDestructive ? OmiColors.danger : OmiColors.textPrimary,
                    ),
                    child: _isGlyph(leading!)
                        // v2: an icon sits in a 30pt tile so the column of icons reads as one set.
                        ? OmiIconTile(
                            color: isDestructive ? OmiColors.dangerSurface : OmiColors.surface3,
                            child: IconTheme.merge(
                              data: IconThemeData(
                                size: 18,
                                color: isDestructive ? OmiColors.danger : OmiColors.textPrimary,
                              ),
                              child: leading!,
                            ),
                          )
                        // An avatar or app logo keeps its own shape, at least 30pt wide so text lines up.
                        : ConstrainedBox(
                            constraints: const BoxConstraints(minWidth: 30),
                            child: Center(widthFactor: 1, child: leading),
                          ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(title, style: OmiType.body.copyWith(color: titleColor)),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(subtitle!, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
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
                      style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                    ),
                  ),
                ],
                if (trailingWidget != null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  trailingWidget,
                ],
                if (chevron) ...[
                  const SizedBox(width: OmiSpacing.xxs),
                  OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
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
          child: InkWell(
            onTap: enabled ? () => onToggle!(!toggleValue!) : null,
            splashFactory: NoSplash.splashFactory,
            highlightColor: _cellPressed,
            child: row,
          ),
        ),
      );
    }
    if (onTap == null) return MergeSemantics(child: row);
    return MergeSemantics(
      child: Semantics(
        button: true,
        child: InkWell(onTap: onTap, splashFactory: NoSplash.splashFactory, highlightColor: _cellPressed, child: row),
      ),
    );
  }
}
