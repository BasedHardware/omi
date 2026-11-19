// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

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
class LiveConversationEndButton extends StatelessWidget {
  const LiveConversationEndButton({super.key, required this.conversation, this.leadingGap = 10});

  final ServerConversation conversation;
  final double leadingGap;

  /// True when [conversation] holds any of this phone's captured segments.
  static bool ownsCapture(ServerConversation conversation, Iterable<String> capturedIds) {
    final captured = capturedIds.toSet();
    if (captured.isEmpty) return false;
    return conversation.transcriptSegments.any((segment) => captured.contains(segment.id));
  }

  @override
  Widget build(BuildContext context) {
    final mine = context.select<CaptureProvider?, bool>(
        (capture) => capture != null && ownsCapture(conversation, capture.segments.map((s) => s.id)));
    if (!mine) return const SizedBox.shrink();
    final label = context.l10n.endConversation;
    return Padding(
      padding: EdgeInsetsDirectional.only(start: leadingGap),
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
                HapticFeedback.mediumImpact();
                final capture = context.read<CaptureProvider>();
                // Checked again at the tap: the capture may have moved on since the last build.
                if (!ownsCapture(conversation, capture.segments.map((s) => s.id))) return;
                capture.forceProcessingCurrentConversation();
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
