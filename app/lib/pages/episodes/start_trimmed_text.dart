import 'package:characters/characters.dart';
import 'package:flutter/material.dart';

/// One run of [StartTrimmedText]: its words and, optionally, its own style.
typedef TrimmedRun = ({String text, TextStyle? style});

/// Running text that keeps its newest words visible: when the runs do not fit
/// in [maxLines], the oldest words are dropped and a leading "…" stands in for
/// them, so a live line reads "…the words just said" instead of ending mid-sentence.
/// Cuts prefer word boundaries, falling back to graphemes for unspaced text.
class StartTrimmedText extends StatelessWidget {
  const StartTrimmedText({super.key, required this.runs, required this.style, this.maxLines = 1});

  final List<TrimmedRun> runs;
  final TextStyle style;
  final int maxLines;

  /// Only the tail can ever show; measuring more than this is wasted layout.
  static const _maxChars = 600;

  @override
  Widget build(BuildContext context) {
    final scaler = MediaQuery.textScalerOf(context);
    final direction = Directionality.of(context);
    // Measured exactly as drawn: the ambient face and size under this widget's own style.
    final effective = DefaultTextStyle.of(context).style.merge(style);
    return LayoutBuilder(
      builder: (context, constraints) {
        final full = runs.map((r) => r.text).join();
        var start = full.length > _maxChars ? full.length - _maxChars : 0;
        bool fits(int from) {
          final painter = TextPainter(
            text: _span(from, from > 0, effective),
            maxLines: maxLines,
            textScaler: scaler,
            textDirection: direction,
          )..layout(maxWidth: constraints.maxWidth);
          final ok = !painter.didExceedMaxLines;
          painter.dispose();
          return ok;
        }

        if (start > 0 || !fits(0)) {
          // Word starts after [start]; the later the cut, the shorter the text, so the first
          // start that fits is found by bisection.
          final graphemeCuts = <int>[];
          final wordCuts = <int>[];
          var offset = 0;
          var afterSpace = false;
          for (final character in full.characters) {
            if (offset > start) {
              graphemeCuts.add(offset);
              if (afterSpace && character.trim().isNotEmpty) wordCuts.add(offset);
            }
            offset += character.length;
            afterSpace = character.trim().isEmpty;
          }
          int? firstFit(List<int> cuts) {
            var lo = 0, hi = cuts.length;
            while (lo < hi) {
              final mid = (lo + hi) >> 1;
              if (fits(cuts[mid])) {
                hi = mid;
              } else {
                lo = mid + 1;
              }
            }
            return lo < cuts.length ? cuts[lo] : null;
          }

          start = firstFit(wordCuts) ?? firstFit(graphemeCuts) ?? full.length;
        }
        return Text.rich(
          _span(start, start > 0, effective),
          maxLines: maxLines,
          overflow: TextOverflow.ellipsis,
        );
      },
    );
  }

  TextSpan _span(int from, bool trimmed, TextStyle style) {
    final children = <TextSpan>[if (trimmed) const TextSpan(text: '…')];
    var offset = 0;
    for (final run in runs) {
      final end = offset + run.text.length;
      if (end > from) {
        children.add(TextSpan(text: run.text.substring(from > offset ? from - offset : 0), style: run.style));
      }
      offset = end;
    }
    return TextSpan(style: style, children: children);
  }
}
