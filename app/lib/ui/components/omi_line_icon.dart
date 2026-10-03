import 'package:flutter/widgets.dart';

import 'package:flutter_svg/flutter_svg.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The line glyphs that sit in an [OmiSettingsIconTile]: 24 × 24, a 1.8 outline with round caps
/// (the Omi v8 icon weight) and finer detail lines inside. Outline only, no fill.
enum OmiLineGlyph {
  person,
  chart,
  gift,
  bluetooth,
  microphone,
  bell,
  integrations,
  shield,
  memories,
  goals,
  help,
  chat,
  file,
  tag,
  task,
  code,
  cloud,
  phone,
  smartphone,
  key,
  globe,
  book,
  wave,
  people,
  speaker,
  clock,
  list,
  contrast,
  export,
  import,
  star,
  save,
  lock,
  plus,
  check,
  broadcast,
  info,
  more,
  trash,
  refresh,
  edit,
  search,
  location,
  translate,
  settings,
}

// Solid ink, no outline.
const _ink = 'fill="currentColor" stroke="none"';
// Detail lines inside a shape.
const _fine = 'stroke-width="1.4"';

const _paths = <OmiLineGlyph, String>{
  OmiLineGlyph.person: '<circle cx="12" cy="8" r="3.8"/>'
      '<path d="M4.8 20.3c.6-3.8 3.5-6.3 7.2-6.3s6.6 2.5 7.2 6.3z"/><path $_fine d="M10.1 14.3l1.9 2.3 1.9-2.3"/>',
  // Plan & Usage: a gauge.
  OmiLineGlyph.chart: '<path d="M3.5 16.5a8.5 8.5 0 0 1 17 0z"/>'
      '<path $_fine d="M6 10.5l1.2 1.2M12 8v1.7M18 10.5l-1.2 1.2"/><path d="M12 16.5l3.3-5.2"/>'
      '<circle $_ink cx="12" cy="16.5" r="1.7"/><path d="M8 20.2h8"/>',
  OmiLineGlyph.gift: '<rect x="3.5" y="8" width="17" height="4.2" rx="1.2"/>'
      '<path d="M5 12.2v6.6a1.7 1.7 0 0 0 1.7 1.7h10.6a1.7 1.7 0 0 0 1.7-1.7v-6.6M12 8v12.5"/>'
      '<path d="M12 8C10.6 5 7.4 4.5 7.4 6.4 7.4 7.7 9.4 8 12 8zm0 0c1.4-3 4.6-3.5 4.6-1.6 0 1.3-2 1.6-4.6 1.6z"/>',
  // The device: a body with the Bluetooth rune and its signal.
  OmiLineGlyph.bluetooth: '<rect x="3.5" y="5" width="12" height="14" rx="3.6"/>'
      '<path $_fine d="M7.2 9.9l4.6 4.2-2.3 2.1V7.8l2.3 2.1-4.6 4.2"/><path d="M18.2 9.6a3.4 3.4 0 0 1 0 4.8M20.5 7.3a6.6 6.6 0 0 1 0 9.4"/>',
  OmiLineGlyph.microphone: '<rect x="8.5" y="2.8" width="7" height="11.4" rx="3.5"/>'
      '<path $_fine d="M10.7 6.6h2.6M10.7 9.2h2.6"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v3M9 20.8h6"/>',
  OmiLineGlyph.bell: '<path d="M6 16.3v-4.8a6 6 0 0 1 12 0v4.8l1.5 1.9h-15z"/>'
      '<path d="M12 3.6v1.8M10 20.8a2 2 0 0 0 4 0"/><path $_fine d="M3.3 8.6a9 9 0 0 1 2.1-3.4M20.7 8.6a9 9 0 0 0-2.1-3.4"/>',
  // Integrations: a puzzle piece.
  OmiLineGlyph.integrations: '<path d="M4 7h4.4a2.3 2.3 0 1 1 4.4 0H17v4.4a2.3 2.3 0 1 1 0 4.4V20H4z"/>',
  OmiLineGlyph.shield: '<path d="M12 3l7 2.8V12c0 4.3-2.9 7.4-7 9-4.1-1.6-7-4.7-7-9V5.8z"/>'
      '<circle cx="12" cy="10.7" r="1.8"/><path d="M12 12.5v3"/>',
  OmiLineGlyph.memories: '<path d="M12 5.5A3 3 0 0 0 6.6 6 3 3 0 0 0 4.5 11a3 3 0 0 0 1.6 4.8A3 3 0 0 0 12 18z"/>'
      '<path d="M12 5.5A3 3 0 0 1 17.4 6a3 3 0 0 1 2.1 5 3 3 0 0 1-1.6 4.8A3 3 0 0 1 12 18z"/><path d="M12 5.5V18"/>'
      '<path $_fine d="M7.9 9.3c1 .1 1.8.8 2 1.8M16.1 9.3c-1 .1-1.8.8-2 1.8M7.6 14.2c.9-.5 2-.4 2.7.3M16.4 14.2c-.9-.5-2-.4-2.7.3"/>',
  // Goals: a target with an arrow in it.
  OmiLineGlyph.goals: '<circle cx="11" cy="13" r="8"/><circle cx="11" cy="13" r="4.4"/>'
      '<circle $_ink cx="11" cy="13" r="1.4"/><path d="M11 13l7.2-7.2"/><path $_fine d="M16.4 3.6v2.6h2.6M18.2 5.8l2.4-2.4"/>',
  // Help & About: a life ring.
  OmiLineGlyph.help:
      '<path fill-rule="evenodd" d="M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 0 1 0-17zm0 5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z"/>'
          '<path d="M6 6l3.5 3.5M18 6l-3.5 3.5M6 18l3.5-3.5M18 18l-3.5-3.5"/>',
  OmiLineGlyph.chat:
      '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H11.5L7.5 20.3V17h-1A2.5 2.5 0 0 1 4 14.5z"/>'
          '<path $_fine d="M8 8.8h8M8 12.1h5"/>',
  OmiLineGlyph.file:
      '<path d="M6.5 3.5h7l4.5 4.5v11a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5z"/>'
          '<path $_fine d="M13.5 3.5V8H18M8.5 12.5h7M8.5 15.5h7M8.5 18.2h4"/>',
  OmiLineGlyph.tag:
      '<path d="M3.5 11.4V5A1.5 1.5 0 0 1 5 3.5h6.4a1.5 1.5 0 0 1 1.1.4l7.6 7.6a1.5 1.5 0 0 1 0 2.1l-6.6 6.6a1.5 1.5 0 0 1-2.1 0l-7.6-7.6a1.5 1.5 0 0 1-.3-1.2z"/>'
          '<circle cx="8.2" cy="8.2" r="1.6"/>',
  OmiLineGlyph.task: '<rect x="4" y="4" width="16" height="16" rx="4"/><path d="M8.2 12.2l2.6 2.6 5-5.2"/>',
  // Developer: a terminal window.
  OmiLineGlyph.code: ''
      '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M3 8.5h18"/>'
      '<circle $_ink cx="5.8" cy="6.5" r=".7"/><circle $_ink cx="7.9" cy="6.5" r=".7"/><circle $_ink cx="10" cy="6.5" r=".7"/>'
      '<path d="M7 12l2.4 2-2.4 2M12 16.2h4.5"/>',
  OmiLineGlyph.cloud: '<path d="M7 18.5a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 8.6a5 5 0 0 1-.5 9.9z"/>'
      '<path $_fine d="M12 16v-4.8M9.9 13.2l2.1-2.1 2.1 2.1"/>',
  // Phone calls: a handset with its ring.
  OmiLineGlyph.phone:
      '<path d="M5 4h3.6l1.9 4.8-2.3 1.5a11 11 0 0 0 5.5 5.5l1.5-2.3 4.8 1.9V19a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>'
          '<path $_fine d="M14.5 3.5a6 6 0 0 1 6 6M14.5 6.8a2.7 2.7 0 0 1 2.7 2.7"/>',
  // The phone itself (storage on this phone).
  OmiLineGlyph.smartphone: '<rect x="6" y="2.8" width="12" height="18.4" rx="2.6"/>'
      '<path $_fine d="M10.5 5.3h3M10.3 18.4h3.4"/>',
  OmiLineGlyph.key: '<circle cx="8" cy="15.5" r="4.3"/><circle $_fine cx="7.2" cy="16.3" r="1.2"/>'
      '<path d="M11.1 12.4l8.4-8.4M16.3 7.2l2.4 2.4M14 9.5l1.7 1.7"/>',
  OmiLineGlyph.globe: '<circle cx="12" cy="12" r="8.5"/>'
      '<path $_fine d="M3.5 12h17M5.2 7.5h13.6M5.2 16.5h13.6M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5z"/>',
  // Custom vocabulary: a dictionary.
  OmiLineGlyph.book: '<path d="M5 5a1.5 1.5 0 0 1 1.5-1.5H18v13H7.5A2.5 2.5 0 0 0 5 19z"/>'
      '<path d="M5 19a2.5 2.5 0 0 0 2.5 2H18v-4.5"/><path $_fine d="M8.5 7.5h6M8.5 10.3h4"/>',
  // Speech profile: a voiceprint.
  OmiLineGlyph.wave:
      '<circle cx="12" cy="12" r="8.5"/><path d="M7.6 11v2M9.8 8.7v6.6M12 6.8v10.4M14.2 9.3v5.4M16.4 11v2"/>',
  OmiLineGlyph.people: '<circle cx="16.2" cy="8" r="2.9"/><path d="M16 13.5c2.8.1 4.6 2.1 5 4.9"/>'
      '<circle cx="9" cy="8.8" r="3.6"/><path d="M2.8 20c.6-3.4 3.1-5.6 6.2-5.6s5.6 2.2 6.2 5.6z"/>',
  OmiLineGlyph.speaker: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path $_fine d="M7.5 9.5v5"/>'
      '<path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
  // Timeouts and waiting: a stopwatch.
  OmiLineGlyph.clock: '<circle cx="12" cy="13.5" r="7.5"/><path d="M10 2.8h4M12 2.8V6M18.3 6.8l1.3-1.3"/>'
      '<path d="M12 9.6v4l2.5 1.6"/>',
  // Conversation display: list rows with a thumbnail each.
  OmiLineGlyph.list:
      '<rect x="3.5" y="4.5" width="6" height="6" rx="1.6"/><rect x="3.5" y="13.5" width="6" height="6" rx="1.6"/>'
          '<path d="M12.5 6h8M12.5 15h8"/><path $_fine d="M12.5 9h5M12.5 18h5"/>',
  // Appearance: half light, half dark, with rays.
  OmiLineGlyph.contrast: '<circle cx="12" cy="12" r="5"/><path $_ink d="M12 7a5 5 0 0 1 0 10z"/>'
      '<path $_fine d="M12 2.8v1.8M12 19.4v1.8M2.8 12h1.8M19.4 12h1.8M5.5 5.5l1.3 1.3M17.2 17.2l1.3 1.3M5.5 18.5l1.3-1.3M17.2 6.8l1.3-1.3"/>',
  OmiLineGlyph.export: ''
      '<path d="M4 13v5.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V13M12 15V3.5M8 7.5l4-4 4 4"/><path $_fine d="M9.5 17.3h5"/>',
  OmiLineGlyph.import: ''
      '<path d="M4 13v5.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V13M12 3.5V15M8 11l4 4 4-4"/>',
  // What's new: sparkles.
  OmiLineGlyph.star: '<path d="M10 5c.6 4 2.6 6 6.5 6.6-3.9.6-5.9 2.6-6.5 6.6-.6-4-2.6-6-6.5-6.6C7.4 11 9.4 9 10 5z"/>'
      '<path $_fine d="M17.6 2.8c.3 1.4.9 2.1 2.3 2.4-1.4.3-2 1-2.3 2.4-.3-1.4-.9-2.1-2.3-2.4 1.4-.3 2-1 2.3-2.4z"/>'
      '<circle $_ink cx="18.6" cy="17.6" r="1.1"/>',
  // Transcribe later: a page with a clock.
  OmiLineGlyph.save: '<path d="M12.5 20.5H6.5A1.5 1.5 0 0 1 5 19V5a1.5 1.5 0 0 1 1.5-1.5h7l4 4V10"/>'
      '<path $_fine d="M13.5 3.5v4h4M8 10h5M8 13h3"/><circle cx="16.8" cy="16.8" r="4.2"/><path $_fine d="M16.8 14.6v2.3l1.5 1"/>',
  OmiLineGlyph.lock: '<rect x="5" y="10.5" width="14" height="10" rx="2.2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>'
      '<circle $_ink cx="12" cy="14.8" r="1.3"/><path d="M12 15.5v2.2"/>',
  OmiLineGlyph.plus: '<path d="M12 5v14M5 12h14"/>',
  OmiLineGlyph.check: '<circle cx="12" cy="12" r="8.5"/><path d="M8 12.3l2.8 2.8L16.2 9.6"/>',
  // Background mode: a broadcasting mast.
  OmiLineGlyph.broadcast: '<circle cx="12" cy="10" r="2.2"/><path d="M12 12.2V21M9.5 21h5"/>'
      '<path d="M8.6 6.6a4.8 4.8 0 0 0 0 6.8M15.4 6.6a4.8 4.8 0 0 1 0 6.8"/>'
      '<path $_fine d="M5.8 3.8a8.8 8.8 0 0 0 0 12.4M18.2 3.8a8.8 8.8 0 0 1 0 12.4"/>',
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
  // Location: the navigation arrow, with its fold.
  OmiLineGlyph.location: '<path d="M19.6 4.4L4.4 11l6.9 1.7 1.7 6.9z"/><path $_fine d="M11.3 12.7l4.4-4.4"/>',
  // Translation: a script character beside a Latin A.
  OmiLineGlyph.translate: '<path d="M12.6 20.5l3.9-9.5 3.9 9.5M14 17.3h5"/>'
      '<path $_fine d="M3.5 5.8h9M8 3.5v2.3M10.6 5.8c-.9 3.4-3.3 6.3-6.8 8M6 8.6c1.2 2.2 3 4 5.2 5.1"/>',
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

/// The battery as a glyph: an outlined shell filled to [level] (0–100), with a bolt while
/// [charging]. Same 24 × 24 grid and stroke as [OmiLineIcon].
class OmiBatteryIcon extends StatelessWidget {
  const OmiBatteryIcon({super.key, required this.level, this.charging = false, this.size, this.color});

  final int level;
  final bool charging;
  final double? size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = IconTheme.of(context);
    final side = size ?? theme.size ?? 24;
    final fill = (12.6 * level.clamp(0, 100) / 100).toStringAsFixed(1);
    // Charging keeps the level, faded, so the solid bolt reads on top of it at any charge.
    final levelOpacity = charging ? ' fill-opacity=".35"' : '';
    final bolt = charging ? '<path $_ink d="M11.6 8.4l-3 4.1h2.6l-.8 3.1 3-4.1h-2.6z"/>' : '';
    return ExcludeSemantics(
      child: SvgPicture.string(
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"><rect x="2.5" y="7" width="17" height="10" rx="2.6"/><path d="M21.5 10.3v3.4"/>'
        '<rect $_ink$levelOpacity x="4.7" y="9.2" width="$fill" height="5.6" rx="1.1"/>$bolt</svg>',
        width: side,
        height: side,
        theme: SvgTheme(currentColor: color ?? theme.color ?? OmiColors.textPrimary),
      ),
    );
  }
}
