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
class FadeInWordsText extends StatefulWidget {
  final String text;
  final TextStyle? style;
  final WrapAlignment alignment;

  /// How long one word takes to fade from transparent to opaque.
  final Duration wordDuration;

  /// Delay between consecutive new words starting their fade.
  final Duration stagger;

  const FadeInWordsText({
    super.key,
    required this.text,
    this.style,
    this.alignment = WrapAlignment.center,
    this.wordDuration = const Duration(milliseconds: 350),
    this.stagger = const Duration(milliseconds: 90),
  });

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
    return Wrap(
      alignment: widget.alignment,
      spacing: gap,
      runSpacing: 0,
      children: [
        for (var i = 0; i < _words.length; i++)
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
