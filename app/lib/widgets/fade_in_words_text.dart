import 'dart:async';

import 'package:flutter/material.dart';

/// Renders a growing transcript so that newly arrived words fade in one after
/// another instead of the whole string snapping onto the screen.
///
/// Words already on screen keep their place and stay fully visible; only the
/// words appended since the previous [text] animate. When [text] no longer
/// extends the previous value (a new question cleared it, or a correction
/// rewrote earlier words) every word is treated as new and revealed again.
/// Layout is a centered [Wrap], so it reads the same as a centered [Text] but
/// each word can carry its own opacity.
///
/// With [visibleLines] set, only the words on the last that many lines are
/// built: earlier lines drop off whole, so the widget never needs a clipped
/// or scrolled viewport (which would show a sliver of the line above) and
/// words keep their reveal state while they stay on screen.
class FadeInWordsText extends StatefulWidget {
  final String text;
  final TextStyle? style;
  final WrapAlignment alignment;

  /// Show only the last this-many lines of text; null shows everything.
  final int? visibleLines;

  /// How long one word takes to fade from transparent to opaque.
  final Duration wordDuration;

  /// Delay between consecutive new words starting their fade.
  final Duration stagger;

  const FadeInWordsText({
    super.key,
    required this.text,
    this.style,
    this.alignment = WrapAlignment.center,
    this.visibleLines,
    this.wordDuration = const Duration(milliseconds: 350),
    this.stagger = const Duration(milliseconds: 90),
  }) : assert(visibleLines == null || visibleLines > 0);

  /// Index of the first word on the last [visibleLines] lines, replaying the
  /// [Wrap] line breaking with measured word widths. Breaks a hair early
  /// (1 px) so the real Wrap never ends up with one line more than allowed.
  static int firstVisibleWord({
    required List<String> words,
    required TextStyle style,
    required double gap,
    required double maxWidth,
    required int visibleLines,
    required TextScaler textScaler,
    required TextDirection textDirection,
  }) {
    if (!maxWidth.isFinite) return 0;
    final lineStarts = <int>[0];
    var lineWidth = 0.0;
    for (var i = 0; i < words.length; i++) {
      final painter = TextPainter(
        text: TextSpan(text: words[i], style: style),
        textDirection: textDirection,
        textScaler: textScaler,
      )..layout();
      final width = painter.width;
      painter.dispose();
      final needed = lineWidth == 0 ? width : lineWidth + gap + width;
      if (lineWidth > 0 && needed > maxWidth - 1) {
        lineStarts.add(i);
        lineWidth = width;
      } else {
        lineWidth = needed;
      }
    }
    if (lineStarts.length <= visibleLines) return 0;
    return lineStarts[lineStarts.length - visibleLines];
  }

  @override
  State<FadeInWordsText> createState() => _FadeInWordsTextState();
}

class _FadeInWordsTextState extends State<FadeInWordsText> {
  List<String> _words = const [];

  /// Indices whose fade has been started (opacity target 1.0).
  final Set<int> _revealed = {};
  final List<Timer> _timers = [];

  static List<String> _split(String text) => text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

  @override
  void initState() {
    super.initState();
    _words = _split(widget.text);
    _scheduleReveal(from: 0);
  }

  @override
  void didUpdateWidget(covariant FadeInWordsText oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.text == widget.text) return;

    final next = _split(widget.text);
    final extendsPrevious =
        next.length >= _words.length && List.generate(_words.length, (i) => next[i] == _words[i]).every((same) => same);

    if (extendsPrevious) {
      final firstNew = _words.length;
      _words = next;
      _scheduleReveal(from: firstNew);
    } else {
      _cancelTimers();
      _revealed.clear();
      _words = next;
      _scheduleReveal(from: 0);
    }
  }

  void _scheduleReveal({required int from}) {
    for (var i = from; i < _words.length; i++) {
      final index = i;
      final delay = widget.stagger * (index - from);
      if (delay == Duration.zero) {
        // Let the first new word render transparent for one frame so the
        // fade is visible instead of appearing already opaque.
        _timers.add(Timer(Duration.zero, () => _reveal(index)));
      } else {
        _timers.add(Timer(delay, () => _reveal(index)));
      }
    }
  }

  void _reveal(int index) {
    if (!mounted) return;
    setState(() => _revealed.add(index));
  }

  void _cancelTimers() {
    for (final timer in _timers) {
      timer.cancel();
    }
    _timers.clear();
  }

  @override
  void dispose() {
    _cancelTimers();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_words.isEmpty) return const SizedBox.shrink();
    final style = widget.style ?? DefaultTextStyle.of(context).style;
    // A regular space glyph keeps word gaps identical to a plain Text run.
    final gap = (style.fontSize ?? 14) * 0.3;
    final visibleLines = widget.visibleLines;
    if (visibleLines == null) return _wrap(from: 0, style: style, gap: gap);
    // Each word's Text inherits the ambient DefaultTextStyle (font family,
    // weight, ...) under [style], so measure with that same effective style
    // or the replayed line breaks drift from the real ones.
    final effective = DefaultTextStyle.of(context).style.merge(style);
    return LayoutBuilder(
      builder: (context, constraints) {
        final from = FadeInWordsText.firstVisibleWord(
          words: _words,
          style: effective,
          gap: gap,
          maxWidth: constraints.maxWidth,
          visibleLines: visibleLines,
          textScaler: MediaQuery.textScalerOf(context),
          textDirection: Directionality.of(context),
        );
        return _wrap(from: from, style: style, gap: gap);
      },
    );
  }

  Widget _wrap({required int from, required TextStyle style, required double gap}) {
    return Wrap(
      alignment: widget.alignment,
      spacing: gap,
      runSpacing: 0,
      children: [
        for (var i = from; i < _words.length; i++)
          AnimatedOpacity(
            key: ValueKey('fade-word-$i'),
            opacity: _revealed.contains(i) ? 1.0 : 0.0,
            duration: widget.wordDuration,
            curve: Curves.easeOut,
            child: Text(_words[i], style: style),
          ),
      ],
    );
  }
}
