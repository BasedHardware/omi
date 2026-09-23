import 'package:flutter/material.dart';

import 'package:omi/ui/components/omi_button.dart';

/// Legacy async button, now a thin shell over [OmiButton].
///
/// New code uses `OmiButton(label:, onPressed:)` with a variant; this class keeps its old
/// constructor so existing call sites compile until they migrate. Behaviour inherited from
/// [OmiButton]: the spinner always clears when [onPressed] finishes or throws, the touch target is
/// at least 44pt even when [height] is smaller, and the button exposes button semantics.
///
/// Colours: [color] fills the button and [textStyle]'s colour is the label and spinner colour.
/// [loaderColor] and [animationDuration] are accepted for compatibility and no longer used (the
/// spinner takes the label colour, so it can no longer vanish on a same-coloured fill).
class AnimatedLoadingButton extends StatelessWidget {
  final String text;
  final Future<void> Function() onPressed;
  final double width;
  final double height;
  final Color color;
  final Color loaderColor;
  final TextStyle textStyle;
  final Duration animationDuration;

  const AnimatedLoadingButton({
    super.key,
    required this.text,
    required this.onPressed,
    this.width = 200,
    this.height = 48,
    required this.color,
    this.loaderColor = Colors.white,
    this.textStyle = const TextStyle(fontSize: 16, color: Colors.white),
    this.animationDuration = const Duration(milliseconds: 300),
  });

  @override
  Widget build(BuildContext context) {
    return OmiButton(
      label: text,
      onPressed: onPressed,
      width: width,
      height: height,
      labelStyle: textStyle,
      colors: OmiButtonColors(background: color, foreground: textStyle.color ?? loaderColor),
    );
  }
}
