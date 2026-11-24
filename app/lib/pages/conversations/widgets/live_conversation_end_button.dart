// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ends the conversation this phone is capturing: the same action as a pendant double-tap
/// (`CaptureProvider.forceProcessingCurrentConversation`). It sits in the live conversation's detail
/// bar beside Ask Omi, never on Home.
///
/// An overlapping transcript segment or the verified source recording establishes ownership.
/// A live window on another device must never end this phone's capture.
///
/// One tap ends it. The capture keeps its segments until the WAL drain finishes (seconds), so the
/// button is still on screen meanwhile; taps before that settles are ignored rather than starting a
/// second finalize, as the pendant's double-tap gate does.
class LiveConversationEndButton extends StatefulWidget {
  const LiveConversationEndButton(
      {super.key, required this.conversation, this.leadingGap = 10, this.onEndSuppressionChanged});

  final ServerConversation conversation;
  final double leadingGap;
  final ValueChanged<bool>? onEndSuppressionChanged;

  /// True when [conversation] holds any of this phone's captured segments.
  static bool ownsCapture(ServerConversation conversation, Iterable<String> capturedIds) {
    final captured = capturedIds.toSet();
    if (captured.isEmpty) return false;
    return conversation.transcriptSegments.any((segment) => captured.contains(segment.id));
  }

  @override
  State<LiveConversationEndButton> createState() => _LiveConversationEndButtonState();
}

class _LiveConversationEndButtonState extends State<LiveConversationEndButton> {
  bool _ended = false;

  bool _owns(ServerConversation conversation, CaptureProvider capture, bool v3Feedback) {
    final recordingId = v3Feedback ? capture.verifiedLiveServerRecordingId : null;
    return (recordingId != null && conversation.v3?.recordingIds.contains(recordingId) == true) ||
        LiveConversationEndButton.ownsCapture(
          conversation,
          capture.segments.map((s) => s.id),
        );
  }

  @override
  Widget build(BuildContext context) {
    final conversation = widget.conversation;
    final v3Feedback = context.select<ConversationsV3Provider?, bool>(
      (v3) => v3?.finishFeedbackEnabled ?? false,
    );
    final mine = context.select<CaptureProvider?, bool>(
      (capture) => capture != null && _owns(conversation, capture, v3Feedback),
    );
    if (!mine) return const SizedBox.shrink();
    final label = context.l10n.endConversation;
    return Padding(
      padding: EdgeInsetsDirectional.only(start: widget.leadingGap),
      child: Semantics(
        button: true,
        label: label,
        excludeSemantics: true,
        child: Material(
          key: const Key('live_conversation_end'),
          color: Colors.transparent,
          child: Ink(
            height: 56,
            decoration: BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.pillAll,
              border: Border.all(color: OmiColors.border, width: 1),
            ),
            child: InkWell(
              borderRadius: OmiRadius.pillAll,
              onTap: () {
                if (_ended) return;
                HapticFeedback.mediumImpact();
                final capture = context.read<CaptureProvider>();
                // Checked again at the tap: the capture may have moved on since the last build.
                if (!_owns(conversation, capture, v3Feedback)) return;
                _ended = true;
                final setEndSuppressed = widget.onEndSuppressionChanged;
                setEndSuppressed?.call(true);
                final v3 = context.read<ConversationsV3Provider?>();
                final previousFinish = v3?.finishRow;
                // Settled: on success the capture has cleared and End is gone; after a failed drain the
                // capture keeps its segments, and End works again.
                unawaited(
                  capture
                      .forceProcessingCurrentConversation(manualFinish: true, liveConversationId: conversation.id)
                      .whenComplete(() {
                    _ended = false;
                    if (_owns(conversation, capture, v3Feedback)) {
                      setEndSuppressed?.call(false);
                    }
                  }).catchError((Object _) {}),
                );
                if (v3?.finishRow != null &&
                    !identical(v3!.finishRow, previousFinish) &&
                    ModalRoute.of(context)?.isCurrent == true) {
                  unawaited(Navigator.of(context).maybePop());
                }
              },
              // At most half the bar, so Ask Omi keeps its room; a long translation scales down on one
              // line, then ellipsizes, rather than overflowing a 320pt screen.
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.45),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Center(
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.headline.copyWith(color: OmiColors.danger)),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
