// The v3 Home live row before the server has a window for the capture in progress.

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/conversation_state_tile.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
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
    // Bind to the exact live capture behind this placeholder. The preview controller is
    // capture-scoped; only an admitted, verified Omi pendant can contribute a snippet.
    // Final transcript text takes precedence, as it does in the capture card.
    final (state, source, verified, admitted, preview, device, _) = context
        .select<CaptureProvider, (CaptureDisplayState, String?, bool, bool, LivePreviewController?, BtDevice?, int)>(
      (capture) => (
        EpisodePresentation.displayState(capture),
        capture.liveCaptureSource,
        capture.pendantCaptureVerified,
        capture.liveWordsShown,
        capture.livePreview,
        capture.recordingDevice,
        // Load-bearing though discarded below: canShowPreview reads segments and photos without
        // subscribing, so this version is what rebuilds the row when final text or photos arrive.
        capture.segmentsPhotosVersion,
      ),
    );
    final capture = context.read<CaptureProvider>();
    final canShowPreview = source != null &&
        source != 'phone' &&
        device?.type == DeviceType.omi &&
        verified &&
        admitted &&
        EpisodePresentation.isListening(state) &&
        capture.segments.isEmpty &&
        capture.photos.isEmpty;
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
            decoration: BoxDecoration(
                color: ExperimentalDesign.of(context) ? Colors.transparent : OmiColors.surface1,
                borderRadius: OmiRadius.xlAll),
            padding: ExperimentalDesign.of(context)
                ? const EdgeInsetsDirectional.symmetric(horizontal: 4, vertical: 6)
                : const EdgeInsetsDirectional.symmetric(horizontal: 14, vertical: 14),
            child: Row(
              children: [
                Container(
                  width: ConversationStateTile.extentOf(context),
                  height: ConversationStateTile.extentOf(context),
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
                          style: experimentalRowTitleStyle(context), maxLines: 1, overflow: TextOverflow.ellipsis),
                      const SizedBox(height: 3),
                      ListenableBuilder(
                        // Listen while an admitted socket is resolving its verdict: the controller's
                        // admission phase change also notifies here.
                        listenable: preview ?? const AlwaysStoppedAnimation<double>(0),
                        builder: (context, _) {
                          final latest =
                              canShowPreview && preview?.admitted == true ? preview!.latestLine?.trim() : null;
                          return Text(
                            latest == null || latest.isEmpty ? l10n.live : latest,
                            key: const Key('v3_live_placeholder_preview'),
                            style: (ExperimentalDesign.of(context) ? OmiType.subhead : OmiType.footnote)
                                .copyWith(color: OmiColors.textSecondary),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          );
                        },
                      ),
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
