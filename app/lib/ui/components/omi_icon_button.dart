import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Smallest comfortable touch target: Apple's HIG asks for 44x44pt, Material for 48dp. Icon
/// controls use the smaller of the two so a row of them still fits a phone-width app bar.
const double kOmiMinTapTarget = 44;

/// Diameter of the circle a filled [OmiIconButton] paints by default.
const double kOmiIconCircleDiameter = 36;

/// An icon-only control. The [label] is required: it is the tooltip on long-press and the name a
/// screen reader announces. An icon without words is only a control for people who already know
/// what it does.
///
/// The touch target is always [kOmiMinTapTarget] square, whatever the glyph or circle size.
///
/// ```dart
/// OmiIconButton(icon: const Icon(Icons.share), label: l10n.share, onPressed: _share)
/// OmiIconButton.filled(icon: const Icon(Icons.settings, size: 16), label: l10n.settings, onPressed: _open)
/// OmiIconButton(icon: const Icon(Icons.delete_outline), label: l10n.delete, onPressed: _delete, isDestructive: true)
/// ```
///
/// Use [OmiIconButton.filled] for header controls that float over content or sit in the tab-root
/// headers (a [diameter] circle in [OmiColors.surface1]); the plain style for toolbar and row
/// actions. For leaving a page or a modal use `OmiBackButton` / `OmiCloseButton`, not this.
class OmiIconButton extends StatelessWidget {
  const OmiIconButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
    this.color,
    this.isDestructive = false,
  })  : filled = false,
        fillColor = null,
        diameter = kOmiIconCircleDiameter;

  const OmiIconButton.filled({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
    this.color,
    this.fillColor,
    this.diameter = kOmiIconCircleDiameter,
    this.isDestructive = false,
  }) : filled = true;

  /// The glyph, usually an [Icon]. Its colour defaults to [color] through [IconTheme].
  final Widget icon;

  /// Tooltip and accessibility label. Sentence case, no trailing period ("Delete memory").
  final String label;

  /// Null disables the control (dimmed, not announced as tappable).
  final VoidCallback? onPressed;

  /// Glyph colour. Defaults to [OmiColors.textPrimary], or [OmiColors.danger] when destructive.
  final Color? color;

  /// Paints the glyph red. Use for delete/remove actions.
  final bool isDestructive;

  /// Whether a circle is painted behind the glyph.
  final bool filled;

  /// Circle colour for [OmiIconButton.filled]. Defaults to [OmiColors.surface1].
  final Color? fillColor;

  /// Diameter of the painted circle. The touch target stays [kOmiMinTapTarget].
  final double diameter;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    var glyphColor = color ?? (isDestructive ? OmiColors.danger : OmiColors.textPrimary);
    if (!enabled) glyphColor = glyphColor.withValues(alpha: 0.38);

    Widget glyph = IconTheme.merge(
      data: IconThemeData(color: glyphColor, size: filled ? 18 : 22),
      child: ExcludeSemantics(child: icon),
    );
    if (filled) {
      glyph = Container(
        width: diameter,
        height: diameter,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: fillColor ?? OmiColors.surface1, shape: BoxShape.circle),
        child: glyph,
      );
    }

    return Tooltip(
      message: label,
      excludeFromSemantics: true,
      child: Semantics(
        button: true,
        enabled: enabled,
        label: label,
        child: InkResponse(
          onTap: onPressed,
          radius: kOmiMinTapTarget / 2,
          child: SizedBox(
            width: kOmiMinTapTarget,
            height: kOmiMinTapTarget,
            child: Center(child: glyph),
          ),
        ),
      ),
    );
  }
}
