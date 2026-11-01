import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'package:omi/pages/onboarding/variants/yinka/activation/activation_visuals.dart';
import 'package:omi/ui/ui.dart';

/// Lower-case words without punctuation, for comparing what was said with the script.
List<String> activationTokens(String text) => text
    .toLowerCase()
    .split(RegExp(r'\s+'))
    .map((w) => w.replaceAll(RegExp(r"[^\p{L}\p{N}']", unicode: true), ''))
    .where((w) => w.isNotEmpty)
    .toList();

/// How much of [script] the reader has said, judging by [heard]: the script index just past the last
/// heard word found in order, and the share of heard words that were found. A low share means the
/// reader is saying something else.
({int reached, double match}) readAlongProgress(List<String> script, List<String> heard) {
  if (heard.isEmpty) return (reached: 0, match: 1);
  var i = 0;
  var found = 0;
  var reached = 0;
  for (final word in heard) {
    // Look a few words ahead, so a skipped or misheard word doesn't lose the place.
    for (var j = i; j < script.length && j < i + 4; j++) {
      if (script[j] == word) {
        found++;
        i = j + 1;
        reached = i;
        break;
      }
    }
  }
  return (reached: reached, match: found / heard.length);
}

/// The dictation card. Before Omi's words come back (they come a sentence at a time), the script
/// lights up word by word while the reader's voice is heard, with a soft tick per word, and waits
/// when they pause. When a sentence arrives it either confirms the script (the lit words turn solid)
/// or, when the reader said something else, their own words ink in instead. A waveform along the
/// bottom moves with the voice from the first moment.
class ReadAlongCard extends StatefulWidget {
  const ReadAlongCard({
    super.key,
    required this.script,
    required this.live,
    required this.level,
    required this.listening,
    required this.style,
    this.levelDriven = true,
  });

  final String script;

  /// What Omi heard so far (whole sentences).
  final ValueListenable<String> live;

  /// Voice loudness, 0..1.
  final ValueListenable<double> level;
  final bool listening;
  final TextStyle style;

  /// False when the voice level is not available (talking through the Omi): the highlight then
  /// moves at speaking pace, a few words ahead of what Omi confirmed at most.
  final bool levelDriven;

  @override
  State<ReadAlongCard> createState() => _ReadAlongCardState();
}

class _ReadAlongCardState extends State<ReadAlongCard> with SingleTickerProviderStateMixin {
  static const _wordsPerSecond = 2.6;
  static const _voiceThreshold = 0.1;
  static const _bars = 32;

  late final List<String> _scriptWords = widget.script.split(RegExp(r'\s+'));
  late final List<String> _scriptTokens = activationTokens(widget.script);
  late final Ticker _ticker = createTicker(_tick);
  Duration _last = Duration.zero;

  /// Words lit so far (fractional while one is lighting).
  double _cursor = 0;
  int _confirmed = 0;
  bool _ownWords = false;
  DateTime _lastTick = DateTime.fromMillisecondsSinceEpoch(0);
  final List<double> _history = List.filled(_bars, 0, growable: true);
  double _sinceSample = 0;

  /// When each word was heard by Omi (script index, or own-word index): drives its flash.
  final Map<int, DateTime> _heardAt = {};
  int _ownSeen = 0;
  static const _flash = Duration(milliseconds: 750);

  @override
  void initState() {
    super.initState();
    widget.live.addListener(_onLive);
    _ticker.start();
  }

  @override
  void dispose() {
    widget.live.removeListener(_onLive);
    _ticker.dispose();
    super.dispose();
  }

  void _onLive() {
    final heard = activationTokens(widget.live.value);
    final p = readAlongProgress(_scriptTokens, heard);
    final now = DateTime.now();
    var landed = false;
    setState(() {
      if (heard.length >= 3 && p.match < 0.5) {
        _ownWords = true;
      }
      if (_ownWords) {
        final count = widget.live.value.trim().split(RegExp(r'\s+')).length;
        for (var i = _ownSeen; i < count; i++) {
          _heardAt[i] = now.add(Duration(milliseconds: 45 * (i - _ownSeen)));
        }
        landed = count > _ownSeen;
        _ownSeen = math.max(_ownSeen, count);
      } else if (p.reached > _confirmed) {
        // Omi's words landed: each newly heard word flashes in turn.
        for (var i = _confirmed; i < p.reached; i++) {
          _heardAt[i] = now.add(Duration(milliseconds: 45 * (i - _confirmed)));
        }
        _confirmed = p.reached;
        _cursor = math.max(_cursor, _confirmed.toDouble());
        landed = true;
      }
    });
    if (landed) OmiHaptics.light();
  }

