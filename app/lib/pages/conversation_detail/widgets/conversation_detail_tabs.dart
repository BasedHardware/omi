import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/footer_glass.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Summary and Transcript under the title and its chips (Omi v8 `.ctabs`): 15/600 labels 22 pt
/// apart at the leading edge, the open one in the primary ink with a 2 pt underline sitting on a hairline,
/// the other in the tertiary ink. Swiping the pages below moves the underline with them. A shared
/// conversation says so at the trailing end, which opens [ConversationVisibilitySheet]; a private one
/// (the default) shows nothing there, and Visibility stays in the ⋯ menu.
///
/// In the experimental design there is no hairline and no underline: each tab is a capsule like
/// the chips above, and the open one is filled with the primary ink, its label in the page colour.
/// The fill slides between the two as the pages are swiped.
class ConversationDetailTabs extends StatelessWidget {
  const ConversationDetailTabs({super.key, required this.controller, required this.onTap, this.showVisibility = true});

  /// Index 0 is Summary, 1 is Transcript.
  final TabController controller;

  /// A tab was tapped (not swiped to).
  final ValueChanged<int> onTap;

  /// The saved conversation's "Shared" label; a live episode has no saved conversation to share yet.
  final bool showVisibility;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final pills = ExperimentalDesign.of(context);
    final style = OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: pills ? 1.2 : 1.4);
    // A scrollable TabBar shrinks to its labels (and the page's column would centre it), so the
    // hairline is drawn full width here and the underline paints over its last point.
    final hairline = pills ? Colors.transparent : ConversationDetailInk.hairline;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: DecoratedBox(
        decoration: BoxDecoration(
          // Transparent rather than absent, so the tabs keep their height in either design.
          border: Border(bottom: BorderSide(color: hairline)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                // The 44 pt tabs hold their labels up to this scale; past it the labels stop
                // growing instead of clipping, as the system's own tab bars do.
                child: MediaQuery.withClampedTextScaling(
                  maxScaleFactor: 1.6,
                  child: TabBar(
                    controller: controller,
                    isScrollable: true,
                    tabAlignment: TabAlignment.start,
                    padding: EdgeInsets.zero,
                    labelPadding: EdgeInsetsDirectional.only(end: pills ? _pillGap : 22),
                    indicatorSize: pills ? TabBarIndicatorSize.tab : TabBarIndicatorSize.label,
                    // The filled capsule covers the open tab's own capsule and slides to the other.
                    indicatorPadding: pills
                        ? const EdgeInsetsDirectional.only(
                            top: (_tabHeight - _pillHeight) / 2,
                            // The bar is the tabs plus the indicator's own 2 pt below them.
                            bottom: (_tabHeight - _pillHeight) / 2 + 2,
                            end: _pillGap,
                          )
                        : EdgeInsets.zero,
                    indicatorWeight: 2,
                    indicator: pills
                        ? ShapeDecoration(color: OmiColors.textPrimary, shape: const StadiumBorder())
                        : UnderlineTabIndicator(borderSide: BorderSide(color: OmiColors.textPrimary, width: 2)),
                    dividerHeight: 0,
                    labelColor: pills ? OmiColors.surface0 : OmiColors.textPrimary,
                    unselectedLabelColor: pills ? ConversationDetailInk.words : ConversationDetailInk.label,
                    labelStyle: style,
                    unselectedLabelStyle: style,
                    overlayColor: const WidgetStatePropertyAll(Colors.transparent),
                    splashFactory: NoSplash.splashFactory,
                    onTap: (index) {
                      OmiHaptics.selection();
                      onTap(index);
                    },
                    tabs: [
                      _tab(const Key('conversation_tab_summary'), l10n.summary, pills, Icons.auto_awesome_outlined),
                      _tab(const Key('conversation_tab_transcript'), l10n.transcript, pills, Icons.notes),
                    ],
                  ),
                ),
              ),
            ),
            if (showVisibility) const _VisibilityLabel(),
          ],
        ),
      ),
    );
  }

  static const double _tabHeight = 44;
  static const double _pillHeight = 34;
  static const double _pillGap = 8;

  /// A plain label, or in the experimental design a capsule with a hairline edge, the size of the
  /// chips above it, with a glyph before the label. The label's ink comes from the TabBar, so it crosses over as the tabs change.
  static Tab _tab(Key key, String label, bool pill, IconData icon) {
    if (!pill) return Tab(key: key, height: _tabHeight, text: label);
    return Tab(
      key: key,
      height: _tabHeight,
      // A pressed capsule grows by the design's rule for its height.
      child: PressSwell(
        height: _pillHeight,
        child: Container(
          height: _pillHeight,
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
            borderRadius: OmiRadius.pillAll,
            border: Border.all(color: ConversationDetailInk.hairline),
          ),
          // The glyph takes the label's ink from the TabBar, as the text does.
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 15),
              const SizedBox(width: 6),
              Text(label, maxLines: 1, softWrap: false),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Shared" with a globe in green, only when the conversation is not private (the default).
class _VisibilityLabel extends StatelessWidget {
  const _VisibilityLabel();

  @override
  Widget build(BuildContext context) {
    final conversation = context.watch<ConversationDetailProvider>().conversationOrNull;
    if (conversation == null || conversation.visibility == ConversationVisibility.private_) {
      return const SizedBox.shrink();
    }
    final l10n = context.l10n;
    final label = l10n.shared;
    final ink = OmiColors.success;
    return Semantics(
      button: true,
      label: '${l10n.visibility}: $label',
      excludeSemantics: true,
      child: GestureDetector(
        key: const Key('conversation_visibility'),
        behavior: HitTestBehavior.opaque,
        onTap: () {
          OmiHaptics.selection();
          trackConversationAction(ConversationActionAction.visibility, ConversationActionSurface.detailBody);
          ConversationVisibilitySheet.show(context, conversation);
        },
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              FaIcon(FontAwesomeIcons.globe, size: 12, color: ink),
              const SizedBox(width: 6),
              Text(
                label,
                style: OmiType.footnote.copyWith(color: ink, fontWeight: FontWeight.w500),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
