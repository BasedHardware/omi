import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// One outer shadow as the design's CSS draws it (`box-shadow: x y blur color`): outside the shape
/// only, so a translucent surface above it is never darkened. [blur] is the CSS blur radius.
@immutable
class OmiShadow {
  const OmiShadow({required this.color, this.offset = Offset.zero, this.blur = 0});

  final Color color;
  final Offset offset;
  final double blur;

  @override
  bool operator ==(Object other) =>
      other is OmiShadow && other.color == color && other.offset == offset && other.blur == blur;

  @override
  int get hashCode => Object.hash(color, offset, blur);
}

/// The light and shade of a raised v2 surface, painted around and over its child:
///
/// * [shadows] outside the shape (CSS outer `box-shadow`);
/// * [topLight], a 0.5 pt highlight along the top edge that thins out round the corners (CSS
///   `inset 0 .5px 0`);
/// * [ring], a 0.5 pt hairline all round (CSS `inset 0 0 0 .5px`).
class OmiSurfaceLight extends StatelessWidget {
  const OmiSurfaceLight({
    super.key,
    required this.borderRadius,
    required this.child,
    this.shadows = const [],
    this.topLight,
    this.ring,
  });

  final BorderRadius borderRadius;
  final List<OmiShadow> shadows;
  final Color? topLight;
  final Color? ring;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: shadows.isEmpty ? null : _OuterShadowPainter(borderRadius, shadows),
      foregroundPainter: topLight == null && ring == null ? null : _EdgeLightPainter(borderRadius, topLight, ring),
      child: child,
    );
  }
}

class _OuterShadowPainter extends CustomPainter {
  _OuterShadowPainter(this.borderRadius, this.shadows);

  final BorderRadius borderRadius;
  final List<OmiShadow> shadows;

  @override
  void paint(Canvas canvas, Size size) {
    final shape = borderRadius.toRRect(Offset.zero & size);
    canvas.save();
    // Everything but the shape itself: CSS shadows never show through the box.
    canvas.clipPath(Path()
      ..fillType = PathFillType.evenOdd
      ..addRect((Offset.zero & size).inflate(120))
      ..addRRect(shape));
    for (final shadow in shadows) {
      final paint = Paint()..color = shadow.color;
      // CSS blur radius = twice the Gaussian standard deviation.
      if (shadow.blur > 0) paint.maskFilter = MaskFilter.blur(BlurStyle.normal, shadow.blur / 2);
      canvas.drawRRect(shape.shift(shadow.offset), paint);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_OuterShadowPainter old) => old.borderRadius != borderRadius || !_same(old.shadows, shadows);

  static bool _same(List<OmiShadow> a, List<OmiShadow> b) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }
}

class _EdgeLightPainter extends CustomPainter {
  _EdgeLightPainter(this.borderRadius, this.topLight, this.ring);

  final BorderRadius borderRadius;
  final Color? topLight;
  final Color? ring;

  @override
  void paint(Canvas canvas, Size size) {
    final shape = borderRadius.toRRect(Offset.zero & size);
    final outer = Path()..addRRect(shape);
    if (ring != null) {
      canvas.drawPath(
        Path.combine(PathOperation.difference, outer, Path()..addRRect(shape.deflate(0.5))),
        Paint()..color = ring!,
      );
    }
    if (topLight != null) {
      canvas.drawPath(
        Path.combine(PathOperation.difference, outer, Path()..addRRect(shape.shift(const Offset(0, 0.5)))),
        Paint()..color = topLight!,
      );
    }
  }

  @override
  bool shouldRepaint(_EdgeLightPainter old) =>
      old.borderRadius != borderRadius || old.topLight != topLight || old.ring != ring;
}

/// The v2 card: a [OmiColors.surface1] panel with the design's edge light (a faint highlight on
/// its top edge and a hard 1 pt shade under it). [radius] is 26 for lists and Home cards, 28 for the
/// live card, 22 for small cards.
///
/// With [onTap] the whole card is one button that dips (scale 0.96, opacity 0.82) while pressed;
/// give it a [semanticLabel] when its text alone does not say where it goes.
class OmiCard extends StatelessWidget {
  const OmiCard({
    super.key,
    required this.child,
    this.radius = OmiRadius.card,
    this.color,
    this.padding = EdgeInsets.zero,
    this.onTap,
    this.onLongPress,
    this.semanticLabel,
    this.clip = false,
  });

  final Widget child;
  final double radius;

  /// The panel's fill; [OmiColors.surface1] by default.
  final Color? color;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final String? semanticLabel;

  /// Clip the child to the rounded shape (lists whose rows paint their own pressed fill).
  final bool clip;

