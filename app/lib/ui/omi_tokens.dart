import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// One complete set of Omi's colours. [OmiColors] reads the active set; the app root switches it
/// when the appearance changes (Settings → Appearance: System, Light or Dark).
///
/// [dark] is the Liquid Dock graphite; [light] is the same design in daylight (the dock prototype's
/// light theme and the canvas's Light boards): a pale page, white cards, ink text.
@immutable
class OmiPalette {
  const OmiPalette._({
    required this.brightness,
    required this.surface0,
    required this.surface1,
    required this.surface2,
    required this.surface3,
    required this.surface4,
    required this.segmentThumb,
    required this.sheet,
    required this.well,
    required this.glass,
    required this.glassSheen,
    required this.glassRim,
    required this.glassRing,
    required this.glassShadow,
    required this.glassShadowTight,
    required this.lensTop,
    required this.lensBottom,
    required this.lensRim,
    required this.lensRing,
    required this.lensShadow,
    required this.cardShade,
    required this.cardTopLight,
    required this.cardRim,
    required this.tileTopLight,
    required this.dockTabIdle,
    required this.shadowSoft,
    required this.scrim,
    required this.cellPressed,
    required this.glassSelected,
    required this.border,
    required this.textPrimary,
    required this.textSecondary,
    required this.textTertiary,
    required this.textDisabled,
    required this.accent,
    required this.onAccent,
    required this.selection,
    required this.live,
    required this.success,
    required this.successSurface,
    required this.warning,
    required this.danger,
    required this.dangerSurface,
  });

  final Brightness brightness;
  final Color surface0;
  final Color surface1;
  final Color surface2;
  final Color surface3;
  final Color surface4;
  final Color segmentThumb;
  final Color sheet;
  final Color well;
  final Color glass;
  final Color glassSheen;
  final Color glassRim;
  final Color glassRing;
  final Color glassShadow;
  final Color glassShadowTight;
  final Color lensTop;
  final Color lensBottom;
  final Color lensRim;
  final Color lensRing;
  final Color lensShadow;
  final Color cardShade;
  final Color cardTopLight;
  final Color cardRim;
  final Color tileTopLight;
  final Color dockTabIdle;
  final Color shadowSoft;
  final Color scrim;
  final Color cellPressed;
  final Color glassSelected;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;
  final Color textTertiary;
  final Color textDisabled;
  final Color accent;
  final Color onAccent;
  final Color selection;
  final Color live;
  final Color success;
  final Color successSurface;
  final Color warning;
  final Color danger;
  final Color dangerSurface;

  bool get isLight => brightness == Brightness.light;

