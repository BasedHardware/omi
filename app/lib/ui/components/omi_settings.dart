import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/gen/fonts.gen.dart';

import 'package:omi/ui/components/omi_line_icon.dart';
import 'package:omi/ui/omi_tokens.dart';

/// The on/off control for a setting. Neutral colours (INV-UI-1): on uses the palette accent.
///
/// Adaptive: a [CupertinoSwitch] on Apple platforms (inverse accent thumb), a Material
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
    if (OmiGroupedScope.of(context)) return _groupedHeader(title, subtitle: subtitle, trailing: trailing);
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

/// Marks a page drawn in the Settings look ([OmiGroupedPage]): below it an [OmiSettingsGroup]
/// with no style is [OmiSettingsGroupStyle.outlined] and an [OmiSectionHeader] is the small label.
class OmiGroupedScope extends InheritedWidget {
  const OmiGroupedScope({super.key, required super.child});

  static bool of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<OmiGroupedScope>() != null;

  @override
  bool updateShouldNotify(OmiGroupedScope oldWidget) => false;
}

/// Sets Settings in Instrument Sans; the rest of the app keeps the system font. It goes around a
/// whole page (above its Scaffold) so the Material and Cupertino text themes, the page's own text
/// and the sheets and dialogs the page opens all pick it up. Scripts it does not cover fall back
/// to the system font glyph by glyph.
class OmiSettingsTypeface extends StatelessWidget {
  const OmiSettingsTypeface({super.key, required this.child});

  static const String family = FontFamily.instrumentSans;

  /// Settings lists run 10% smaller than the app's rows elsewhere: row text, section labels and
  /// icon tiles.
  static const double listScale = 0.9;

  /// [listScale] on a Settings page (and the sheets it opens), 1 elsewhere, so a row in a
  /// conversation sheet keeps its size.
  static double scaleOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_SettingsListScale>() == null ? 1 : listScale;

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cupertino = theme.cupertinoOverrideTheme ?? const CupertinoThemeData();
    return Theme(
      data: theme.copyWith(
        textTheme: theme.textTheme.apply(fontFamily: family),
        primaryTextTheme: theme.primaryTextTheme.apply(fontFamily: family),
        cupertinoOverrideTheme: cupertino.copyWith(
          textTheme: CupertinoTheme.of(context).textTheme.copyWith(
                textStyle: CupertinoTheme.of(context).textTheme.textStyle.copyWith(fontFamily: family),
              ),
        ),
      ),
      child: _SettingsListScale(
        child: DefaultTextStyle.merge(style: const TextStyle(fontFamily: family), child: child),
      ),
    );
  }
}

/// Marks a Settings page for [OmiSettingsTypeface.scaleOf]; an [InheritedTheme] so a sheet or
/// dialog the page opens is scaled too.
class _SettingsListScale extends InheritedTheme {
  const _SettingsListScale({required super.child});

  @override
  Widget wrap(BuildContext context, Widget child) => _SettingsListScale(child: child);

  @override
  bool updateShouldNotify(_SettingsListScale oldWidget) => false;
}

/// [style] at [OmiSettingsTypeface.scaleOf] its size, never under [min].
TextStyle _scaled(BuildContext context, TextStyle style, double base, {double min = 11}) {
  final scale = OmiSettingsTypeface.scaleOf(context);
  if (scale == 1) return style;
  final size = (style.fontSize ?? base) * scale;
  return style.copyWith(fontSize: size < min ? min : size);
}

/// The small label above an outlined card: subhead, medium, secondary; optional supporting line
/// and trailing control.
Widget _groupedHeader(String title, {String? subtitle, Widget? trailing}) {
  return Padding(
    padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.xs),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Semantics(
                header: true,
                child: Builder(
                  builder: (context) => Text(
                    title,
                    style: _scaled(context,
                        OmiType.subhead.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textSecondary), 15),
                  ),
                ),
              ),
            ),
            if (trailing != null) trailing,
          ],
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 2),
          Builder(
            builder: (context) =>
                Text(subtitle, style: _scaled(context, OmiType.footnote.copyWith(color: OmiColors.textTertiary), 13)),
          ),
        ],
      ],
    ),
  );
}