  static const List<OmiShadow> _shade = [OmiShadow(color: Color(0x33000000), offset: Offset(0, 1))];

  /// Daylight (canvas light `.card`): a whisper of ink under the edge instead of a hard shade.
  static const List<OmiShadow> _shadeLight = [
    OmiShadow(color: Color(0x0A14171E), offset: Offset(0, 0.5)),
    OmiShadow(color: Color(0x0D14171E), offset: Offset(0, 1), blur: 3),
  ];

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(radius);
    Widget body = Padding(padding: padding, child: child);
    if (clip) body = ClipRRect(borderRadius: borderRadius, child: body);
    Widget card = OmiSurfaceLight(
      borderRadius: borderRadius,
      shadows: OmiColors.isLight ? _shadeLight : _shade,
      topLight: OmiColors.palette.cardTopLight,
      ring: OmiColors.palette.cardRim,
      child: DecoratedBox(
        decoration: BoxDecoration(color: color ?? OmiColors.surface1, borderRadius: borderRadius),
        child: body,
      ),
    );
    if (onTap == null && onLongPress == null) return card;
    card = OmiPressable(onTap: onTap, onLongPress: onLongPress, child: card);
    return Semantics(button: onTap != null, label: semanticLabel, child: card);
  }
}

/// The design's press feedback (`.press`): while a finger is down the child shrinks to 0.96 and
/// fades to 0.82, springing back on release. Under Reduce Motion only the fade remains.
class OmiPressable extends StatefulWidget {
  const OmiPressable({super.key, required this.child, this.onTap, this.onLongPress, this.behavior});

  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final HitTestBehavior? behavior;

  @override
  State<OmiPressable> createState() => _OmiPressableState();
}

class _OmiPressableState extends State<OmiPressable> {
  bool _down = false;

  void _set(bool down) {
    if (_down != down && mounted) setState(() => _down = down);
  }

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.disableAnimationsOf(context);
    final enabled = widget.onTap != null || widget.onLongPress != null;
    return GestureDetector(
      behavior: widget.behavior ?? HitTestBehavior.opaque,
      onTapDown: enabled ? (_) => _set(true) : null,
      onTapUp: enabled ? (_) => _set(false) : null,
      onTapCancel: enabled ? () => _set(false) : null,
      onLongPressEnd: enabled ? (_) => _set(false) : null,
      onTap: widget.onTap,
      onLongPress: widget.onLongPress,
      child: AnimatedOpacity(
        opacity: _down ? 0.82 : 1,
        duration: const Duration(milliseconds: 200),
        curve: Curves.ease,
        child: AnimatedScale(
          scale: _down && !reduce ? 0.96 : 1,
          duration: const Duration(milliseconds: 420),
          curve: OmiMotion.springCurve,
          child: widget.child,
        ),
      ),
    );
  }
}

/// A glyph in a rounded tile (v2 `tile`): [OmiColors.surface3] with a soft top sheen, a 0.5 pt
/// highlight and a small shadow. Corner radius follows the size (30 → 8, 32 → 9, 36 → 10,
/// 40 → 12, 52 → 14). Decorative; the row around it carries the label.
class OmiIconTile extends StatelessWidget {
  const OmiIconTile({super.key, required this.child, this.size = 30, this.color});

  final Widget child;
  final double size;

  /// The tile's fill; [OmiColors.surface3] by default.
  final Color? color;

  static double radiusFor(double size) => switch (size) {
        >= 52 => 14,
        >= 40 => 12,
        >= 36 => 10,
        >= 32 => 9,
        _ => 8,
      };

