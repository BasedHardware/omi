import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Spinner sizes. [small] sits inside a button or row, [regular] is a section or page load,
/// [large] is a blocking overlay.
enum OmiSpinnerSize {
  small(16),
  regular(24),
  large(36);

  const OmiSpinnerSize(this.diameter);

  final double diameter;
}

/// The one activity indicator: white, 2pt stroke, three sizes.
///
/// Use it for every spinner — in a button, a row, a list footer, an overlay. For a page body that
/// is loading for the first time use [OmiLoadingState], which centres a regular spinner with an
/// optional label. Never scale a spinner with `Transform.scale`; pick a size.
class OmiSpinner extends StatelessWidget {
  const OmiSpinner({super.key, this.size = OmiSpinnerSize.regular, this.color, this.label});

  final OmiSpinnerSize size;

  /// Arc colour. Defaults to [OmiColors.accent]; pass the button's foreground inside a filled
  /// button.
  final Color? color;

  /// Optional text under the spinner ("Loading tasks…"). Also its accessibility label.
  final String? label;

  @override
  Widget build(BuildContext context) {
    final spinner = SizedBox.square(
      dimension: size.diameter,
      child: CircularProgressIndicator(
        strokeWidth: 2,
        color: color ?? OmiColors.accent,
        semanticsLabel: label,
      ),
    );
    if (label == null) return spinner;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        spinner,
        const SizedBox(height: OmiSpacing.sm),
        ExcludeSemantics(
          child: Text(
            label!,
            textAlign: TextAlign.center,
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
        ),
      ],
    );
  }
}
