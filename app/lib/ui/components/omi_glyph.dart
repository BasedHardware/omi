import 'package:flutter/material.dart';

import 'package:flutter_svg/flutter_svg.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The v2 glyph set (`assets/icons/`): 24 pt SF-Symbols-style line icons, with `-fill` twins for a
/// selected tab. Same files on iOS and Android, so the two platforms draw identical icons.
abstract final class OmiGlyphs {
  static const String house = 'assets/icons/house.svg';
  static const String houseFill = 'assets/icons/house-fill.svg';
  static const String bubbles = 'assets/icons/bubbles.svg';
  static const String bubblesFill = 'assets/icons/bubbles-fill.svg';
  static const String checklist = 'assets/icons/checklist.svg';
  static const String grid = 'assets/icons/grid.svg';
  static const String gridFill = 'assets/icons/grid-fill.svg';
  static const String magnifyingGlass = 'assets/icons/magnifyingglass.svg';
  static const String person = 'assets/icons/person.svg';
  static const String pauseFill = 'assets/icons/pause-fill.svg';
  static const String playFill = 'assets/icons/play-fill.svg';
  static const String stopFill = 'assets/icons/stop-fill.svg';
  static const String chevronRight = 'assets/icons/chevron-right.svg';
  static const String mic = 'assets/icons/mic.svg';
  static const String waveform = 'assets/icons/waveform.svg';
  static const String cpu = 'assets/icons/cpu.svg';
  static const String hand = 'assets/icons/hand.svg';
  static const String bell = 'assets/icons/bell.svg';
  static const String location = 'assets/icons/location.svg';
  static const String bolt = 'assets/icons/bolt.svg';
  static const String checkmark = 'assets/icons/checkmark.svg';
  static const String sdcard = 'assets/icons/sdcard.svg';
  static const String graph = 'assets/icons/graph.svg';
  static const String devices = 'assets/icons/devices.svg';
  static const String iphone = 'assets/icons/iphone.svg';
  static const String tray = 'assets/icons/tray.svg';
  static const String doc = 'assets/icons/doc.svg';
  static const String textLines = 'assets/icons/text-lines.svg';
}

/// One glyph from [OmiGlyphs], tinted with [color] (the ambient icon colour by default).
///
/// Decorative: the control around it carries the label. Give [semanticLabel] only when the glyph is
/// the sole content that names something.
class OmiGlyph extends StatelessWidget {
  const OmiGlyph(this.asset, {super.key, this.size = 24, this.color, this.semanticLabel});

  /// A path from [OmiGlyphs].
  final String asset;

  final double size;

  /// Defaults to the ambient [IconTheme] colour, else [OmiColors.textPrimary].
  final Color? color;

  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final tint = color ?? IconTheme.of(context).color ?? OmiColors.textPrimary;
    final glyph = SvgPicture.asset(
      asset,
      width: size,
      height: size,
      colorFilter: ColorFilter.mode(tint, BlendMode.srcIn),
    );
    return semanticLabel == null
        ? ExcludeSemantics(child: glyph)
        : Semantics(label: semanticLabel, image: true, child: glyph);
  }
}