  /// Graphite with a faint cool cast (the Liquid Dock palette).
  static const OmiPalette dark = OmiPalette._(
    brightness: Brightness.dark,
    surface0: Color(0xFF0A0B0F),
    surface1: Color(0xFF13151B),
    surface2: Color(0xFF1C1F27),
    surface3: Color(0xFF262A33),
    surface4: Color(0xFF333842),
    segmentThumb: Color(0xFF3B404B),
    sheet: Color(0xFF101217),
    well: Color(0xFF0D0F13),
    glass: Color(0xF014161B),
    glassSheen: Color(0x0AFFFFFF),
    glassRim: Color(0x21FFFFFF),
    glassRing: Color(0x14FFFFFF),
    glassShadow: Color(0x73000000),
    glassShadowTight: Color(0x59000000),
    lensTop: Color(0x17FFFFFF),
    lensBottom: Color(0x11FFFFFF),
    lensRim: Color(0x24FFFFFF),
    lensRing: Color(0x0FFFFFFF),
    lensShadow: Color(0x2E000000),
    cardShade: Color(0x33000000),
    cardTopLight: Color(0x14FFFFFF),
    cardRim: Color(0x0DFFFFFF),
    tileTopLight: Color(0x14FFFFFF),
    dockTabIdle: Color(0xB8FFFFFF),
    shadowSoft: Color(0x40000000),
    scrim: Color(0x38000000),
    cellPressed: Color(0x0DFFFFFF),
    glassSelected: Color(0x1CFFFFFF),
    border: Color(0x29969EAF),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFA9AEB9),
    textTertiary: Color(0xFF868B96),
    textDisabled: Color(0xFF5C616C),
    accent: Color(0xFFFFFFFF),
    onAccent: Color(0xFF0A0B0F),
    selection: Color(0xFF6F86AD),
    live: Color(0xFF4C9BFF),
    success: Color(0xFF30D158),
    successSurface: Color(0x2630D158),
    warning: Color(0xFFFFB547),
    danger: Color(0xFFFF6B61),
    dangerSurface: Color(0x24FF6B61),
  );

  /// Daylight: pale page, white cards, ink text, the same one blue for live audio.
  static const OmiPalette light = OmiPalette._(
    brightness: Brightness.light,
    surface0: Color(0xFFF2F3F6),
    surface1: Color(0xFFFFFFFF),
    surface2: Color(0xFFE8EAEF),
    surface3: Color(0xFFDEE1E7),
    surface4: Color(0xFFC9CED7),
    segmentThumb: Color(0xFFFFFFFF),
    sheet: Color(0xFFF7F8FA),
    well: Color(0xFFE4E7EC),
    glass: Color(0x6BFFFFFF),
    glassSheen: Color(0xB3FFFFFF),
    glassRim: Color(0xFFFFFFFF),
    glassRing: Color(0x1A14171E),
    glassShadow: Color(0x2414171E),
    glassShadowTight: Color(0x1414171E),
    lensTop: Color(0xC7FFFFFF),
    lensBottom: Color(0xB8FFFFFF),
    lensRim: Color(0xFFFFFFFF),
    lensRing: Color(0x24FFFFFF),
    lensShadow: Color(0x1F14171E),
    cardShade: Color(0x0D14171E),
    cardTopLight: Color(0xFFFFFFFF),
    cardRim: Color(0x0D14171E),
    tileTopLight: Color(0xE6FFFFFF),
    dockTabIdle: Color(0xFF5B6270),
    shadowSoft: Color(0x2914171E),
    scrim: Color(0x38000000),
    cellPressed: Color(0x0D14171E),
    glassSelected: Color(0x1414171E),
    border: Color(0x243C4350),
    textPrimary: Color(0xFF14171D),
    textSecondary: Color(0xFF5B6270),
    textTertiary: Color(0xFF6B7280),
    textDisabled: Color(0xFFB0B5BF),
    accent: Color(0xFF14171D),
    onAccent: Color(0xFFFFFFFF),
    selection: Color(0xFF3F5B8C),
    live: Color(0xFF4C9BFF),
    success: Color(0xFF1A7F37),
    successSurface: Color(0x1F1A7F37),
    warning: Color(0xFFA35F00),
    danger: Color(0xFFD2342A),
    dangerSurface: Color(0x1AD2342A),
  );
}

/// Omi's colour tokens: the v2 "Midnight Graphite" palette (`design/omi-flutter-v2/tokens.json`).
/// Each token is a getter on the active [OmiPalette] (dark or light, see Settings → Appearance);
/// these are the only colours new UI should name. Never cache one in a `static final`: it would
/// keep the palette it was first read in.
///
/// Surfaces step up from the ink page: [surface0] page, [surface1] cards and grouped settings,
/// [surface2] controls, fields and chips sitting on a card, [surface3] pressed fills, secondary
/// buttons and tiles, [surface4] the strongest fill. [sheet] is the background of a modal sheet, one
/// step above the page. Graphite with a faint cool cast (the Liquid Dock palette): calm and neutral
/// (INV-UI-1); the one saturated colour is [live].
///
/// Accents and primary actions are neutral: [accent] is the colour of [textPrimary] (white on the
/// dark palette, ink on the light one) with [onAccent] text. [selection] marks a switch that is on or a selected segment. [live] means
/// only "audio is being captured right now". Status colours ([success], [warning], [danger]) are
/// legible as text on every surface (danger is 7.0:1 on [surface0], 6.4:1 on [surface1]).
///
/// `AppStyles` (utils/ui_guidelines.dart) and the `ResponsiveHelper` palette predate these tokens.
/// Do not add new uses of them; migrate a file to [OmiColors] when you touch it.
abstract final class OmiColors {
  static OmiPalette _palette = OmiPalette.dark;

  /// The active palette.
  static OmiPalette get palette => _palette;

  /// Whether the light palette is active.
  static bool get isLight => _palette.isLight;

  /// Switches every colour and type token to [palette]. Only the app root calls this (the
  /// appearance scope), and it rebuilds the whole tree right after.
  static void use(OmiPalette palette) {
    if (identical(palette, _palette)) return;
    _palette = palette;
    OmiType._tinted.clear();
  }

  /// Page background.
  static Color get surface0 => _palette.surface0;

