import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_icon_button.dart';

/// The leading control of every pushed page.
///
/// Rule: a page that **replaced** the one you were on (a push) leaves by [OmiBackButton] on the
/// leading edge; a surface that **floats over** it (sheet, full-screen modal, viewer) leaves by
/// `OmiCloseButton` on the trailing edge. Never an X on a push, never a chevron on a modal.
///
/// The glyph is the platform's back icon ([BackButtonIcon]: the iOS chevron on Apple platforms,
/// the Material arrow on Android), the label is the localized "Back", and the target is 44pt.
/// Pressing it calls [onPressed], or `Navigator.maybePop` when that is null — so it behaves like
/// the edge swipe and the Android system back.
///
/// ```dart
/// Scaffold(appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.dataPrivacy)))
/// ```
///
/// v2 draws every back button as the 44pt header circle ([OmiColors.surface1] behind the glyph),
/// in an app bar or in a header that floats over content. [OmiBackButton.circled] is the same
/// control with a custom [fillColor].
class OmiBackButton extends StatelessWidget {
  const OmiBackButton({super.key, this.onPressed, this.color})
      : circled = true,
        fillColor = null;

  const OmiBackButton.circled({super.key, this.onPressed, this.color, this.fillColor}) : circled = true;

  /// Overrides the default `Navigator.maybePop`. Use it to step back inside a multi-step flow.
  final VoidCallback? onPressed;

  /// Glyph colour; defaults to `OmiColors.textPrimary`.
  final Color? color;

  /// Circle colour for [OmiBackButton.circled].
  final Color? fillColor;

  final bool circled;

  @override
  Widget build(BuildContext context) {
    final label = MaterialLocalizations.of(context).backButtonTooltip;
    void pressed() => onPressed != null ? onPressed!() : Navigator.maybePop(context);
    if (circled) {
      return OmiIconButton.filled(
        icon: const BackButtonIcon(),
        label: label,
        onPressed: pressed,
        color: color,
        fillColor: fillColor,
      );
    }
    return OmiIconButton(icon: const BackButtonIcon(), label: label, onPressed: pressed, color: color);
  }
}

/// The trailing X of a modal surface: bottom sheets, full-screen dialogs, media viewers.
///
/// Localized "Close" label, 44pt target, `Navigator.maybePop` by default. See [OmiBackButton] for
/// the push/modal rule. v2 draws it as the 44pt header circle, like [OmiBackButton];
/// [OmiCloseButton.circled] is the same control with a custom [fillColor].
class OmiCloseButton extends StatelessWidget {
  const OmiCloseButton({super.key, this.onPressed, this.color})
      : circled = true,
        fillColor = null;

  const OmiCloseButton.circled({super.key, this.onPressed, this.color, this.fillColor}) : circled = true;

  /// Overrides the default `Navigator.maybePop`.
  final VoidCallback? onPressed;

  /// Glyph colour; defaults to `OmiColors.textPrimary`.
  final Color? color;

  /// Circle colour for [OmiCloseButton.circled].
  final Color? fillColor;

  final bool circled;

  @override
  Widget build(BuildContext context) {
    final label = MaterialLocalizations.of(context).closeButtonTooltip;
    void pressed() => onPressed != null ? onPressed!() : Navigator.maybePop(context);
    if (circled) {
      return OmiIconButton.filled(
        icon: const Icon(Icons.close),
        label: label,
        onPressed: pressed,
        color: color,
        fillColor: fillColor,
      );
    }
    return OmiIconButton(icon: const Icon(Icons.close), label: label, onPressed: pressed, color: color);
  }
}
