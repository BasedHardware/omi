import 'package:flutter/material.dart';

import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

enum OmiButtonType { primary, text, neutral }

/// Shared label/icon button.
///
/// The [primary] variant matches the app's canonical white call-to-action
/// (white background, black label, 28px pill, 18/w600 Manrope, no elevation) —
/// the same style used across onboarding. On brand: white/neutral, never purple.
/// Sizing ([width]/[height]) and geometry ([borderRadius]/[fontSize]) are
/// overridable so existing call sites can be matched exactly.
class OmiButton extends AdaptiveWidget {
  final String label;
  final VoidCallback? onPressed;
  final OmiButtonType type;
  final bool enabled;
  final bool isLoading;
  final IconData? icon;

  /// When true the [icon] is rendered after the label (e.g. a trailing arrow).
  final bool trailingIcon;

  /// Background color override (primary/neutral). Defaults to white for primary.
  final Color? color;

  /// Foreground (label/icon) color override. Defaults to black for primary.
  final Color? textColor;

  /// Disabled-state background / foreground overrides (primary). Default to the
  /// neutral tokens used by the canonical CTA.
  final Color? disabledColor;
  final Color? disabledTextColor;

  final double? width;
  final double? height;
  final double? borderRadius;
  final double? fontSize;

  /// Label weight override (primary defaults to w600).
  final FontWeight? fontWeight;

  /// Icon size override (defaults to fontSize + 2) and label↔icon gap (defaults to 8).
  final double? iconSize;
  final double? iconGap;

  /// Internal padding override (primary). When null, the button's height is
  /// driven by its content / an outer SizedBox, matching the default CTA.
  final EdgeInsetsGeometry? padding;

  const OmiButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.type = OmiButtonType.primary,
    this.enabled = true,
    this.isLoading = false,
    this.icon,
    this.trailingIcon = false,
    this.color,
    this.textColor,
    this.disabledColor,
    this.disabledTextColor,
    this.width,
    this.height,
    this.borderRadius,
    this.fontSize,
    this.fontWeight,
    this.iconSize,
    this.iconGap,
    this.padding,
  });

  bool get _active => enabled && !isLoading && onPressed != null;

  @override
  Widget buildDesktop(BuildContext context) => _base();

  @override
  Widget buildMobile(BuildContext context) => _base();

  Widget _base() {
    switch (type) {
      case OmiButtonType.primary:
        return _primary();
      case OmiButtonType.text:
        return _text();
      case OmiButtonType.neutral:
        return _neutral();
    }
  }

  Widget _primary() {
    final radius = borderRadius ?? 28;
    final bg = color ?? Colors.white;
    final fg = textColor ?? Colors.black;
    final size = fontSize ?? 18;

    final button = ElevatedButton(
      onPressed: _active ? onPressed : null,
      style: ElevatedButton.styleFrom(
        backgroundColor: bg,
        foregroundColor: fg,
        disabledBackgroundColor: disabledColor ?? ResponsiveHelper.backgroundTertiary,
        disabledForegroundColor: disabledTextColor ?? ResponsiveHelper.textQuaternary,
        elevation: 0,
        padding: padding,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
      ),
      child: isLoading
          ? SizedBox(
              width: size + 4,
              height: size + 4,
              child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation<Color>(fg)),
            )
          // color: null → the label/icon inherit the ElevatedButton's resolved
          // foreground (fg when enabled, disabledForegroundColor when disabled),
          // instead of baking the enabled color on and defeating the disabled state.
          : _labelRow(
              size: size,
              weight: fontWeight ?? FontWeight.w600,
              color: null,
              iconSize: iconSize ?? (size + 2),
              iconGap: iconGap ?? 8,
            ),
    );

    if (width != null || height != null) {
      return SizedBox(width: width, height: height, child: button);
    }
    return button;
  }

  Widget _text() {
    final fg = enabled ? (textColor ?? ResponsiveHelper.textSecondary) : ResponsiveHelper.textTertiary;
    final size = fontSize ?? 14;
    return TextButton(
      onPressed: _active ? onPressed : null,
      child: _labelRow(size: size, weight: FontWeight.normal, color: fg, iconSize: 18, iconGap: 4),
    );
  }

  Widget _neutral() {
    final radius = borderRadius ?? 8;
    final fg = enabled ? (textColor ?? ResponsiveHelper.textSecondary) : ResponsiveHelper.textQuaternary;
    final size = fontSize ?? 12;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: _active ? onPressed : null,
        borderRadius: BorderRadius.circular(radius),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          decoration: BoxDecoration(
            color: (color ?? ResponsiveHelper.backgroundTertiary).withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(radius),
          ),
          child: _labelRow(size: size, weight: FontWeight.w500, color: fg, iconSize: 12, iconGap: 6),
        ),
      ),
    );
  }

  /// [color] may be null so the label/icon inherit the button's own state-aware
  /// foreground (enabled vs disabled). The [primary] variant relies on this so
  /// disabledForegroundColor actually dims the disabled label/icon; the
  /// [text]/[neutral] variants pass an explicit color since they drive their own.
  Widget _labelRow({
    required double size,
    required FontWeight weight,
    Color? color,
    required double iconSize,
    double iconGap = 8,
  }) {
    final text = Text(
      label,
      style: TextStyle(fontSize: size, fontWeight: weight, fontFamily: 'Manrope', color: color),
    );
    if (icon == null) return text;
    final iconWidget = Icon(icon, size: iconSize, color: color);
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children:
          trailingIcon ? [text, SizedBox(width: iconGap), iconWidget] : [iconWidget, SizedBox(width: iconGap), text],
    );
  }
}
