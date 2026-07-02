import 'package:flutter/material.dart';

import 'package:omi/ui/adaptive_widget.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';

/// Shared filled button.
///
/// Defaults match the app's canonical white call-to-action (white background,
/// black label, 28px pill, 18/w600, no elevation) — the style used across
/// onboarding. On brand: white/neutral, never purple.
///
/// Migrated call sites that still render the raw Material-2 button look use
/// [OmiButton.legacy]; that constructor is the grep-able work list for the
/// style-convergence pass.
///
/// Known, accepted deviations from the raw ElevatedButtons this replaces
/// (both effectively invisible on the near-black theme):
/// - elevation is always 0 (M2 default was 2 resting / 8 pressed);
/// - the pressed/hover ripple derives from the resolved foreground, so sites
///   whose label was white only via its Text style now ripple white-based.
class OmiButton extends AdaptiveWidget {
  final String label;
  final VoidCallback? onPressed;

  /// While true the label is replaced by a spinner and taps are blocked; the
  /// button keeps its enabled background so the color doesn't flash grey.
  final bool isLoading;

  final IconData? icon;

  /// When true the [icon] is rendered after the label (e.g. a trailing arrow).
  final bool trailingIcon;

  /// Background color override. Defaults to white.
  final Color? color;

  /// Foreground (label/icon/spinner) color override. Defaults to black.
  final Color? textColor;

  /// Disabled-state background / foreground overrides. Default to the
  /// neutral tokens used by the canonical CTA.
  final Color? disabledColor;
  final Color? disabledTextColor;

  final double? width;
  final double? height;
  final double borderRadius;
  final double fontSize;
  final FontWeight fontWeight;

  /// Icon size (defaults to fontSize + 2) and label↔icon gap.
  final double? iconSize;
  final double iconGap;

  /// Internal padding override. When null, the button's height is driven by
  /// its content / an outer SizedBox, matching the default CTA.
  final EdgeInsetsGeometry? padding;

  const OmiButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.icon,
    this.trailingIcon = false,
    this.color,
    this.textColor,
    this.disabledColor,
    this.disabledTextColor,
    this.width,
    this.height,
    this.borderRadius = 28,
    this.fontSize = 18,
    this.fontWeight = FontWeight.w600,
    this.iconSize,
    this.iconGap = 8,
    this.padding,
  });

  /// A button that intentionally keeps the raw Material-2 ElevatedButton look
  /// it replaced (radius 4 unless overridden, 14/w500 label). These sites are
  /// 1:1 carryovers from the pre-design-system migration, not designed styles
  /// — grep `OmiButton.legacy` to find every button awaiting convergence.
  const OmiButton.legacy({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.icon,
    this.trailingIcon = false,
    this.color,
    this.textColor,
    this.disabledColor,
    this.disabledTextColor,
    this.width,
    this.height,
    this.borderRadius = 4,
    this.iconSize,
    this.iconGap = 8,
    this.padding,
  })  : fontSize = 14,
        fontWeight = FontWeight.w500;

  bool get _active => !isLoading && onPressed != null;

  @override
  Widget buildDesktop(BuildContext context) => _button();

  @override
  Widget buildMobile(BuildContext context) => _button();

  Widget _button() {
    final bg = color ?? Colors.white;
    final fg = textColor ?? Colors.black;

    final button = ElevatedButton(
      onPressed: _active ? onPressed : null,
      style: ElevatedButton.styleFrom(
        backgroundColor: bg,
        foregroundColor: fg,
        // While loading the button is technically disabled (taps blocked), but
        // it keeps its enabled background so the color doesn't flash grey.
        disabledBackgroundColor: isLoading ? bg : (disabledColor ?? ResponsiveHelper.backgroundTertiary),
        disabledForegroundColor: disabledTextColor ?? ResponsiveHelper.textQuaternary,
        elevation: 0,
        padding: padding,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(borderRadius)),
      ),
      child: isLoading
          ? SizedBox(
              width: fontSize + 4,
              height: fontSize + 4,
              child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation<Color>(fg)),
            )
          : _labelRow(),
    );

    if (width != null || height != null) {
      return SizedBox(width: width, height: height, child: button);
    }
    return button;
  }

  /// No explicit colors here: the label and icon inherit the ElevatedButton's
  /// resolved foreground (fg when enabled, disabledForegroundColor when
  /// disabled), so the disabled state dims correctly.
  Widget _labelRow() {
    final text = Text(label, style: TextStyle(fontSize: fontSize, fontWeight: fontWeight));
    if (icon == null) return text;
    // The label is Flexible (like ElevatedButton.icon's) so long localized
    // labels wrap instead of overflowing the Row.
    final flexibleText = Flexible(child: text);
    final iconWidget = Icon(icon, size: iconSize ?? (fontSize + 2));
    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: trailingIcon
          ? [flexibleText, SizedBox(width: iconGap), iconWidget]
          : [iconWidget, SizedBox(width: iconGap), flexibleText],
    );
  }
}
