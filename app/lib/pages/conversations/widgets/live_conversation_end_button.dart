// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ends the conversation this phone is capturing: the same action as a pendant double-tap
/// (`CaptureProvider.forceProcessingCurrentConversation`). It sits in the live conversation's detail
/// bar beside Ask Omi, never on Home.
///
/// It shows only when [conversation] is this phone's own capture: its transcript holds a segment
/// this phone captured (a v3 window copies its recordings' segments, ids included). The live window
/// on the page can belong to another device (a desktop capture) while this phone also records, and
/// End would then finalize this phone's capture, not the one on screen; so with no shared segment,
/// including before the window's transcript has loaded, End is hidden. [leadingGap] goes with it,
/// so the Ask bar keeps the full width.
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

  @override
  Widget build(BuildContext context) {
    final conversation = widget.conversation;
    final mine = context.select<CaptureProvider?, bool>((capture) =>
        capture != null && LiveConversationEndButton.ownsCapture(conversation, capture.segments.map((s) => s.id)));
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
                if (!LiveConversationEndButton.ownsCapture(conversation, capture.segments.map((s) => s.id))) return;
                _ended = true;
                final setEndSuppressed = widget.onEndSuppressionChanged;
                setEndSuppressed?.call(true);
                // Settled: on success the capture has cleared and End is gone; after a failed drain the
                // capture keeps its segments, and End works again.
                unawaited(capture.forceProcessingCurrentConversation().whenComplete(() {
                  _ended = false;
                  if (LiveConversationEndButton.ownsCapture(conversation, capture.segments.map((s) => s.id))) {
                    setEndSuppressed?.call(false);
                  }
                }));
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