  /// 1 the moment a word is heard by Omi, easing to 0 over [_flash]; 0 when not flashing.
  double _flashOf(int i) {
    final at = _heardAt[i];
    if (at == null) return 0;
    final ms = DateTime.now().difference(at).inMilliseconds;
    if (ms < 0) return 0;
    return 1 - Curves.easeOut.transform((ms / _flash.inMilliseconds).clamp(0.0, 1.0));
  }

  bool get _flashing {
    final now = DateTime.now();
    return _heardAt.values.any((at) => now.difference(at) < _flash + const Duration(milliseconds: 600));
  }

  void _tick(Duration now) {
    final dt = (now - _last).inMicroseconds / 1e6;
    _last = now;
    if (dt <= 0 || dt > 0.25) return;
    final level = widget.level.value;
    _sinceSample += dt;
    var changed = false;
    if (_sinceSample >= 0.06) {
      _sinceSample = 0;
      _history.removeAt(0);
      _history.add(widget.listening ? level : 0);
      changed = true;
    }
    if (widget.listening && !_ownWords) {
      final speaking = widget.levelDriven ? level > _voiceThreshold : true;
      final cap = widget.levelDriven
          ? _scriptWords.length.toDouble()
          : math.min<double>(_scriptWords.length.toDouble(), _confirmed + 6.0);
      if (speaking && _cursor < cap) {
        final before = _cursor.floor();
        _cursor = math.min<double>(cap, _cursor + dt * _wordsPerSecond);
        if (_cursor.floor() > before) _wordTick();
        changed = true;
      }
    }
    if ((changed || _flashing) && mounted) setState(() {});
  }

  void _wordTick() {
    final now = DateTime.now();
    if (now.difference(_lastTick).inMilliseconds < 80) return;
    _lastTick = now;
    OmiHaptics.selection();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return NoteCard(
      minHeight: 150,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedSwitcher(
            duration: Duration(milliseconds: reduce ? 0 : 280),
            child: _ownWords ? _own(reduce) : _scripted(reduce),
          ),
          const SizedBox(height: OmiSpacing.md),
          SizedBox(height: 22, child: CustomPaint(painter: _Waveform(_history, OmiColors.textPrimary))),
        ],
      ),
    );
  }

  Widget _scripted(bool reduce) {
    return Wrap(
      key: const ValueKey('script'),
      children: [
        for (var i = 0; i < _scriptWords.length; i++) _word(i, reduce),
      ],
    );
  }

  /// Three clear states: not said yet (faint), heard by the microphone but not yet by Omi (grey),
  /// and heard by Omi (full ink, arriving with a flash behind it).
  Widget _word(int i, bool reduce) {
    final lit = (_cursor - i).clamp(0.0, 1.0);
    final confirmed = i < _confirmed;
    final color = confirmed
        ? OmiColors.textPrimary
        : Color.lerp(OmiColors.textTertiary.withValues(alpha: 0.55), OmiColors.textSecondary, lit)!;
    // A word lifts a touch as the voice lights it, then settles.
    final lift = reduce || confirmed ? 0.0 : -2.0 * math.sin(math.pi * lit);
    return _flashWord(Text('${_scriptWords[i]} ', style: widget.style.copyWith(color: color)), reduce ? 0 : _flashOf(i),
        lift: lift);
  }

  /// The moment Omi hears a word: a soft highlight behind it and a small pop, fading out.
  Widget _flashWord(Widget word, double f, {double lift = 0}) {
    return Transform.translate(
      offset: Offset(0, lift),
      child: Transform.scale(
        scale: 1 + 0.07 * f,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: OmiColors.textPrimary.withValues(alpha: 0.14 * f),
            borderRadius: OmiRadius.smAll,
          ),
          child: word,
        ),
      ),
    );
  }

  Widget _own(bool reduce) {
    final words = widget.live.value.trim().split(RegExp(r'\s+'));
    return Wrap(
      key: const ValueKey('own'),
      children: [
        for (var i = 0; i < words.length; i++)
          TweenAnimationBuilder<double>(
            key: ValueKey('own_$i'),
            tween: Tween(begin: reduce ? 1 : 0, end: 1),
            duration: Duration(milliseconds: 260 + 30 * (i % 6)),
            curve: Curves.easeOutCubic,
            builder: (context, t, child) => Opacity(
              opacity: t,
              child: Transform.translate(offset: Offset(0, 6 * (1 - t)), child: child),
            ),
            child: _flashWord(
              Text('${words[i]} ', style: widget.style.copyWith(color: OmiColors.textPrimary)),
              reduce ? 0 : _flashOf(i),
            ),
          ),
      ],
    );
  }
}

