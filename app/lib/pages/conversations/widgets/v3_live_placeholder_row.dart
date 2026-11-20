// The v3 Home live row before the server has a window for the capture in progress.

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Stands in for the v3 live conversation row while this phone streams a capture the server has not
/// shown as a window yet: before the first window, or between one window closing and the next
/// opening. It has the live row's card, tile and breathing dot, so a v3 user sees one presentation
/// for the whole capture instead of the pendant capture card coming back in each gap. It opens the
/// live transcript, as the capture card did.
class V3LivePlaceholderRow extends StatelessWidget {
  const V3LivePlaceholderRow({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // The capture's own state (listening, paused, reconnecting…), resolved as the capture card did.
    final state = context.select<CaptureProvider, CaptureDisplayState>(EpisodePresentation.displayState);
    final title = captureStateLabel(l10n, state);
    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: Semantics(
        button: true,
        label: title,
        hint: l10n.liveTranscript,
        excludeSemantics: true,
        child: GestureDetector(
          key: const Key('v3_live_placeholder'),
          behavior: HitTestBehavior.opaque,
          onTap: () => routeToPage(
              context, LiveEpisodePage(topConversationId: context.read<CaptureProvider>().topConversationId)),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
            padding: const EdgeInsetsDirectional.symmetric(horizontal: 14, vertical: 14),
            child: Row(
              children: [
                Container(
                  width: ConversationStateTile.extent,
                  height: ConversationStateTile.extent,
                  decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                  alignment: Alignment.center,
                  child: const OmiBreathingDot(),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: Theme.of(context).textTheme.titleMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 3),
                      Text(l10n.live, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary), maxLines: 1),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
