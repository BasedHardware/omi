import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/omi_canvas.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/ui/components/omi_glass.dart';
import 'package:omi/ui/components/omi_line_icon.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The two-bubbles glyph (FontAwesome `comments`, regular weight) that marks Ask Omi everywhere it
/// appears, so every entry point reads as one family.
const FaIconData kAskOmiGlyph = FontAwesomeIcons.comments;

/// The Home shell has no tab bar: Home and Tasks are switched at the top of the screen, and the only
/// thing at the bottom is Home's floating [Ask Omi | record] row. These helpers are the one source
/// of the space that row and the system inset take, so nothing positions itself with a literal.

/// Height of the fade that dissolves list content above the chat bar. Paint only.
const double kHomeBottomFadeHeight = 48;

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

/// Home's page in light mode blends into a warm white toward the bottom of the screen (Omi v8):
/// white down to 62% of the height, half-way by 72%, the warm tint from 82%. Fixed to the screen,
/// under the floating row. Nothing in dark.
class HomeWarmBlend extends StatelessWidget {
  const HomeWarmBlend({super.key});

  @override
  Widget build(BuildContext context) {
    // The palette is a static, so the theme is what rebuilds this when the app turns dark on a Home
    // already on screen. Dark has no blend. With no blend it is still positioned: a bare box would
    // size Home's bottom Stack to nothing and take the floating row with it.
    const none = Positioned.fill(child: SizedBox.shrink());
    if (Theme.brightnessOf(context) == Brightness.dark) return none;
    final blend = OmiColors.canvasBlend;
    if (blend.a == 0) return none;
    return Positioned.fill(
      child: IgnorePointer(
        child: DecoratedBox(
          key: const ValueKey('home_warm_blend'),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: const [0.62, 0.72, 0.82],
              colors: [blend.withValues(alpha: 0), blend.withValues(alpha: blend.a / 2), blend],
            ),
          ),
        ),
      ),
    );
  }
}

/// The backdrop behind Home's floating [Ask Omi | record] row: list content fades into the page
/// colour as it passes under the glass row (half by the row's top, solid below its bottom edge), so
/// the row stays legible while what scrolls beneath shows through its blur. Paint only; a [Stack]
/// child placed before the row.
class HomeChatBarBackdrop extends StatelessWidget {
  const HomeChatBarBackdrop({super.key});

  @override
  Widget build(BuildContext context) {
    // Fade through transparent page-coloured pixels: a zero-alpha black stop greys the light page.
    // Read after the theme, so the fade follows a switch between light and dark (the palette is a
    // static).
    Theme.brightnessOf(context);
    final page = OmiCanvas.pageOf(context);
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      height: homeChatBarOffset(context) + kHomeChatBarHeight + kHomeBottomFadeHeight,
      child: IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: const [0.0, 0.4, 0.76],
              colors: [page.withValues(alpha: 0), page.withValues(alpha: 0.5), page],
            ),
          ),
        ),
      ),
    );
  }
}

/// Home's "Ask anything" bar, left of the record button in the floating row: the same height and
/// glass as the record button, so the pair reads as one set. The label opens the chat to type; the
/// round mic at the end opens it already listening, as main's Home mic does (David, 2026-10-03).
class HomeAskOmiButton extends StatelessWidget {
  const HomeAskOmiButton({super.key, required this.onTap, required this.onVoice});

  final VoidCallback onTap;
  final VoidCallback onVoice;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final label = l10n.askAnythingButton;
    return OmiGlass(
      shape: const StadiumBorder(),
      blur: true,
      child: SizedBox(
        height: kHomeChatBarHeight,
        child: Row(
          children: [
            Expanded(
              child: Semantics(
                container: true,
                button: true,
                label: label,
                onTap: onTap,
                excludeSemantics: true,
                child: GestureDetector(
                  key: const ValueKey('home_ask_omi_bar'),
                  behavior: HitTestBehavior.opaque,
                  onTap: onTap,
                  child: Padding(
                    padding: const EdgeInsetsDirectional.only(start: 22),
                    child: Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: Text(
                        label,
                        style: OmiType.callout.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            // The mic owns the bar's full height and its rounded end, not just the circle, so a near
            // miss still talks instead of opening text chat.
            Semantics(
              container: true,
              button: true,
              label: l10n.voiceMode,
              onTap: onVoice,
              excludeSemantics: true,
              child: GestureDetector(
                key: const ValueKey('home_ask_omi_voice'),
                behavior: HitTestBehavior.opaque,
                onTap: onVoice,
                child: Padding(
                  padding: const EdgeInsetsDirectional.only(start: 8, end: 6),
                  child: Center(
                    child: Container(
                      width: 46,
                      height: 46,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: OmiColors.textPrimary.withValues(alpha: 0.07),
                        shape: BoxShape.circle,
                      ),
                      child: OmiLineIcon(OmiLineGlyph.voice, size: 21, color: OmiColors.textPrimary),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
