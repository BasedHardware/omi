import 'dart:ui' show PathMetric;

import 'package:flutter/material.dart';

import 'package:flutter_svg/flutter_svg.dart';

import 'package:omi/ui/ui.dart';

/// The device a Home row came from, as a soft line glyph in a small warm tile at the start of the
/// row. Pendants, phones, watches, glasses, desktops and integrations have drawn glyphs; a source
/// with no device of its own (an older row, an unknown source) shows a conversation bubble. A caller
/// can pass an [icon] instead, and a recap's tile holds its day [emoji]. Decorative: the row names
/// what it is.
class DeviceTile extends StatelessWidget {
  const DeviceTile(
      {super.key, this.source, this.icon, this.emoji, this.status, this.faded = false, this.missing = false});

  /// A conversation source ('omi', 'phone', 'apple_watch', …).
  final String? source;

  /// A glyph instead of the source's, for a row that is not a recording (a firmware update).
  final IconData? icon;

  /// An emoji instead of a glyph (a recap's day, a highlight).
  final String? emoji;

  /// A dot on the top-right corner, ringed in the page colour: live or paused capture.
  final Color? status;

  /// Something still being made (a conversation processing).
  final bool faded;

  /// Something that was not recorded (a capture gap): a dashed outline and no fill.
  final bool missing;

  static const double size = 40;

  /// Air above and below a row that starts with a tile.
  static const double rowPadding = 10;

  @override
  Widget build(BuildContext context) {
    final ink = missing ? OmiColors.textTertiary : OmiColors.deviceTileInk;
    final glyph = icon == null && emoji == null ? glyphFor(source) : null;
    Widget tile = Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: missing ? null : BoxDecoration(color: OmiColors.deviceTile, borderRadius: OmiRadius.mdAll),
      child: emoji != null
          ? Text(emoji!, style: OmiType.title3)
          : glyph != null
              ? SvgPicture.string(glyph, width: 24, height: 24, colorFilter: ColorFilter.mode(ink, BlendMode.srcIn))
              : Icon(icon, size: 20, color: ink),
    );
    if (missing) tile = CustomPaint(painter: _DashedOutlinePainter(OmiColors.textTertiary), child: tile);
    if (faded) tile = Opacity(opacity: 0.45, child: tile);
    if (status != null) {
      tile = Stack(clipBehavior: Clip.none, children: [
        tile,
        Positioned(
          top: -3,
          right: -3,
          child: Container(
            key: const ValueKey('device_tile_status'),
            width: 11,
            height: 11,
            decoration: BoxDecoration(
              color: status,
              shape: BoxShape.circle,
              border: Border.all(color: OmiCanvas.pageOf(context), width: 2),
            ),
          ),
        ),
      ]);
    }
    return ExcludeSemantics(child: tile);
  }

  /// Whether [source] is a pendant (Omi, Limitless, Bee, Plaud, …), as opposed to a phone, watch,
  /// glasses or other source.
  static bool isPendant(String? source) => glyphFor(source) == _pendant;

  /// The drawn glyph for [source]. Every source has one, so a row never falls back to a bare mic.
  static String glyphFor(String? source) => switch (source) {
        'omi' || 'friend' || 'friend_com' || 'sdcard' || 'limitless' || 'bee' || 'fieldy' || 'plaud' => _pendant,
        'phone' => _phone,
        'apple_watch' => _watch,
        'openglass' || 'rayban_meta' || 'frame' => _glasses,
        'desktop' || 'screenpipe' => _desktop,
        'workflow' => _workflow,
        _ => _conversation,
      };

  static String _svg(String body) =>
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">$body</svg>';

  static final String _pendant = _svg('<path d="M6.5 2.5C8 5 9.6 6.4 12 6.6 14.4 6.4 16 5 17.5 2.5"/>'
      '<circle cx="12" cy="14.4" r="7.2"/><circle cx="12" cy="14.4" r="4.2" stroke-width="1.2" opacity=".55"/>'
      '<circle cx="12" cy="14.4" r="1.5" fill="currentColor" stroke="none"/>');
  static final String _phone = _svg('<rect x="7" y="3" width="10" height="18" rx="2.6"/><path d="M11 18h2"/>');
  static final String _watch = _svg(
      '<rect x="6.5" y="6.5" width="11" height="11" rx="3"/><path d="M9 6.5l.6-3h4.8l.6 3M9 17.5l.6 3h4.8l.6-3"/>');
  static final String _glasses = _svg('<circle cx="7" cy="14" r="3.5"/><circle cx="17" cy="14" r="3.5"/>'
      '<path d="M10.5 14h3M3.5 14l1-5M20.5 14l-1-5"/>');
  static final String _desktop =
      _svg('<rect x="3" y="4.5" width="18" height="12" rx="2.2"/><path d="M12 16.5v3.5M8.5 20h7"/>');
  // An integration (a workflow): the puzzle piece Settings uses for integrations.
  static final String _workflow = _svg('<path d="M4 7h4.4a2.3 2.3 0 1 1 4.4 0H17v4.4a2.3 2.3 0 1 1 0 4.4V20H4z"/>');
  static final String _conversation = _svg(
      '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H11.5L7.5 20.3V17h-1A2.5 2.5 0 0 1 4 14.5z"/>');
}

/// A dashed rounded outline: a tile for something that is not there.
class _DashedOutlinePainter extends CustomPainter {
  const _DashedOutlinePainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final outline = Path()..addRRect(OmiRadius.mdAll.toRRect((Offset.zero & size).deflate(0.5)));
    for (final PathMetric metric in outline.computeMetrics()) {
      for (double d = 0; d < metric.length; d += 6) {
        canvas.drawPath(metric.extractPath(d, d + 3), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedOutlinePainter oldDelegate) => oldDelegate.color != color;
}
