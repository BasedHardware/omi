import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The two-bubbles glyph (FontAwesome `comments`, regular weight) that marks Ask Omi everywhere it
/// appears, so every entry point reads as one family.
const FaIconData kAskOmiGlyph = FontAwesomeIcons.comments;

/// The Home shell has no tab bar: Home and Tasks are switched at the top of the screen, and the only
/// thing at the bottom is Home's floating [Ask Omi | record] row. These helpers are the one source
/// of the space that row and the system inset take, so nothing positions itself with a literal.

/// Height of the fade that dissolves list content just above the chat bar. Paint only.
const double kHomeBottomFadeHeight = 20;

/// Gap between the chat bar and the system inset (or the screen edge when there is none).
const double kHomeChatBarBottomGap = 8;

/// Height of Home's floating chat bar.
const double kHomeChatBarHeight = 62;

/// Space every Home-shell page leaves below its last row so it can scroll clear of the screen edge.
const double kHomeScrollEndPadding = 24;

/// The bottom inset the shell reserves for system chrome.
///
/// viewPadding, not padding: the home Scaffold sets resizeToAvoidBottomInset: false, and
/// padding.bottom collapses to zero while a keyboard is open.
double homeBottomInset(BuildContext context) => MediaQuery.viewPaddingOf(context).bottom;

/// Distance from the bottom of the screen that a Home-shell page without the chat bar (Tasks)
/// clears: the system inset plus a little air.
double homeBottomClearance(BuildContext context) => homeBottomInset(context) + kHomeScrollEndPadding;

/// Offset from the bottom of the screen to the bottom edge of Home's chat bar.
double homeChatBarOffset(BuildContext context) => homeBottomInset(context) + kHomeChatBarBottomGap;

/// Distance from the bottom of the screen that Home content clears to stay out from under the
/// floating chat bar, with a little air above it.
double homeChatBarClearance(BuildContext context) => homeChatBarOffset(context) + kHomeChatBarHeight + 20;

/// Interpolate the light fade through transparent page-coloured pixels. A zero-alpha black stop
/// darkens intermediate gradient colours and shows up as a grey band against the light page.
Color get _fadeStart =>
    OmiColors.active == OmiPalette.light ? OmiColors.surface0.withValues(alpha: 0) : Colors.transparent;

/// The backdrop behind Home's floating [Ask Omi | record] row: solid page colour from the screen
/// edge up through the row, fading out above it, so list content never shows between the chat bar
/// and the record button or around them. Paint only; a [Stack] child placed before the row.
class HomeChatBarBackdrop extends StatelessWidget {
  const HomeChatBarBackdrop({super.key});

  @override
  Widget build(BuildContext context) {
    final solid = homeChatBarOffset(context) + kHomeChatBarHeight;
    final height = solid + kHomeBottomFadeHeight;
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      height: height,
      child: IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0.0, kHomeBottomFadeHeight / height, 1.0],
              colors: [_fadeStart, OmiColors.surface0, OmiColors.surface0],
            ),
          ),
        ),
      ),
    );
  }
}
