import 'package:flutter/widgets.dart';

import 'package:flutter_svg/flutter_svg.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The line glyphs on the toolbar and Ask bar buttons: 24 × 24, a 1.8 outline with round caps
/// (the Omi v8 icon weight) and finer detail lines inside. Outline only, no fill.
enum OmiLineGlyph {
  microphone,

  /// The microphone without its inner detail, for talking to Omi from Home's Ask bar.
  voice,
  cloud,
  key,
  clock,
  export,
  plus,
  check,
  info,
  more,
  trash,
  refresh,
  edit,
  search,
  settings,
}

// Solid ink, no outline.
const _ink = 'fill="currentColor" stroke="none"';
// Detail lines inside a shape.
const _fine = 'stroke-width="1.4"';

const _paths = <OmiLineGlyph, String>{
  OmiLineGlyph.microphone: '<rect x="8.5" y="2.8" width="7" height="11.4" rx="3.5"/>'
      '<path $_fine d="M10.7 6.6h2.6M10.7 9.2h2.6"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v3M9 20.8h6"/>',
  OmiLineGlyph.voice:
      '<rect x="8.5" y="2.8" width="7" height="11.4" rx="3.5"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v3"/>',
  OmiLineGlyph.cloud: '<path d="M7 18.5a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 8.6a5 5 0 0 1-.5 9.9z"/>'
      '<path $_fine d="M12 16v-4.8M9.9 13.2l2.1-2.1 2.1 2.1"/>',
  OmiLineGlyph.key: '<circle cx="8" cy="15.5" r="4.3"/><circle $_fine cx="7.2" cy="16.3" r="1.2"/>'
      '<path d="M11.1 12.4l8.4-8.4M16.3 7.2l2.4 2.4M14 9.5l1.7 1.7"/>',
  // Timeouts and waiting: a stopwatch.
  OmiLineGlyph.clock: '<circle cx="12" cy="13.5" r="7.5"/><path d="M10 2.8h4M12 2.8V6M18.3 6.8l1.3-1.3"/>'
      '<path d="M12 9.6v4l2.5 1.6"/>',
  OmiLineGlyph.export: ''
      '<path d="M4 13v5.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V13M12 15V3.5M8 7.5l4-4 4 4"/><path $_fine d="M9.5 17.3h5"/>',
  OmiLineGlyph.plus: '<path d="M12 5v14M5 12h14"/>',
  OmiLineGlyph.check: '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.8 2.8L16.2 9.6"/>',
  OmiLineGlyph.info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.3"/><circle $_ink cx="12" cy="7.9" r="1"/>',
  OmiLineGlyph.more:
      '<circle $_ink cx="5.5" cy="12" r="1.5"/><circle $_ink cx="12" cy="12" r="1.5"/><circle $_ink cx="18.5" cy="12" r="1.5"/>',
  OmiLineGlyph.trash: '<path d="M6.5 6.8l.9 12.3a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4l.9-12.3"/>'
      '<path d="M4.5 6.8h15M9.5 6.8V4.6a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2.2"/><path $_fine d="M10.2 10.2v6.8M13.8 10.2v6.8"/>',
  OmiLineGlyph.edit: '<path d="M4.5 19.5l.8-3.9L15.6 5.3a1.8 1.8 0 0 1 2.6 0l.5.5a1.8 1.8 0 0 1 0 2.6L8.4 18.7z"/>'
      '<path $_fine d="M13.8 7.1l3.1 3.1"/><path d="M13 20h6.5"/>',
  OmiLineGlyph.search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.3 15.3l4.7 4.7"/>',
  // Settings: a cog, its teeth drawn heavier than the ring.
  OmiLineGlyph.settings: '<circle cx="12" cy="12" r="6.4"/><circle cx="12" cy="12" r="2.6"/>'
      '<path stroke-width="2.6" d="M18.4 12h2.2M16.53 16.53l1.55 1.55M12 18.4v2.2M7.47 16.53l-1.55 1.55M5.6 12H3.4'
      'M7.47 7.47L5.92 5.92M12 5.6V3.4M16.53 7.47l1.55-1.55"/>',
  OmiLineGlyph.refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4v4.5H15"/>',
};

/// One [OmiLineGlyph], drawn in [color] or the ambient [IconTheme] colour at [size] (default the
/// icon theme's size). Decorative: the row it sits in carries the label.
class OmiLineIcon extends StatelessWidget {
  const OmiLineIcon(this.glyph, {super.key, this.size, this.color});

  final OmiLineGlyph glyph;
  final double? size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = IconTheme.of(context);
    final side = size ?? theme.size ?? 24;
    return ExcludeSemantics(
      child: SvgPicture.string(
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round">${_paths[glyph]}</svg>',
        width: side,
        height: side,
        theme: SvgTheme(currentColor: color ?? theme.color ?? OmiColors.textPrimary),
      ),
    );
  }
}
