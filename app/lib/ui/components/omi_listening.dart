import 'dart:async';
import 'dart:io' show Platform;
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Whether endless loops (the listening wave, the Ask ring's orbit, the orb's breathing LED) may
/// run. They stop under Reduce Motion, and never run under `flutter test`, where an endless
/// animation would keep `pumpAndSettle` from ever settling (the app already reads FLUTTER_TEST the
/// same way in preferences and capture composition).
bool omiLoopsEnabled(BuildContext context) {
  if (MediaQuery.maybeDisableAnimationsOf(context) ?? false) return false;
  if (kIsWeb) return true;
  return !Platform.environment.containsKey('FLUTTER_TEST');
}

/// The Omi orb (Liquid Dock): the device's dark dome seen straight on, one LED near its top that
/// breathes in the live blue while audio is captured. Grey and still otherwise.
class OmiOrb extends StatefulWidget {
  const OmiOrb({super.key, this.size = 30, this.live = true});

  final double size;
  final bool live;

  @override
  State<OmiOrb> createState() => _OmiOrbState();
}

class _OmiOrbState extends State<OmiOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _breath =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2400));

  void _sync() {
    final run = widget.live && omiLoopsEnabled(context);
    if (run && !_breath.isAnimating) {
      _breath.repeat();
    } else if (!run && _breath.isAnimating) {
      _breath
        ..stop()
        ..value = 0;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(OmiOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  @override
  void dispose() {
    _breath.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.size;
    final led = math.max(4.0, s * 0.13);
    return ExcludeSemantics(
      child: SizedBox.square(
        dimension: s,
        child: DecoratedBox(
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              center: Alignment(0.36, -0.52),
              radius: 1.0,
              colors: [Color(0xFF7A808A), Color(0xFF40454E), Color(0xFF1B1E24), Color(0xFF0C0D10), Color(0xFF08090B)],
              stops: [0, 0.2, 0.52, 0.8, 1],
            ),
            boxShadow: [BoxShadow(color: Color(0x40FFFFFF), spreadRadius: 0.5)],
          ),
          child: Align(
            alignment: const Alignment(0, -0.36),
            child: AnimatedBuilder(
              animation: _breath,
              builder: (context, _) {
                // .orb::after: opacity 1 → .55 → 1 over 2.4 s.
                final t = _breath.value;
                final opacity = widget.live ? 1 - 0.45 * (0.5 - 0.5 * math.cos(2 * math.pi * t)) : 1.0;
                return Opacity(
                  opacity: opacity,
                  child: Container(
                    width: led,
                    height: led,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: widget.live ? OmiColors.live : OmiColors.surface4,
                      boxShadow: widget.live
                          ? const [BoxShadow(color: Color(0x994C9BFF), blurRadius: 8, spreadRadius: 2)]
                          : null,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}

/// The listening wave (Liquid Dock): a row of thin bars whose heights ripple — each bar eases down
/// to 45 % and back over 1.6 s, neighbours a beat apart — while Omi is listening. Paused, the bars
/// hold still and dim. Decorative: the card's words say what is happening.
class OmiListeningWave extends StatefulWidget {
  const OmiListeningWave({super.key, this.live = true, this.height = 34, this.color});

  final bool live;
  final double height;

  /// The bars' colour; [OmiColors.textPrimary] by default.
  final Color? color;

  @override
  State<OmiListeningWave> createState() => _OmiListeningWaveState();
}

class _OmiListeningWaveState extends State<OmiListeningWave> with SingleTickerProviderStateMixin {
  late final AnimationController _ripple =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1600));

  void _sync() {
    final run = widget.live && omiLoopsEnabled(context);
    if (run && !_ripple.isAnimating) {
      _ripple.repeat();
    } else if (!run && _ripple.isAnimating) {
      _ripple.stop();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(OmiListeningWave oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  @override
  void dispose() {
    _ripple.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? OmiColors.textPrimary;
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: SizedBox(
          height: widget.height,
          width: double.infinity,
          child: CustomPaint(
            painter: _WavePainter(
              ripple: _ripple,
              color: widget.live ? color : color.withValues(alpha: 0.35),
            ),
          ),
        ),
      ),
    );
  }
}

class _WavePainter extends CustomPainter {
  _WavePainter({required this.ripple, required this.color}) : super(repaint: ripple);

  final Animation<double> ripple;
  final Color color;

  /// The prototype's bar heights (fractions of the strip), repeated along it.
  static const List<double> levels = [
    .22, .35, .5, .3, .62, .8, .45, .28, .55, .9, .7, .38, .25, .42, .66, .52, .3, .2, .35, .58, .76, .6, .4, .33, //
    .48, .7, .85, .5, .3, .24, .4, .62, .45, .3, .52, .72, .56, .36, .28, .44, .6, .8, .64, .4, .3, .5, .66, .42, //
    .3, .26,
  ];
  static const double _bar = 2;
  static const double _gap = 2.2;

  /// Height factor of bar [i] at ripple time [t] (0–1): 1 → 0.45 → 1, delayed −(i % 13) × 0.13 s.
  static double pulse(int i, double t) {
    final phase = (t + (i % 13) * 0.13 / 1.6) % 1.0;
    return 1 - 0.55 * (0.5 - 0.5 * math.cos(2 * math.pi * phase));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final count = ((size.width + _gap) / (_bar + _gap)).floor();
    if (count <= 0) return;
    final paint = Paint()..color = color;
    final t = ripple.value;
    final mid = size.height / 2;
    for (var i = 0; i < count; i++) {
      final base = math.max(3.0, levels[i % levels.length] * size.height);
      final h = math.max(3.0, base * pulse(i, t));
      final x = i * (_bar + _gap);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(x, mid - h / 2, _bar, h), const Radius.circular(1)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) => old.color != color || old.ripple != ripple;
}

/// The real audio level (Rev 3 Live): one bar per 125 ms bin, newest on the right, [levels]
/// giving heights 0–100. Redrawn eight times a second while [live]; still when paused (dimmed).
class OmiLevelStrip extends StatefulWidget {
  const OmiLevelStrip({super.key, required this.levels, this.live = true, this.height = 40, this.color});

  final List<int> Function() levels;
  final bool live;
  final double height;

  /// The bars' colour; [OmiColors.textPrimary] by default.
  final Color? color;

  @override
  State<OmiLevelStrip> createState() => _OmiLevelStripState();
}

class _OmiLevelStripState extends State<OmiLevelStrip> {
  Timer? _timer;

  void _sync() {
    final run = widget.live && omiLoopsEnabled(context);
    if (run && _timer == null) {
      _timer = Timer.periodic(const Duration(milliseconds: 125), (_) {
        if (mounted) setState(() {});
      });
    } else if (!run) {
      _timer?.cancel();
      _timer = null;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(OmiLevelStrip oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? OmiColors.textPrimary;
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: SizedBox(
          height: widget.height,
          width: double.infinity,
          child: CustomPaint(
            painter: _LevelPainter(
              levels: widget.levels(),
              color: widget.live ? color : color.withValues(alpha: 0.35),
            ),
          ),
        ),
      ),
    );
  }
}

class _LevelPainter extends CustomPainter {
  _LevelPainter({required this.levels, required this.color});

  final List<int> levels;
  final Color color;
  static const double _bar = 2;
  static const double _gap = 2.2;

  @override
  void paint(Canvas canvas, Size size) {
    final count = ((size.width + _gap) / (_bar + _gap)).floor();
    if (count <= 0) return;
    final paint = Paint()..color = color;
    final mid = size.height / 2;
    // Right-aligned: the newest bin is the last bar.
    final shown = levels.length > count ? levels.sublist(levels.length - count) : levels;
    final offset = count - shown.length;
    for (var i = 0; i < count; i++) {
      final level = i < offset ? 0 : shown[i - offset];
      final h = math.max(3.0, level / 100 * size.height);
      final x = i * (_bar + _gap);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(x, mid - h / 2, _bar, h), const Radius.circular(1)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_LevelPainter old) => true;
}