/// Rounded bars of the last couple of seconds of voice, newest on the right.
class _Waveform extends CustomPainter {
  _Waveform(List<double> history, this.color) : history = List.of(history);

  final List<double> history;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final n = history.length;
    final gap = size.width / n;
    final w = math.min(3.0, gap * 0.5);
    for (var i = 0; i < n; i++) {
      final v = history[i].clamp(0.0, 1.0);
      final h = 3 + (size.height - 3) * v;
      final x = gap * i + gap / 2;
      final paint = Paint()..color = color.withValues(alpha: 0.18 + 0.7 * v);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset(x, size.height / 2), width: w, height: h), Radius.circular(w)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _Waveform old) => !listEquals(old.history, history) || old.color != color;
}

const _fillerWords = {
  'a',
  'an',
  'the',
  'and',
  'or',
  'but',
  'so',
  'to',
  'of',
  'in',
  'on',
  'at',
  'by',
  'for',
  'with',
  'from',
  'just',
  'had',
  'have',
  'has',
  'is',
  'was',
  'are',
  'be',
  'me',
  'my',
  'i',
  'im',
  "i'm",
  'she',
  'he',
  'they',
  'we',
  'you',
  'it',
  'its',
  "it's",
  "she's",
  "he's",
  'that',
  'this',
  'then',
  'um',
  'uh',
  'like',
  'really',
  'also',
  'way',
  'up',
  'out',
  'about',
  'remind',
  'grab',
  'get',
  'pick',
};

/// "Summarizing…": the reader's words stay in the same card and visibly condense. Filler words fade
/// and fold away, the words that matter draw together and darken, and the card shrinks around them;
/// then a light passes over what is left while Omi finishes.
class CompactingCard extends StatefulWidget {
  const CompactingCard({super.key, required this.text, required this.style});

  final String text;
  final TextStyle style;

  @override
  State<CompactingCard> createState() => _CompactingCardState();
}

class _CompactingCardState extends State<CompactingCard> with TickerProviderStateMixin {
  late final AnimationController _fold = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))
    ..forward();
  late final AnimationController _sweep =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));
  late final List<String> _words = widget.text.trim().split(RegExp(r'\s+'));
  late final List<bool> _keep = [
    for (final w in _words)
      () {
        final t = activationTokens(w);
        return t.isNotEmpty && !_fillerWords.contains(t.first) && t.first.length > 2;
      }(),
  ];

  @override
  void initState() {
    super.initState();
    _fold.addStatusListener((s) {
      if (s == AnimationStatus.completed && mounted) _sweep.repeat();
    });
  }

  @override
  void dispose() {
    _fold.dispose();
    _sweep.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    if (reduce) {
      return NoteCard(
        minHeight: 150,
        child: Text(
          [
            for (var i = 0; i < _words.length; i++)
              if (_keep[i]) _words[i]
          ].join(' '),
          style: widget.style.copyWith(color: OmiColors.textPrimary),
        ),
      );
    }
    return AnimatedBuilder(
      animation: Listenable.merge([_fold, _sweep]),
      builder: (context, _) {
        final f = Curves.easeInOutCubic.transform(_fold.value);
        final words = Wrap(
          children: [
            for (var i = 0; i < _words.length; i++)
              if (_keep[i]) _kept(i, f) else _dropped(i, f),
          ],
        );
        return AnimatedSize(
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOutCubic,
          alignment: Alignment.topCenter,
          child: NoteCard(
            // The card lets go of its minimum height as the words fold, so it shrinks around them.
            minHeight: 150 * (1 - f) + 60 * f,
            child: _fold.isCompleted ? _withSweep(words) : words,
          ),
        );
      },
    );
  }

  /// Each dropped word starts going a little after the one before, so the folding travels along.
  Widget _dropped(int i, double f) {
    final start = (i / _words.length) * 0.5;
    final t = ((f - start) / 0.5).clamp(0.0, 1.0);
    return ClipRect(
      child: Align(
        alignment: Alignment.centerLeft,
        widthFactor: 1 - t,
        heightFactor: 1,
        child: Opacity(
          opacity: (1 - t * 1.6).clamp(0.0, 1.0),
          child: Text('${_words[i]} ', style: widget.style.copyWith(color: OmiColors.textTertiary)),
        ),
      ),
    );
  }

  Widget _kept(int i, double f) {
    final color = Color.lerp(OmiColors.textSecondary, OmiColors.textPrimary, f)!;
    return Text(
      '${_words[i]} ',
      style: widget.style.copyWith(color: color, fontWeight: FontWeight.lerp(FontWeight.w400, FontWeight.w600, f)),
    );
  }

  Widget _withSweep(Widget child) {
    final x = -1.0 + 3.0 * _sweep.value;
    return ShaderMask(
      blendMode: BlendMode.srcATop,
      shaderCallback: (bounds) => LinearGradient(
        begin: Alignment(x - 1, -0.2),
        end: Alignment(x + 1, 0.2),
        colors: [
          OmiColors.surface1.withValues(alpha: 0),
          OmiColors.surface1.withValues(alpha: 0.75),
          OmiColors.surface1.withValues(alpha: 0)
        ],
        stops: const [0.35, 0.5, 0.65],
      ).createShader(bounds),
      child: child,
    );
  }
}

