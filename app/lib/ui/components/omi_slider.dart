import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The v2 slider (design `.range`): a 4pt track, filled in the text colour up to the value and
/// [OmiColors.surface4] after it, under a 26pt white thumb with a soft shadow. 28pt tall.
///
/// ```dart
/// OmiSlider(value: brightness, max: 100, divisions: 100, onChanged: _preview, onChangeEnd: _save)
/// ```
class OmiSlider extends StatelessWidget {
  const OmiSlider({
    super.key,
    required this.value,
    required this.onChanged,
    this.onChangeEnd,
    this.min = 0,
    this.max = 1,
    this.divisions,
    this.semanticFormatterCallback,
  });

  final double value;

  /// Null disables the slider.
  final ValueChanged<double>? onChanged;
  final ValueChanged<double>? onChangeEnd;
  final double min;
  final double max;
  final int? divisions;

  /// What a screen reader announces for a value (e.g. "60%" or "+6dB").
  final SemanticFormatterCallback? semanticFormatterCallback;

  @override
  Widget build(BuildContext context) {
    return SliderTheme(
      data: SliderThemeData(
        trackHeight: 4,
        activeTrackColor: OmiColors.textPrimary,
        inactiveTrackColor: OmiColors.surface4,
        disabledActiveTrackColor: OmiColors.textTertiary,
        disabledInactiveTrackColor: OmiColors.surface3,
        activeTickMarkColor: Colors.transparent,
        inactiveTickMarkColor: Colors.transparent,
        disabledActiveTickMarkColor: Colors.transparent,
        disabledInactiveTickMarkColor: Colors.transparent,
        thumbColor: Colors.white,
        disabledThumbColor: Colors.white,
        trackShape: const _OmiTrackShape(),
        thumbShape: const _OmiThumbShape(),
        overlayShape: SliderComponentShape.noOverlay,
        showValueIndicator: ShowValueIndicator.never,
      ),
      child: SizedBox(
        height: 28,
        child: Slider(
          value: value.clamp(min, max),
          min: min,
          max: max,
          divisions: divisions,
          onChanged: onChanged,
          onChangeEnd: onChangeEnd,
          semanticFormatterCallback: semanticFormatterCallback,
        ),
      ),
    );
  }
}

/// One height for both halves of the track (Material thickens the filled half by 2pt).
class _OmiTrackShape extends RoundedRectSliderTrackShape {
  const _OmiTrackShape();

  @override
  void paint(
    PaintingContext context,
    Offset offset, {
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required Animation<double> enableAnimation,
    required TextDirection textDirection,
    required Offset thumbCenter,
    Offset? secondaryOffset,
    bool isDiscrete = false,
    bool isEnabled = false,
    double additionalActiveTrackHeight = 2,
  }) {
    super.paint(
      context,
      offset,
      parentBox: parentBox,
      sliderTheme: sliderTheme,
      enableAnimation: enableAnimation,
      textDirection: textDirection,
      thumbCenter: thumbCenter,
      secondaryOffset: secondaryOffset,
      isDiscrete: isDiscrete,
      isEnabled: isEnabled,
      additionalActiveTrackHeight: 0,
    );
  }
}

/// A 26pt white knob: `0 3px 8px rgba(0,0,0,.35)` shadow and a 0.5pt ring.
class _OmiThumbShape extends SliderComponentShape {
  const _OmiThumbShape();

  static const double _radius = 13;

  @override
  Size getPreferredSize(bool isEnabled, bool isDiscrete) => const Size.fromRadius(_radius);

  @override
  void paint(
    PaintingContext context,
    Offset center, {
    required Animation<double> activationAnimation,
    required Animation<double> enableAnimation,
    required bool isDiscrete,
    required TextPainter labelPainter,
    required RenderBox parentBox,
    required SliderThemeData sliderTheme,
    required TextDirection textDirection,
    required double value,
    required double textScaleFactor,
    required Size sizeWithOverflow,
  }) {
    final canvas = context.canvas;
    canvas.drawCircle(
      center.translate(0, 3),
      _radius,
      Paint()
        ..color = const Color(0x59000000)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4),
    );
    canvas.drawCircle(center, _radius, Paint()..color = sliderTheme.thumbColor ?? Colors.white);
    canvas.drawCircle(
      center,
      _radius,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.5
        ..color = const Color(0x1A000000),
    );
  }
}
