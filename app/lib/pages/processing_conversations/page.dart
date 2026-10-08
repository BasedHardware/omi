import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_capturing/capture_state_header.dart';
import 'package:omi/pages/conversation_capturing/page.dart' show groupCapturePhotos;
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/string_utils.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/photos_grid.dart';

/// A conversation whose recording has ended and whose summary is being made.
///
/// Same header as the live and saved pages (circled back, the state as the title: Processing).
/// There is one view — the transcript or photos captured so far — because the summary does not
/// exist yet; the saved page adds its tabs once it does. When processing looks stuck it offers the
/// same "Try again" as the processing card on the conversation list.
class ProcessingConversationPage extends StatefulWidget {
  final ServerConversation conversation;

  /// Optional clock override for tests.
  final DateTime Function()? now;

  /// Optional reprocess override for tests.
  final Future<ServerConversation?> Function(String conversationId)? reprocess;

  const ProcessingConversationPage({super.key, required this.conversation, this.now, this.reprocess});

  @override
  State<ProcessingConversationPage> createState() => _ProcessingConversationPageState();
}

class _ProcessingConversationPageState extends State<ProcessingConversationPage> {
  late final ProcessingRetryController _retry;

  @override
  void initState() {
    super.initState();
    _retry = ProcessingRetryController(conversation: widget.conversation, now: widget.now, reprocess: widget.reprocess)
      ..addListener(_onRetryChanged);
  }

  void _onRetryChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didUpdateWidget(ProcessingConversationPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    _retry.updateConversation(widget.conversation);
  }

  @override
  void dispose() {
    _retry.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final conversation = widget.conversation;
    final hasContent = conversation.transcriptSegments.isNotEmpty || conversation.photos.isNotEmpty;
    final Widget content = hasContent
        ? getTranscriptWidget(
            false,
            conversation.transcriptSegments,
            conversation.photos,
            null,
            conversationId: conversation.id,
            bottomMargin: OmiSpacing.xxl,
          )
        : OmiEmptyState(icon: Icons.hourglass_empty, title: context.l10n.noContentToDisplay);
    final classic = Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: const ConversationStateAppBar(
        state: CaptureDisplayState.processing,
        backKey: ValueKey('processing_conversation_back_button'),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
        child: _retry.timedOut
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [Expanded(child: content), _buildTimeoutNotice(context)],
              )
            : content,
      ),
    );
    if (!nativePresentationEnabled) return classic;
    return _buildNative(context, classic);
  }

  /// The processing card's timeout notice and retry, under the transcript.
  Widget _buildTimeoutNotice(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              context.l10n.processingTakingLonger,
              style: TextStyle(color: OmiColors.textTertiary, fontSize: 13, height: 1.3),
            ),
            const SizedBox(height: 10),
            TextButton(
              key: const Key('processing_page_retry_button'),
              onPressed: _retry.retrying ? null : () => _retry.retry(context),
              style: TextButton.styleFrom(
                foregroundColor: OmiColors.textPrimary,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                minimumSize: const Size(44, 44),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: _retry.retrying ? const OmiSpinner(size: OmiSpinnerSize.small) : Text(context.l10n.tryAgain),
            ),
          ],
        ),
      ),
    );
  }

  /// Photo groups (opened in the existing viewer, which loads the images), then the transcript as
  /// literal text, in the classic page's order.
  Widget _buildNative(BuildContext context, Widget classic) {
    final l10n = context.l10n;
    final conversation = widget.conversation;
    final dates = OmiDateFormat.of(context);
    final segments = conversation.transcriptSegments;
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final names = SpeakerNames.forSegments(segments, people: people, l10n: l10n);
    final photos = List<ConversationPhoto>.from(conversation.photos)
      ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
    final groups = groupCapturePhotos(photos);
    final rows = [
      for (var index = 0; index < groups.length; index++)
        NativeRow(
          'processing_photos:$index',
          groups[index].length > 1
              ? '${dates.time(groups[index].first.createdAt)} · ${l10n.conversationPhotosCount(groups[index].length)}'
              : dates.time(groups[index].first.createdAt),
          kind: 'navigation',
          symbol: 'camera',
          action: (_) => MediaViewerPage.open(
            context,
            items: mediaItemsForPhotos(photos, conversation.id),
            initialIndex: photos.indexOf(groups[index].first),
          ),
        ),
      for (var index = 0; index < segments.length; index++)
        NativeRow(
          'processing_segment:$index',
          [
            tryDecodingText(segments[index].text),
            for (final translation in segments[index].translations) tryDecodingText(translation.text),
          ].join('\n'),
          kind: 'label',
          subtitle: '${names.forSegment(segments[index])} · ${OmiDuration.offset(segments[index].start)}',
        ),
    ];
    return IosNativeSurface(
      title: conversationStateTitle(l10n, CaptureDisplayState.processing),
      fallback: classic,
      empty: l10n.noContentToDisplay,
      // The classic header's spinner, which also covers a Try again in flight (its row then waits).
      loading: true,
      loadingLabel: captureStateLabel(l10n, CaptureDisplayState.processing),
      toolbar: [
        NativeRow('processing_back', l10n.back,
            symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
      ],
      sections: [
        NativeSection('processing_timeline', [
          ...rows,
          // A reader shows no empty copy of its own.
          if (rows.isEmpty) NativeRow('processing_empty', l10n.noContentToDisplay, kind: 'label'),
        ]),
      ],
      reader: NativeReader(
        footer: [
          if (_retry.timedOut) ...[
            NativeRow('processing_timeout', l10n.processingTakingLonger, kind: 'label'),
            NativeRow('processing_retry', l10n.tryAgain,
                enabled: !_retry.retrying, action: (_) => _retry.retry(context)),
          ],
        ],
      ),
    );
  }
}
