import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';

import 'package:omi/pages/activity/activity_page.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/header_circle_button.dart';

/// Home's bell: always there, so the header never shifts, with a dot only when Activity holds
/// something new worth opening (see [ActivitySeen]). No count: nothing in Activity is owed.
///
/// The dot lights for exactly four things: a new recap, work the server gave up on that the user
/// has not seen yet, a v3 conversation that failed and left Home for Activity, and an unseen capture
/// problem (full phone disk, stalled upload, or a pendant
/// that stopped sending audio). The latter two use the warning color. Home has no capture banner,
/// so this dot is how a stalled pendant reaches a reader who is not on the live page.
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
    // A failed v3 conversation left Home for Activity (X5); until Activity has shown it, it lights the
    // attention dot. Selected as a joined id string so a list read with the same failures does not
    // rebuild the bell.
    final failedIds = context.select<ConversationProvider?, String>((p) => [
          for (final c in p?.conversations ?? const <ServerConversation>[])
            if (c.v3?.tileState == ConversationTileState.failed && !c.deleted && !c.discarded) c.id,
        ].join(','));
    final v3 = context.select<ConversationsV3Provider?, bool>((p) => p?.v3 ?? false);
    return ListenableBuilder(
      listenable: Listenable.merge(
          [state.hasNew, store.hasUnseenAttention, monitor.hasUnseenCaptureAttention, store.failedConversationsSeen]),
      builder: (context, child) {
        // Activity lists these under their attention row, or not at all once dismissed: either way it
        // never shows them as failed rows, so they must not keep the dot lit.
        final hidden = failedIds.isEmpty ? const <String>{} : store.attentionConversationIds;
        final failedUnseen = v3 &&
            failedIds.isNotEmpty &&
            store.hasUnseenFailedConversation(failedIds.split(',').where((id) => !hidden.contains(id)));
        final attention = store.hasUnseenAttention.value || monitor.hasUnseenCaptureAttention.value || failedUnseen;
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