  static const List<OmiShadow> _shade = [OmiShadow(color: Color(0x47000000), offset: Offset(0, 1), blur: 2)];
  static const List<OmiShadow> _shadeLight = [OmiShadow(color: Color(0x0F14171E), offset: Offset(0, 1), blur: 2)];

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(radiusFor(size));
    final light = OmiColors.isLight;
    final color = this.color ?? OmiColors.surface3;
    return ExcludeSemantics(
      child: OmiSurfaceLight(
        borderRadius: borderRadius,
        shadows: light ? _shadeLight : _shade,
        topLight: light ? null : const Color(0x24FFFFFF),
        ring: light ? const Color(0x1214171E) : null,
        child: Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: borderRadius,
            // Opaque at both ends: the sheen is the fill lightened by 8 % white.
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              // Daylight (canvas light `.tile`): 90 % white at the top, gone by three quarters.
              colors: [Color.alphaBlend(light ? const Color(0xE6FFFFFF) : const Color(0x14FFFFFF), color), color],
              stops: light ? const [0, 0.75] : const [0, 0.72],
            ),
          ),
          child: IconTheme.merge(
            data: IconThemeData(size: size * 0.6, color: OmiColors.textPrimary),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// A 4 pt progress bar (v2): [OmiColors.surface4] track, white fill that glides to [value].
class OmiProgressBar extends StatelessWidget {
  const OmiProgressBar({super.key, required this.value, this.semanticLabel});

  /// 0–1.
  final double value;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final v = value.clamp(0.0, 1.0);
    return Semantics(
      label: semanticLabel,
      value: '${(v * 100).round()}%',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(2),
        child: SizedBox(
          height: 4,
          child: DecoratedBox(
            decoration: BoxDecoration(color: OmiColors.surface4),
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              child: TweenAnimationBuilder<double>(
                tween: Tween(end: v),
                duration: OmiMotion.of(context).emphasized,
                curve: OmiMotion.springCurve,
                builder: (context, t, _) => FractionallySizedBox(
                  widthFactor: t,
                  heightFactor: 1,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: OmiColors.textPrimary,
                      borderRadius: const BorderRadius.all(Radius.circular(2)),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The round task checkbox (v2): a 24 pt ring in [OmiColors.textTertiary]; done, a white disc with
/// an ink check that pops in. The 44 pt target is the parent's job ([OmiCheckCircle] pads itself
/// out to it).
class OmiCheckCircle extends StatelessWidget {
  const OmiCheckCircle({super.key, required this.done, required this.onChanged, required this.semanticLabel});

  final bool done;
  final ValueChanged<bool>? onChanged;

  /// "Mark as done" / "Mark as not done" (the caller knows which).
  final String semanticLabel;

  @override
  Widget build(BuildContext context) {
    final reduce = MediaQuery.disableAnimationsOf(context);
    return Semantics(
      button: true,
      checked: done,
      label: semanticLabel,
      excludeSemantics: true,
      onTap: onChanged == null ? null : () => onChanged!(!done),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onChanged == null ? null : () => onChanged!(!done),
        child: SizedBox(
          width: OmiSize.minTap,
          height: OmiSize.minTap,
          child: Center(
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: done ? OmiColors.textPrimary : Colors.transparent,
                border: done ? null : Border.all(color: OmiColors.textTertiary, width: 1.5),
              ),
              child: done
                  ? TweenAnimationBuilder<double>(
                      tween: Tween(begin: reduce ? 1 : 0.4, end: 1),
                      duration: const Duration(milliseconds: 380),
                      curve: OmiMotion.bouncyCurve,
                      builder: (context, s, child) => Transform.scale(scale: s, child: child),
                      child: Icon(Icons.check_rounded, size: 15, color: OmiColors.onAccent),
                    )
                  : null,
            ),
          ),
        ),
      ),
    );
  }
}

/// The fade that lets content slide under a floating header or tab bar (v2 `edge-top` /
/// `edge-bottom`): page ink at the edge, clear at [height]. Never takes touches.
class OmiEdgeFade extends StatelessWidget {
  const OmiEdgeFade.top({super.key, this.height = 110}) : _top = true;
  const OmiEdgeFade.bottom({super.key, this.height = 150}) : _top = false;

  final double height;
  final bool _top;

  static Color _ink(double alpha) => OmiColors.surface0.withValues(alpha: alpha);

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: SizedBox(
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: _top ? Alignment.topCenter : Alignment.bottomCenter,
              end: _top ? Alignment.bottomCenter : Alignment.topCenter,
              // The page colour at 95 → 80 → 0 % (top) and 97 → 72 → 0 % (bottom).
              colors: _top ? [_ink(0.95), _ink(0.8), _ink(0)] : [_ink(0.97), _ink(0.72), _ink(0)],
              stops: _top ? const [0, 0.52, 1] : const [0, 0.48, 1],
            ),
          ),
        ),
      ),
    );
  }
}

/// A person's initial on the neutral graphite disc (v2 Settings account row): 56 pt on Settings,
/// smaller in lists. The same in light and dark — it is the avatar, not a surface.
class OmiInitialAvatar extends StatelessWidget {
  const OmiInitialAvatar({super.key, required this.name, this.size = 56});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final trimmed = name.trim();
    final initial = trimmed.isEmpty ? '' : trimmed.characters.first.toUpperCase();
    return ExcludeSemantics(
      child: OmiSurfaceLight(
        borderRadius: BorderRadius.circular(size / 2),
        shadows: const [],
        topLight: const Color(0x59FFFFFF),
        child: Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFFA3AAB7), Color(0xFF6C7381)],
            ),
          ),
          child: Text(
            initial,
            style: TextStyle(
              fontSize: size * 24 / 56,
              fontWeight: FontWeight.w600,
              color: const Color(0xFFFFFFFF),
              height: 1,
            ),
          ),
        ),
      ),
    );
  }
}
