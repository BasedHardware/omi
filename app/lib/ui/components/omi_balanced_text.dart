import 'package:flutter/widgets.dart';

/// Short UI copy that wraps into even lines instead of leaving one word alone on the last line
/// (CSS `text-wrap: balance`): "Start with this phone, or connect / a device to listen all day."
/// rather than "… to listen all / day.".
///
/// A card whose copy changes with state keeps its height when [reserveFor] names the other copy it
/// can show ("Start with this phone, or connect a device…" and "Pendant · Ready"): the text holds
/// the height of the tallest of them at this width and text size, so nothing below it moves.
/// [minLines] holds at least that many lines. For titles, card subtitles and empty states — not for
/// long prose or user text.
class OmiBalancedText extends StatelessWidget {
  const OmiBalancedText(
    this.data, {
    super.key,
    this.style,
    this.textAlign,
    this.maxLines,
    this.minLines = 1,
    this.reserveFor = const [],
    this.overflow,
  });

  final String data;
  final TextStyle? style;
  final TextAlign? textAlign;
  final int? maxLines;
  final int minLines;
  final List<String> reserveFor;
  final TextOverflow? overflow;

  /// The narrowest width, at most [maxWidth], at which [painter]'s text still takes the lines it
  /// takes at [maxWidth]: the lines come out even. Returns [maxWidth] for one line or a clipped text.
  static double balancedWidth(TextPainter painter, double maxWidth) {
    painter.layout(maxWidth: maxWidth);
    final lines = painter.computeLineMetrics().length;
    if (!maxWidth.isFinite || lines < 2 || painter.didExceedMaxLines) return maxWidth;
    var fits = maxWidth;
    var tooNarrow = 0.0;
    while (fits - tooNarrow > 1) {
      final width = (fits + tooNarrow) / 2;
      painter.layout(maxWidth: width);
      if (painter.computeLineMetrics().length > lines || painter.didExceedMaxLines) {
        tooNarrow = width;
      } else {
        fits = width;
      }
    }
    return fits.ceilToDouble().clamp(0, maxWidth);
  }

  @override
  Widget build(BuildContext context) {
    final resolved = DefaultTextStyle.of(context).style.merge(style);
    final scaler = MediaQuery.textScalerOf(context);
    final direction = Directionality.of(context);
    final locale = Localizations.maybeLocaleOf(context);
    final centered = textAlign == TextAlign.center;
    return LayoutBuilder(
      builder: (context, constraints) {
        final painter = TextPainter(
          text: TextSpan(text: data, style: resolved),
          textDirection: direction,
          textScaler: scaler,
          maxLines: maxLines,
          locale: locale,
        );
        final width = balancedWidth(painter, constraints.maxWidth);
        var reserved = painter.preferredLineHeight * minLines;
        for (final other in reserveFor) {
          painter
            ..text = TextSpan(text: other, style: resolved)
            ..layout(maxWidth: constraints.maxWidth);
          if (painter.height > reserved) reserved = painter.height;
        }
        painter.dispose();
        return ConstrainedBox(
          constraints: BoxConstraints(minHeight: reserved),
          child: Align(
            alignment: centered ? Alignment.topCenter : AlignmentDirectional.topStart,
            heightFactor: 1,
            child: SizedBox(
              width: width.isFinite ? width : null,
              child: Text(data, style: style, textAlign: textAlign, maxLines: maxLines, overflow: overflow),
            ),
          ),
        );
      },
    );
  }
}