/// How an [OmiSettingsGroup] draws its card.
enum OmiSettingsGroupStyle {
  /// A [OmiColors.surface1] card, rows separated by hairlines, under a title3 [OmiSectionHeader].
  inset,

  /// Top-level Settings: an outlined [OmiColors.groupedCard] on [OmiColors.groupedPage], no
  /// hairlines, under a small label. Its rows lead with an [OmiSettingsIconTile] and sit tighter.
  outlined,
}

/// A rounded [OmiColors.surface1] card holding [OmiSettingsRow]s, separated by hairlines
/// ([OmiSettingsGroupStyle.inset]), or the outlined top-level Settings card
/// ([OmiSettingsGroupStyle.outlined]).
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
  const OmiSettingsGroup({
    super.key,
    required this.children,
    this.header,
    this.headerSubtitle,
    this.footer,
    this.style,
  });

  /// Null: [OmiSettingsGroupStyle.outlined] inside an [OmiGroupedPage], else
  /// [OmiSettingsGroupStyle.inset].
  final OmiSettingsGroupStyle? style;

  final List<Widget> children;

  /// Optional [OmiSectionHeader] title drawn above the card.
  final String? header;
  final String? headerSubtitle;

  /// Optional explanatory text under the card.
  final String? footer;

  @override
  Widget build(BuildContext context) {
    final resolved =
        style ?? (OmiGroupedScope.of(context) ? OmiSettingsGroupStyle.outlined : OmiSettingsGroupStyle.inset);
    if (resolved == OmiSettingsGroupStyle.outlined) return _outlinedGroup(this);
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Divider(height: 1, thickness: 1, color: OmiColors.border));
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
class _OutlinedGroupScope extends InheritedWidget {
  const _OutlinedGroupScope({required super.child});

  static bool of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<_OutlinedGroupScope>() != null;

  @override
  bool updateShouldNotify(_OutlinedGroupScope oldWidget) => false;
}

/// [OmiSettingsGroupStyle.outlined]: label, outlined card, no hairlines, tighter rows.
Widget _outlinedGroup(OmiSettingsGroup group) {
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: [
      if (group.header != null) _groupedHeader(group.header!, subtitle: group.headerSubtitle),
      DecoratedBox(
        decoration: BoxDecoration(
          color: OmiColors.groupedCard,
          borderRadius: OmiRadius.xlAll,
          border: Border.all(color: OmiColors.groupedBorder),
        ),
        child: ClipRRect(
          borderRadius: OmiRadius.xlAll,
          child: Material(
            type: MaterialType.transparency,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xxs),
              child: _OutlinedGroupScope(
                child: Column(mainAxisSize: MainAxisSize.min, children: group.children),
              ),
            ),
          ),
        ),
      ),
      if (group.footer != null)
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
          // Takes the list scale like the header's supporting line.
          child: Builder(
            builder: (context) => Text(group.footer!,
                style: _scaled(context, OmiType.footnote.copyWith(color: OmiColors.textTertiary), 13)),
          ),
        ),
    ],
  );
}

/// A custom block on a grouped page (a slider, a banner, a word list) drawn like the outlined
/// Settings card around it: [OmiColors.groupedCard], [OmiColors.groupedBorder], xl corners.
class OmiGroupedCard extends StatelessWidget {
  const OmiGroupedCard({super.key, required this.child, this.padding = const EdgeInsets.all(OmiSpacing.md)});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: OmiColors.groupedCard,
        borderRadius: OmiRadius.xlAll,
        border: Border.all(color: OmiColors.groupedBorder),
      ),
      child: ClipRRect(
        borderRadius: OmiRadius.xlAll,
        child: Material(type: MaterialType.transparency, child: Padding(padding: padding, child: child)),
      ),
    );
  }
}

/// One row of an outlined Settings card that a lazy list builds row by row (thousands of
/// recordings): every row paints the card's sides, [first] rounds and closes the top, [last] the
/// bottom, so consecutive rows read as one [OmiGroupedCard].
class OmiGroupedSlice extends StatelessWidget {
  const OmiGroupedSlice({super.key, required this.child, this.first = false, this.last = false});