/// Where the ✓ was while Omi writes: the same dark circle, holding three lines that shorten into
/// one and grow back, over and over — notes condensing.
class CondensingControl extends StatefulWidget {
  const CondensingControl({super.key});

  @override
  State<CondensingControl> createState() => _CondensingControlState();
}

class _CondensingControlState extends State<CondensingControl> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1600))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduce = OmiMotion.of(context).emphasized == Duration.zero;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 140,
          height: 140,
          child: Center(
            child: Container(
              width: 68,
              height: 68,
              decoration: BoxDecoration(color: OmiColors.accent, shape: BoxShape.circle),
              child: AnimatedBuilder(
                animation: _c,
                builder: (context, _) => CustomPaint(
                  painter: _CondensingLines(t: reduce ? 0.5 : _c.value, color: OmiColors.onAccent),
                ),
              ),
            ),
          ),
        ),
        // Keeps the circle level with the ✓ it replaces (which has a status line under it).
        const SizedBox(height: OmiSpacing.xs + 20),
      ],
    );
  }
}

class _CondensingLines extends CustomPainter {
  _CondensingLines({required this.t, required this.color});

  final double t;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    // 0→0.5: three lines draw together into one short line; 0.5→1: they spread back out.
    final phase = t < 0.5 ? Curves.easeInOutCubic.transform(t * 2) : 1 - Curves.easeInOutCubic.transform((t - 0.5) * 2);
    final c = size.center(Offset.zero);
    final paint = Paint()
      ..color = color
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3;
    const widths = [26.0, 20.0, 14.0];
    for (var k = 0; k < 3; k++) {
      final y = c.dy + (k - 1) * 8 * (1 - phase);
      final w = widths[k] * (1 - phase) + 18 * phase;
      canvas.drawLine(Offset(c.dx - w / 2, y), Offset(c.dx + w / 2, y),
          paint..color = color.withValues(alpha: k == 1 ? 1 : 1 - 0.6 * phase));
    }
  }

  @override
  bool shouldRepaint(covariant _CondensingLines old) => old.t != t || old.color != color;
}

/// The summary's entrance: the card comes up out of a soft blur, then a light passes across it once.
class SummaryReveal extends StatefulWidget {
  const SummaryReveal({super.key, required this.child});

  final Widget child;

  @override
  State<SummaryReveal> createState() => _SummaryRevealState();
}