  /// Cards, grouped settings, dialogs, search fields.
  static Color get surface1 => _palette.surface1;

  /// Controls, fields and chips; rows that sit on a [surface1] card; snack bars.
  static Color get surface2 => _palette.surface2;

  /// Pressed and selected fills, secondary buttons, tiles.
  static Color get surface3 => _palette.surface3;

  /// The strongest fill (v2 `fillStrong`): a switch that is off, the track of a progress bar,
  /// past days in the week chart.
  static Color get surface4 => _palette.surface4;

  /// The raised thumb of a segmented control, one step above [surface4].
  static Color get segmentThumb => _palette.segmentThumb;

  /// Modal sheet background.
  static Color get sheet => _palette.sheet;

  /// A recessed panel on a [sheet] page: the device page's hero, where the device hangs.
  static Color get well => _palette.well;

  /// Floating glass (tab bar, Ask button) over a 26 pt blur: rgba(30, 34, 43, 0.58).
  static Color get glass => _palette.glass;

  /// A dock tab at rest (Liquid Dock `--tab-off`): 72 % white.
  static Color get dockTabIdle => _palette.dockTabIdle;

  /// The soft shadow under a white primary capsule (Liquid Dock `.cap.pri`): 25 % black.
  static Color get shadowSoft => _palette.shadowSoft;

  /// The dim over the page while the dock is open for a question.
  static Color get scrim => _palette.scrim;

  /// A row or cell while a finger is on it (v2 `.cell:active`): 5 % white.
  static Color get cellPressed => _palette.cellPressed;

  /// The selected item on glass (the tab bar's pill, the Ask button while Chat is open): 11 % white.
  static Color get glassSelected => _palette.glassSelected;

  /// Hairline dividers and card outlines: the blue-grey at 20 %.
  static Color get border => _palette.border;

  /// Titles and body text (15.5:1 on [surface1]).
  static Color get textPrimary => _palette.textPrimary;

  /// Descriptions and supporting text (6.9:1 on [surface1]).
  static Color get textSecondary => _palette.textSecondary;

  /// Metadata, placeholders, leading icons (4.9:1 on [surface1], 5.3:1 on [surface0]). Never
  /// darker: greys below this fail WCAG AA on the app's cards.
  static Color get textTertiary => _palette.textTertiary;

  /// Labels of disabled controls only. Exempt from contrast rules because it marks "unavailable";
  /// never use it for text a reader needs.
  static Color get textDisabled => _palette.textDisabled;

  /// The accent: primary buttons, spinners, the thumb of a switch that is on. Neutral per INV-UI-1.
  static Color get accent => _palette.accent;

  /// Text and icons drawn on [accent].
  static Color get onAccent => _palette.onAccent;

  /// A switch that is on, a selected segment's accent.
  static Color get selection => _palette.selection;

  /// Audio is being captured right now (the pendant's LED, the phone mic). Only while capture is
  /// real: never decoration, never a paused or finished recording.
  static Color get live => _palette.live;

  /// Success status, as text or icon.
  static Color get success => _palette.success;

  /// Tinted background behind [success] content (e.g. a "Connected" banner).
  static Color get successSurface => _palette.successSurface;

  /// Warning status (something needs the user), as text or icon.
  static Color get warning => _palette.warning;

  /// Destructive actions and errors, as text or icon.
  static Color get danger => _palette.danger;

  /// Tinted background behind [danger] content (destructive buttons, error banners).
  static Color get dangerSurface => _palette.dangerSurface;
}