  final Widget child;
  final bool first;
  final bool last;

  @override
  Widget build(BuildContext context) {
    const r = Radius.circular(OmiRadius.xl);
    return CustomPaint(
      painter: _SlicePainter(first: first, last: last, color: OmiColors.groupedCard),
      // The outline over the row, so a pressed row's highlight never covers it.
      foregroundPainter: _SlicePainter(first: first, last: last, color: OmiColors.groupedBorder, stroke: true),
      child: ClipRRect(
        borderRadius: BorderRadius.vertical(top: first ? r : Radius.zero, bottom: last ? r : Radius.zero),
        child: Material(
          type: MaterialType.transparency,
          child: Padding(
            padding: EdgeInsets.only(top: first ? OmiSpacing.xxs : 0, bottom: last ? OmiSpacing.xxs : 0),
            child: child,
          ),
        ),
      ),
    );
  }
}

class _SlicePainter extends CustomPainter {
  _SlicePainter({required this.first, required this.last, required this.color, this.stroke = false});

  final bool first;
  final bool last;
  final Color color;

  /// The 1 pt outline, else the fill.
  final bool stroke;

  @override
  void paint(Canvas canvas, Size size) {
    const r = Radius.circular(OmiRadius.xl);
    // An open edge runs past the row and is clipped, so the sides join the next row seamlessly.
    final rect = Rect.fromLTRB(0, first ? 0 : -2, size.width, last ? size.height : size.height + 2);
    final shape = RRect.fromRectAndCorners(
      rect,
      topLeft: first ? r : Radius.zero,
      topRight: first ? r : Radius.zero,
      bottomLeft: last ? r : Radius.zero,
      bottomRight: last ? r : Radius.zero,
    );
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    if (stroke) {
      canvas.drawRRect(
        shape.deflate(0.5),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1
          ..color = color,
      );
    } else {
      canvas.drawRRect(shape, Paint()..color = color);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_SlicePainter old) =>
      old.first != first || old.last != last || old.color != color || old.stroke != stroke;
}

/// The 44 pt warm tile a row in an [OmiSettingsGroupStyle.outlined] group leads with.
class OmiSettingsIconTile extends StatelessWidget {
  const OmiSettingsIconTile(OmiLineGlyph this.glyph, {super.key}) : child = null;

  /// The same tile around something the row draws itself: a spinner, or a glyph in a warning or
  /// error colour.
  const OmiSettingsIconTile.custom({super.key, required Widget this.child}) : glyph = null;

  final OmiLineGlyph? glyph;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    final scale = OmiSettingsTypeface.scaleOf(context);
    final side = kOmiSettingsIconTileSize * scale;
    return Container(
      width: side,
      height: side,
      alignment: Alignment.center,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: OmiColors.iconTile,
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: OmiColors.groupedBorder),
      ),
      // A custom child sized by the icon theme (no size of its own) scales with the tile.
      child: IconTheme.merge(
        data: IconThemeData(size: 24 * scale, color: OmiColors.iconTileGlyph),
        child: child ?? OmiLineIcon(glyph!),
      ),
    );
  }
}

const double kOmiSettingsIconTileSize = 44;