class _SummaryRevealState extends State<SummaryReveal> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1500))
    ..forward();
  Timer? _done;

  @override
  void initState() {
    super.initState();
    _done = Timer(const Duration(milliseconds: 1250), OmiHaptics.medium);
  }

  @override
  void dispose() {
    _done?.cancel();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (OmiMotion.of(context).emphasized == Duration.zero) return widget.child;
    return AnimatedBuilder(
      animation: _c,
      child: widget.child,
      builder: (context, child) {
        final v = _c.value;
        final appear = Curves.easeOutCubic.transform((v / 0.45).clamp(0.0, 1.0));
        final sweep = ((v - 0.55) / 0.45).clamp(0.0, 1.0);
        // The blur only runs during the 450 ms entrance; once settled the card is drawn plain.
        final Widget settled = appear >= 1
            ? child!
            : ImageFiltered(
                // omi-perf-allow: blur-filter -- one-shot entrance of a single card, gone when appear == 1; never in a list
                imageFilter: ImageFilter.blur(sigmaX: 12 * (1 - appear), sigmaY: 12 * (1 - appear)),
                child: child,
              );
        Widget out = Opacity(opacity: appear, child: Transform.scale(scale: 0.94 + 0.06 * appear, child: settled));
        if (sweep > 0 && sweep < 1) {
          final x = -1.5 + 3.0 * Curves.easeInOut.transform(sweep);
          out = ShaderMask(
            blendMode: BlendMode.srcATop,
            shaderCallback: (bounds) => LinearGradient(
              begin: Alignment(x - 0.6, -1),
              end: Alignment(x + 0.6, 1),
              colors: [
                OmiColors.surface1.withValues(alpha: 0),
                OmiColors.surface1.withValues(alpha: 0.6),
                OmiColors.surface1.withValues(alpha: 0)
              ],
            ).createShader(bounds),
            child: out,
          );
        }
        return out;
      },
    );
  }
}

/// One line of a summary: a heading (`## …`), a bullet (`- …`), or plain text.
@visibleForTesting
typedef SummaryLine = ({String text, bool heading, bool bullet});

/// Omi's notes arrive as light markdown; the onboarding card shows them as text: headings become
/// short bold lines, `-`/`*` items become bullets, emphasis markers go, blank lines collapse.
@visibleForTesting
List<SummaryLine> summaryLines(String markdown) {
  final out = <SummaryLine>[];
  for (final raw in markdown.split('\n')) {
    var line = raw.trim();
    if (line.isEmpty) continue;
    line = line.replaceAll('**', '').replaceAll('__', '');
    final heading = RegExp(r'^#{1,6}\s+').firstMatch(line);
    final bullet = RegExp(r'^([-*•]|\d+[.)])\s+').firstMatch(line);
    if (heading != null) {
      out.add((text: line.substring(heading.end).trim(), heading: true, bullet: false));
    } else if (bullet != null) {
      out.add((text: line.substring(bullet.end).trim(), heading: false, bullet: true));
    } else {
      out.add((text: line, heading: false, bullet: false));
    }
  }
  return out;
}

/// The summary in the onboarding card, written in word by word ([t] 0→1) across its lines, in a
/// box that never grows past [maxHeight]: longer notes scroll inside it, with a fade at the bottom.
class SummaryText extends StatelessWidget {
  const SummaryText({super.key, required this.text, required this.t, required this.style, this.maxHeight = 190});

  final String text;
  final double t;
  final TextStyle style;
  final double maxHeight;

  @override
  Widget build(BuildContext context) {
    final lines = summaryLines(text);
    final total = lines.fold<int>(0, (n, l) => n + l.text.split(' ').length);
    final shown = (total * t).ceil();
    var index = 0;
    final children = <Widget>[];
    for (var k = 0; k < lines.length; k++) {
      final line = lines[k];
      final lineStyle = line.heading ? style.copyWith(fontWeight: FontWeight.w600) : style;
      final words = line.text.split(' ');
      final spans = <TextSpan>[
        if (line.bullet)
          TextSpan(text: '•  ', style: lineStyle.copyWith(color: index < shown ? null : Colors.transparent)),
        for (var i = 0; i < words.length; i++)
          TextSpan(
            text: i == words.length - 1 ? words[i] : '${words[i]} ',
            style: lineStyle.copyWith(
              color: index + i < shown ? lineStyle.color : lineStyle.color?.withValues(alpha: 0),
            ),
          ),
      ];
      index += words.length;
      children.add(Padding(
        padding: EdgeInsets.only(top: k == 0 ? 0 : (line.heading ? OmiSpacing.md : OmiSpacing.xs)),
        child: Text.rich(TextSpan(children: spans)),
      ));
    }
    final column =
        Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: children);
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: maxHeight),
      child: ShaderMask(
        blendMode: BlendMode.dstIn,
        shaderCallback: (bounds) => LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: const [Colors.black, Colors.black, Colors.transparent],
          stops: [0, bounds.height >= maxHeight - 1 ? 0.82 : 1, 1],
        ).createShader(bounds),
        child: SingleChildScrollView(physics: const ClampingScrollPhysics(), child: column),
      ),
    );
  }
}
