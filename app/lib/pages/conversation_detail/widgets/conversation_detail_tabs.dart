import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/pages/conversations/conversation_action_analytics.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Summary and Transcript under the title and its chips (Omi v8 `.ctabs`): 15/600 labels 22 pt
/// apart at the leading edge, the open one in the primary ink with a 2 pt underline sitting on a hairline,
/// the other in the tertiary ink. Swiping the pages below moves the underline with them. A shared
/// conversation says so at the trailing end, which opens [ConversationVisibilitySheet]; a private one
/// (the default) shows nothing there, and Visibility stays in the ⋯ menu.
class ConversationDetailTabs extends StatelessWidget {
  const ConversationDetailTabs({super.key, required this.controller, required this.onTap});

  /// Index 0 is Summary, 1 is Transcript.
  final TabController controller;

  /// A tab was tapped (not swiped to).
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final style = OmiType.subhead.copyWith(fontWeight: FontWeight.w600, height: 1.4);
    // A scrollable TabBar shrinks to its labels (and the page's column would centre it), so the
    // hairline is drawn full width here and the underline paints over its last point.
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: ConversationDetailInk.hairline)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: TabBar(
                  controller: controller,
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  padding: EdgeInsets.zero,
                  labelPadding: const EdgeInsetsDirectional.only(end: 22),
                  indicatorSize: TabBarIndicatorSize.label,
                  indicator: UnderlineTabIndicator(borderSide: BorderSide(color: OmiColors.textPrimary, width: 2)),
                  dividerHeight: 0,
                  labelColor: OmiColors.textPrimary,
                  unselectedLabelColor: ConversationDetailInk.label,
                  labelStyle: style,
                  unselectedLabelStyle: style,
                  overlayColor: const WidgetStatePropertyAll(Colors.transparent),
                  splashFactory: NoSplash.splashFactory,
                  onTap: (index) {
                    OmiHaptics.selection();
                    onTap(index);
                  },
                  tabs: [
                    Tab(key: const Key('conversation_tab_summary'), height: 44, text: l10n.summary),
                    Tab(key: const Key('conversation_tab_transcript'), height: 44, text: l10n.transcript),
                  ],
                ),
              ),
            ),
            const _VisibilityLabel(),
          ],
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