/// The signed-in person as a round tile with their initial (a person glyph when the name is
/// empty): the Settings profile card and the top of Account.
class OmiSettingsAvatar extends StatelessWidget {
  const OmiSettingsAvatar({super.key, required this.name, this.size = 52});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final trimmed = name.trim();
    final initial = trimmed.isEmpty ? null : String.fromCharCodes(trimmed.runes.take(1)).toUpperCase();
    final size = this.size * OmiSettingsTypeface.scaleOf(context);
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: OmiColors.iconTile,
          shape: BoxShape.circle,
          border: Border.all(color: OmiColors.groupedBorder),
        ),
        child: initial == null
            ? OmiLineIcon(OmiLineGlyph.person, size: size * 0.45, color: OmiColors.iconTileGlyph)
            : Text(initial,
                style: OmiType.title1.copyWith(fontSize: size * 0.4, height: 1, color: OmiColors.textPrimary)),
      ),
    );
  }
}

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
    this.titleStyle,
    this.subtitleColor,
    this.subtitleStyle,
    this.titleMaxLines,
    this.subtitleMaxLines,
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
        isDestructive = false,
        titleStyle = null,
        subtitleColor = null,
        subtitleStyle = null,
        titleMaxLines = null,
        subtitleMaxLines = null;

  final String title;

  /// Usually an [Icon] (20pt [OmiColors.textTertiary] by default through [IconTheme]); an app
  /// avatar (32pt) also fits.
  final Widget? leading;

  final String? subtitle;

  /// Current value shown trailing in secondary text ("English", "Off"). Ellipsized so the title
  /// always keeps at least half the row ("Hardware Revision" stays on one line).
  final String? value;

  /// Custom trailing widget; wins over [value].
  final Widget? trailing;

  final VoidCallback? onTap;

  /// Force the chevron on or off. Defaults to on when the row has [onTap] and no [trailing].
  final bool? showChevron;

  /// Red title and icon, for rows like "Delete Account" or "Sign Out".
  final bool isDestructive;

  /// Overrides the body title style (the Settings profile card's larger name, a dimmed row).
  final TextStyle? titleStyle;

  /// Overrides the tertiary subtitle colour, for a status line that is a warning or an error.
  final Color? subtitleColor;

  /// Merged over the subtitle's footnote style: a key prefix set in monospace, for one.
  final TextStyle? subtitleStyle;

  /// Ellipsize the title or subtitle after this many lines (a name or an email the person typed);
  /// null wraps in full, the default for the app's own words.
  final int? titleMaxLines;
  final int? subtitleMaxLines;

  final bool? toggleValue;
  final ValueChanged<bool>? onToggle;

  bool get _isToggle => toggleValue != null;

  @override
  Widget build(BuildContext context) {
    final titleColor = isDestructive ? OmiColors.danger : (titleStyle?.color ?? OmiColors.textPrimary);
    final chevron = showChevron ?? (onTap != null && trailing == null);
    final scale = OmiSettingsTypeface.scaleOf(context);

    Widget? trailingWidget;
    if (_isToggle) {
      trailingWidget = ExcludeSemantics(child: OmiSwitch(value: toggleValue!, onChanged: onToggle));
    } else if (trailing != null) {
      trailingWidget = trailing;
    }

    // In an outlined group a 44 pt icon tile sets the height, so that row pads less.
    final tight = leading is OmiSettingsIconTile && _OutlinedGroupScope.of(context);
    final row = ConstrainedBox(
      // Smaller in Settings, but never under a 44 pt touch target.
      constraints: BoxConstraints(minHeight: scale == 1 ? 48 : 44),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: tight ? OmiSpacing.xs : OmiSpacing.md),
        child: LayoutBuilder(
          builder: (context, constraints) {
            return Row(
              children: [
                if (leading != null) ...[
                  IconTheme.merge(
                    data: IconThemeData(
                      size: 20 * scale,
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
                      Text(
                        title,
                        maxLines: titleMaxLines,
                        overflow: titleMaxLines == null ? null : TextOverflow.ellipsis,
                        style: _scaled(context, (titleStyle ?? OmiType.body).copyWith(color: titleColor), 17),
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          maxLines: subtitleMaxLines,
                          overflow: subtitleMaxLines == null ? null : TextOverflow.ellipsis,
                          style: _scaled(
                              context,
                              OmiType.footnote
                                  .copyWith(color: subtitleColor ?? OmiColors.textTertiary)
                                  .merge(subtitleStyle),
                              13),
                        ),
                      ],
                    ],
                  ),
                ),
                if (value != null && trailingWidget == null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  ConstrainedBox(
                    constraints: BoxConstraints(maxWidth: constraints.maxWidth * 0.5),
                    child: Text(
                      value!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.end,
                      style: _scaled(context, OmiType.subhead.copyWith(color: OmiColors.textSecondary), 15),
                    ),
                  ),
                ],
                if (trailingWidget != null) ...[
                  const SizedBox(width: OmiSpacing.xs),
                  trailingWidget,
                ],
                if (chevron) ...[
                  const SizedBox(width: OmiSpacing.xxs),
                  ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20 * scale, color: OmiColors.textTertiary)),
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