/// Omi's type ramp, modelled on iOS text styles so that sizes land where the app's text already
/// sat (16 is `callout`, 17 is `body`, 20 is `title3`).
///
/// Every style carries [OmiColors.textPrimary] and the design's line height (iOS text styles:
/// body 17/22, footnote 13/18 …), with the extra leading split evenly above and below the glyphs as
/// the design's CSS does; override with `copyWith(color: ...)`.
abstract final class OmiType {
  /// 11 — badges, timestamps in dense rows.
  static TextStyle get caption => _tint(_caption);
  static const TextStyle _caption = TextStyle(
    fontSize: 11,
    height: 13 / 11,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 12 — the smallest running text: AM/PM under a time, chart labels (v2 `caption1`).
  static TextStyle get caption1 => _tint(_caption1);
  static const TextStyle _caption1 = TextStyle(
    fontSize: 12,
    height: 16 / 12,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 10 semibold — the tab bar's labels.
  static TextStyle get tabLabel => _tint(_tabLabel);
  static const TextStyle _tabLabel = TextStyle(
    fontSize: 10,
    height: 12 / 10,
    leadingDistribution: TextLeadingDistribution.even,
    letterSpacing: -0.1,
    fontWeight: FontWeight.w600,
  );

  /// 13 — secondary lines under a row title, footers, hints.
  static TextStyle get footnote => _tint(_footnote);
  static const TextStyle _footnote = TextStyle(
    fontSize: 13,
    height: 18 / 13,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 15 — descriptions, compact button labels, search text.
  static TextStyle get subhead => _tint(_subhead);
  static const TextStyle _subhead = TextStyle(
    fontSize: 15,
    height: 20 / 15,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 16 — button labels, snack bars, dense body copy.
  static TextStyle get callout => _tint(_callout);
  static const TextStyle _callout = TextStyle(
    fontSize: 16,
    height: 21 / 16,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 17 — row titles and reading text.
  static TextStyle get body => _tint(_body);
  static const TextStyle _body = TextStyle(
    fontSize: 17,
    height: 22 / 17,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
  );

  /// 17 semibold — app bar titles, sheet titles, emphasised row titles.
  static TextStyle get headline => _tint(_headline);
  static const TextStyle _headline = TextStyle(
    fontSize: 17,
    height: 22 / 17,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w600,
  );

  /// 20 semibold — section headers.
  static TextStyle get title3 => _tint(_title3);
  static const TextStyle _title3 = TextStyle(
    fontSize: 20,
    height: 25 / 20,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w600,
  );

  /// 22 bold — section headers over grouped rows, in-body headings (v2 `title2`).
  static TextStyle get title2 => _tint(_title2);
  static const TextStyle _title2 = TextStyle(
    fontSize: 22,
    height: 28 / 22,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w700,
  );

  /// 30 bold — a first-run step's title (v2 onboarding: Consent, Name, Language, Permissions).
  static TextStyle get display => _tint(_display);
  static const TextStyle _display = TextStyle(
    fontSize: 30,
    height: 36 / 30,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w700,
  );

  /// 28 bold — hero headings (empty hero, sheets).
  static TextStyle get title1 => _tint(_title1);
  static const TextStyle _title1 = TextStyle(
    fontSize: 28,
    height: 34 / 28,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w700,
  );

  /// 36 serif — onboarding and recap headlines (v2 uses the system serif there: New York on iOS,
  /// Noto Serif on Android; nothing is bundled).
  static TextStyle get serifDisplay => _tint(_serifDisplay);
  static const TextStyle _serifDisplay = TextStyle(
    fontSize: 36,
    height: 42 / 36,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w500,
    fontFamily: 'Georgia',
    fontFamilyFallback: ['serif'],
  );

  /// 23 serif — a recap headline on a Home card.
  static TextStyle get serifCard => _tint(_serifCard);
  static const TextStyle _serifCard = TextStyle(
    fontSize: 23,
    height: 30 / 23,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
    fontFamily: 'Georgia',
    fontFamilyFallback: ['serif'],
  );

  /// 19 serif — a memory as a row of the Memories list (v2 `Memories`).
  static TextStyle get serifRow => _tint(_serifRow);
  static const TextStyle _serifRow = TextStyle(
    fontSize: 19,
    height: 26 / 19,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w400,
    fontFamily: 'Georgia',
    fontFamilyFallback: ['serif'],
  );

  /// 28 serif — sheet and card headlines (plans, recap).
  static TextStyle get serifTitle => _tint(_serifTitle);
  static const TextStyle _serifTitle = TextStyle(
    fontSize: 28,
    height: 34 / 28,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w500,
    fontFamily: 'Georgia',
    fontFamilyFallback: ['serif'],
  );

  /// 34 bold — the largest display text; one per screen at most.
  static TextStyle get largeTitle => _tint(_largeTitle);
  static const TextStyle _largeTitle = TextStyle(
    fontSize: 34,
    height: 41 / 34,
    leadingDistribution: TextLeadingDistribution.even,
    fontWeight: FontWeight.w700,
  );

  static final Map<TextStyle, TextStyle> _tinted = Map<TextStyle, TextStyle>.identity();

  /// [base] in the active palette's [OmiColors.textPrimary], made once per palette.
  static TextStyle _tint(TextStyle base) =>
      _tinted.putIfAbsent(base, () => base.copyWith(color: OmiColors.textPrimary));
}

/// Corner radii. Pick by the size of the thing being rounded, not by taste. A corner nested inside
/// another is concentric: inner radius = outer radius − padding.
abstract final class OmiRadius {
  /// 8 — chips, tags, small inline fills.
  static const double sm = 8;

  /// 12 — buttons, text fields, list cards, snack bars.
  static const double md = 12;

  /// 16 — grouped settings cards, dialogs, large cards.
  static const double lg = 16;

  /// 24 — bottom sheet top corners, search fields.
  static const double xl = 24;

  /// 14 — a 52pt app or feature tile (v2 `tile52`).
  static const double tile = 14;

  /// 22 — grouped rows (v2 settings and list groups).
  static const double row = 22;

  /// 26 — cards on Home and in lists (v2).
  static const double card = 26;

  /// 28 — hero cards (v2).
  static const double cardLarge = 28;

  /// 32 — the floating tab bar capsule (v2).
  static const double tabBar = 32;

  /// 40 — top corners of a large sheet on iOS (v2). Android sheets use [sheetMaterial].
  static const double sheet = 40;

  /// 28 — top corners of a sheet on Android (v2).
  static const double sheetMaterial = 28;

  /// Fully rounded ends (capsules, avatars).
  static const double pill = 999;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlAll = BorderRadius.all(Radius.circular(xl));
  static const BorderRadius tileAll = BorderRadius.all(Radius.circular(tile));
  static const BorderRadius rowAll = BorderRadius.all(Radius.circular(row));
  static const BorderRadius cardAll = BorderRadius.all(Radius.circular(card));
  static const BorderRadius cardLargeAll = BorderRadius.all(Radius.circular(cardLarge));
  static const BorderRadius tabBarAll = BorderRadius.all(Radius.circular(tabBar));
  static const BorderRadius pillAll = BorderRadius.all(Radius.circular(pill));

  /// Top corners of a bottom sheet where the platform is not known ([sheetMaterial]). Prefer
  /// [sheetTopFor], which gives iOS its larger [sheet] corners.
  static const BorderRadius sheetTop = BorderRadius.vertical(top: Radius.circular(sheetMaterial));

  /// Top corners of a bottom sheet on [platform]: [sheet] (40) on Apple platforms, [sheetMaterial]
  /// (28) elsewhere.
  static BorderRadius sheetTopFor(TargetPlatform platform) {
    final apple = platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
    return BorderRadius.vertical(top: Radius.circular(apple ? sheet : sheetMaterial));
  }
}

/// Spacing steps. Page gutters are [md] (16) or [lg] (20); stack gaps come from this list.
abstract final class OmiSpacing {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;
}

/// Fixed sizes the v2 designs rely on. Containers of text still grow with the text size; these are
/// minimums and visual heights, not caps.
abstract final class OmiSize {
  /// The smallest touch target, on every platform.
  static const double minTap = 44;

  /// A primary capsule button's height at the default text size.
  static const double primaryButton = 50;

  /// A circular header button (back, close, account).
  static const double navButton = 44;

  /// The floating tab bar's height.
  static const double tabBar = 64;

  /// The round Ask Omi button beside the tab bar.
  static const double askButton = 64;

  /// The page gutter.
  static const double screenMargin = OmiSpacing.md;

  /// A grouped row's minimum height.
  static const double rowMinHeight = 52;
}

/// Animation durations and curves that honour the system's Reduce Motion setting.
///
/// Read durations through [OmiMotion.of] so that `MediaQuery.disableAnimations` (iOS Reduce
/// Motion, Android "Remove animations") turns them into [Duration.zero]:
///
/// ```dart
/// AnimatedOpacity(duration: OmiMotion.of(context).standard, curve: OmiMotion.standardCurve, ...)
/// ```
class OmiMotion {
  const OmiMotion._({
    required this.quick,
    required this.standard,
    required this.emphasized,
    required this.press,
    required this.sheet,
    required this.navigation,
  });

  /// Small state changes: a checkmark, a fade of a label, a pressed state.
  final Duration quick;

  /// Most transitions: expanding a row, swapping content, showing a banner.
  final Duration standard;

  /// Large movements that need to be followed by the eye: a panel sliding in.
  final Duration emphasized;

  /// A control shrinking under the finger (v2: scale 0.96, opacity 0.82), with [springCurve].
  final Duration press;

  /// A sheet rising or settling, with [springCurve].
  final Duration sheet;

  /// A page pushing or popping, with [springCurve].
  final Duration navigation;

  static const Duration quickDuration = Duration(milliseconds: 150);
  static const Duration standardDuration = Duration(milliseconds: 250);
  static const Duration emphasizedDuration = Duration(milliseconds: 400);
  static const Duration pressDuration = Duration(milliseconds: 180);
  static const Duration sheetDuration = Duration(milliseconds: 450);
  static const Duration navigationDuration = Duration(milliseconds: 500);

  /// One breath of the live LED (v2). A loop period, not a transition: under Reduce Motion the
  /// loop stops instead of running at zero length.
  static const Duration ledBreatheDuration = Duration(milliseconds: 2400);

  static const Curve standardCurve = Curves.easeInOut;
  static const Curve emphasizedCurve = Curves.easeOutCubic;

  /// The v2 spring, cubic-bezier(.32, .72, 0, 1): pushes, sheets, cards, toggles, press.
  static const Curve springCurve = Cubic(0.32, 0.72, 0, 1);

  /// Overshoots. Success moments only: a check popping in, a plan picked.
  static const Curve bouncyCurve = Cubic(0.34, 1.56, 0.64, 1);

  static const OmiMotion _full = OmiMotion._(
    quick: quickDuration,
    standard: standardDuration,
    emphasized: emphasizedDuration,
    press: pressDuration,
    sheet: sheetDuration,
    navigation: navigationDuration,
  );
  static const OmiMotion _reduced = OmiMotion._(
    quick: Duration.zero,
    standard: Duration.zero,
    emphasized: Duration.zero,
    press: Duration.zero,
    sheet: Duration.zero,
    navigation: Duration.zero,
  );

  /// The durations for this context: all [Duration.zero] when the user asked the system to remove
  /// animations.
  static OmiMotion of(BuildContext context) {
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return reduce ? _reduced : _full;
  }
}

/// The haptic vocabulary (v2 "Feel" board). Use these instead of calling [HapticFeedback] directly
/// so each kind of moment always feels the same:
///
/// | Moment | Haptic |
/// |---|---|
/// | tab, segment, switch, star, page | [selection] |
/// | complete a task, pull-to-refresh threshold | [light] |
/// | pause / resume listening, long-press lift | [medium] |
/// | capture starts | [soft] |
/// | conversation finished, pendant connected, saved | [success] |
/// | delete, destructive confirmation | [warning] |
/// | an error that needs the user | [error] |
///
/// On iOS the notification kinds are the system's own (UINotificationFeedbackGenerator, through the
/// `omi/haptics` channel); elsewhere, or if the channel is missing, they fall back to impacts.
abstract final class OmiHaptics {
  static const MethodChannel _channel = MethodChannel('omi/haptics');

  /// Settings → Appearance → Haptics. Off, every tap below is silent.
  static bool enabled = true;

  static Future<void> _impact(Future<void> Function() impact) async {
    if (enabled) await impact();
  }

  static bool get _ios => defaultTargetPlatform == TargetPlatform.iOS;

  static Future<void> _native(String kind, Future<void> Function() fallback) async {
    if (!enabled) return;
    if (_ios) {
      try {
        await _channel.invokeMethod<void>(kind);
        return;
      } on MissingPluginException {
        // Tests and embedders without the channel.
      } on PlatformException {
        // Fall through to the impact.
      }
    }
    await fallback();
  }

  /// Moving between places: a tab, a segment, a picker value; a switch; a star.
  static Future<void> selection() => _impact(HapticFeedback.selectionClick);

  /// Checking an item; the pull-to-refresh threshold.
  static Future<void> light() => _impact(HapticFeedback.lightImpact);

  /// Pausing or resuming listening; a long-press lift.
  static Future<void> medium() => _impact(HapticFeedback.mediumImpact);

  /// A firm thump: a hard limit reached, a recording discarded.
  static Future<void> heavy() => _impact(HapticFeedback.heavyImpact);

  /// Capture starts (the Live card grows into the screen).
  static Future<void> soft() => _native('soft', HapticFeedback.lightImpact);

  /// An action completed and the user should notice (conversation finished, connected, saved).
  static Future<void> success() => _native('success', HapticFeedback.mediumImpact);

  /// A destructive action or confirmation (delete).
  static Future<void> warning() => _native('warning', HapticFeedback.mediumImpact);

  /// An action failed or was refused and needs the user.
  static Future<void> error() => _native('error', HapticFeedback.heavyImpact);
}
