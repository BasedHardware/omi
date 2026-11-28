import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/on_this_phone_section.dart';
import 'package:omi/pages/conversations/home_rows.dart' show isFailedConversation;
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/header_circle_button.dart';

/// Home's bell: always there, so the header never shifts, with a dot only when Activity holds
/// something new worth opening (see [ActivitySeen]). No count: nothing in Activity is owed.
///
/// The dot announces new recaps, unseen capture problems, and other unseen attention items. Two more
/// light its warning color, since Home no longer shows them (SCA-5226): a conversation that failed
/// and that Activity has not shown yet, and, for as long as any is there, a recording kept only on
/// this phone (it may be the only copy of the audio, so seeing it once is not enough).
class ActivityBellButton extends StatelessWidget {
  const ActivityBellButton({super.key, this.seen, this.pendingWork, this.captureMonitor});

  final ActivitySeen? seen;

  /// Injectable for tests; defaults to [PendingWorkStore.instance].
  final PendingWorkStore? pendingWork;

  /// Injectable for tests; defaults to [CaptureWedgeMonitor.instance].
  final CaptureWedgeMonitor? captureMonitor;

  @override
  Widget build(BuildContext context) {
    final state = seen ?? ActivitySeen.instance;
    final store = pendingWork ?? PendingWorkStore.instance;
    final monitor = captureMonitor ?? CaptureWedgeMonitor.instance;
    // Selected as a joined id string so a list read with the same failures does not rebuild the bell.
    final failedIds = context.select<ConversationProvider?, String>((p) => [
          for (final c in p?.conversations ?? const <ServerConversation>[])
            if (isFailedConversation(c) && !c.deleted && !c.discarded) c.id,
        ].join(','));
    final onPhone = context.select<LocalRecordingsProvider?, bool>(OnThisPhoneSection.hasContent);
    return ListenableBuilder(
      listenable:
          Listenable.merge([state.hasNew, store, monitor.hasUnseenCaptureAttention, store.failedConversationsSeen]),
      builder: (context, child) {
        // A failure Activity lists under its attention row, or not at all once dismissed, is not a
        // failed row there, so it does not keep the dot lit.
        final hidden = failedIds.isEmpty ? const <String>{} : store.attentionConversationIds;
        final failedUnseen = failedIds.isNotEmpty &&
            store.hasUnseenFailedConversation(failedIds.split(',').where((id) => !hidden.contains(id)));
        final attention = store.attention.any((item) => !item.seen && item.kind != 'conversation_summary_failed') ||
            monitor.hasUnseenCaptureAttention.value ||
            failedUnseen ||
            onPhone;
        final hasNew = (state.hasNew.value && state.describesCurrentOwner) || attention;
        final button = HeaderCircleButton(
          key: const ValueKey('home_activity_button'),
          semanticLabel: hasNew
              ? (attention ? context.l10n.activityAttentionSemantics : context.l10n.activityNewSemantics)
              : context.l10n.activity,
          icon: FaIcon(FontAwesomeIcons.bell, size: 16, color: OmiColors.textSecondary),
          onTap: () {
            OmiHaptics.selection();
            routeToPage(
                context, ActivityPage(seen: seen, pendingWork: pendingWork, captureWedgeMonitor: captureMonitor));
          },
        );
        if (!hasNew) return button;
        return Stack(
          clipBehavior: Clip.none,
          children: [
            button,
            PositionedDirectional(
              top: 9,
              end: 9,
              child: IgnorePointer(
                child: Container(
                  key: ValueKey(attention ? 'home_activity_attention_dot' : 'home_activity_dot'),
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: attention ? OmiColors.warning : OmiColors.accent,
                    shape: BoxShape.circle,
                    border: Border.all(color: OmiColors.surface1, width: 2),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}
