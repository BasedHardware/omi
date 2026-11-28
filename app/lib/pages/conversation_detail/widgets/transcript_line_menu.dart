import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';

/// One action of the menu a held transcript line opens.
typedef TranscriptLineAction = ({Key key, String title, FaIconData icon, VoidCallback onTap});

/// The iPhone form of a held transcript line's menu (experimental design): the page blurs and
/// dims, the line stays where it was on a card, and its actions are listed on a second card under
/// it (over it when there is no room below). A tap anywhere else closes it.
Future<void> showTranscriptLineMenu(
  BuildContext context, {
  required Rect lineRect,
  required Widget preview,
  required List<TranscriptLineAction> actions,
}) {
  return Navigator.of(context, rootNavigator: true).push(
    PageRouteBuilder<void>(
      opaque: false,
      barrierDismissible: true,
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
      barrierColor: Colors.transparent,
      transitionDuration: const Duration(milliseconds: 220),
      reverseTransitionDuration: const Duration(milliseconds: 160),
      pageBuilder: (context, animation, _) =>
          _TranscriptLineMenu(animation: animation, lineRect: lineRect, preview: preview, actions: actions),
    ),
  );
}

class _TranscriptLineMenu extends StatelessWidget {
  const _TranscriptLineMenu({
    required this.animation,
    required this.lineRect,
    required this.preview,
    required this.actions,
  });

  final Animation<double> animation;
  final Rect lineRect;
  final Widget preview;
  final List<TranscriptLineAction> actions;

  static const double _rowHeight = 46;
  static const double _gap = 8;
  static const double _cardPadding = 12;
  static const double _menuWidth = 196;
  static const double _iconColumn = 50;
  static const double _rowInset = 16;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final dark = Theme.of(context).brightness == Brightness.dark;
    final curved = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic, reverseCurve: Curves.easeIn);
    final menuHeight = actions.length * _rowHeight;
    final top = media.padding.top + 8;
    final bottom = media.size.height - media.padding.bottom - 8;
    // The card is the line with a margin; a very long line is cut to what leaves room for the menu.
    final cardHeight = (lineRect.height + _cardPadding * 2).clamp(0.0, bottom - top - menuHeight - _gap);
    final cardTop = (lineRect.top - _cardPadding).clamp(top, bottom - cardHeight - _gap - menuHeight);
    final cardLeft = (lineRect.left - _cardPadding).clamp(8.0, media.size.width);
    final cardWidth = (lineRect.width + _cardPadding * 2).clamp(0.0, media.size.width - cardLeft - 8);
    final surface = dark ? const Color(0xF02C2C2E) : const Color(0xF7FFFFFF);
    final shadow = BoxShadow(color: Color(dark ? 0x80000000 : 0x2E000000), blurRadius: 32, offset: const Offset(0, 10));

    // A route has no Material above it; without one the text draws with the debug underline.
    return Material(
      type: MaterialType.transparency,
      child: Stack(
        children: [
          Positioned.fill(
            child: GestureDetector(
              key: const Key('transcript_line_menu_scrim'),
              behavior: HitTestBehavior.opaque,
              onTap: () => Navigator.of(context).pop(),
              child: AnimatedBuilder(
                animation: curved,
                // omi-perf-allow: blur-filter -- a transient menu route over a still page, closed by any tap; nothing scrolls under it
                builder: (context, _) => BackdropFilter(
                  // omi-perf-allow: blur-filter -- same transient menu route
                  filter: ImageFilter.blur(sigmaX: 18 * curved.value, sigmaY: 18 * curved.value),
                  child: ColoredBox(color: Colors.black.withValues(alpha: (dark ? 0.45 : 0.18) * curved.value)),
                ),
              ),
            ),
          ),
          Positioned(
            top: cardTop,
            left: cardLeft,
            width: cardWidth,
            child: FadeTransition(
              opacity: curved,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  ScaleTransition(
                    scale: Tween<double>(begin: 1, end: 1.02).animate(curved),
                    child: Container(
                      key: const Key('transcript_line_menu_preview'),
                      width: double.infinity,
                      constraints: BoxConstraints(maxHeight: cardHeight),
                      clipBehavior: Clip.antiAlias,
                      padding: const EdgeInsets.all(_cardPadding),
                      decoration:
                          BoxDecoration(color: surface, borderRadius: BorderRadius.circular(18), boxShadow: [shadow]),
                      // The scrim below takes the taps: the copy of the line is for reading only.
                      child: IgnorePointer(
                        child: SingleChildScrollView(physics: const NeverScrollableScrollPhysics(), child: preview),
                      ),
                    ),
                  ),
                  const SizedBox(height: _gap),
                  SizedBox(
                    width: _menuWidth.clamp(0.0, cardWidth),
                    child: ScaleTransition(
                      alignment: Alignment.topLeft,
                      scale: Tween<double>(begin: 0.86, end: 1).animate(curved),
                      child: Container(
                        clipBehavior: Clip.antiAlias,
                        decoration:
                            BoxDecoration(color: surface, borderRadius: BorderRadius.circular(14), boxShadow: [shadow]),
                        child: Material(
                          type: MaterialType.transparency,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              for (var index = 0; index < actions.length; index++)
                                InkWell(
                                  key: actions[index].key,
                                  onTap: () {
                                    Navigator.of(context).pop();
                                    actions[index].onTap();
                                  },
                                  child: SizedBox(
                                    height: _rowHeight,
                                    child: Row(
                                      children: [
                                        // The glyph leads, in a column of its own so the titles line up.
                                        SizedBox(
                                          width: _iconColumn,
                                          child: Center(
                                            child: FaIcon(actions[index].icon, size: 17, color: OmiColors.textPrimary),
                                          ),
                                        ),
                                        Expanded(
                                          child: Container(
                                            height: _rowHeight,
                                            alignment: AlignmentDirectional.centerStart,
                                            margin: const EdgeInsetsDirectional.only(end: _rowInset),
                                            // The rule sits over the title only: it starts after the
                                            // glyph and stops short of the card's edge.
                                            decoration: index == 0
                                                ? null
                                                : BoxDecoration(
                                                    border: Border(
                                                      top: BorderSide(
                                                          color: OmiColors.textPrimary.withValues(alpha: 0.12),
                                                          width: 0.5),
                                                    ),
                                                  ),
                                            child: Text(
                                              actions[index].title,
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                              style: OmiType.body.copyWith(color: OmiColors.textPrimary),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
