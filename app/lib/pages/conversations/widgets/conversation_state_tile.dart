import 'package:flutter/material.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A Home row's tile. For a v3 conversation it shows where the conversation is in the pipeline:
/// today's breathing dot while it is going, a spinner while its transcript arrives, a pen while its
/// summary is written, and the subject's emoji when done. Every other conversation shows its emoji,
/// as before.
class ConversationStateTile extends StatelessWidget {
  const ConversationStateTile({super.key, required this.conversation});

  final ServerConversation conversation;

  static const double extent = 36;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final state = conversation.v3?.tileState;
    final (Widget child, String? label) = switch (state) {
      ConversationTileState.live => (const OmiBreathingDot(key: Key('conversation_tile_live')), l10n.live),
      ConversationTileState.transcribing => (
          const OmiSpinner(key: Key('conversation_tile_transcribing'), size: OmiSpinnerSize.small),
          l10n.homeStepTranscribing,
        ),
      ConversationTileState.writing => (
          const ConversationWritingPen(key: Key('conversation_tile_writing')),
          l10n.episodeWritingNotes
        ),
      _ => (
          Text(
            conversation.structured.getEmoji(),
            key: const Key('conversation_tile_emoji'),
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w500),
          ),
          null,
        ),
    };
    final tile = Container(
      width: extent,
      height: extent,
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
      alignment: Alignment.center,
      child: child,
    );
    return label == null ? tile : Semantics(label: label, child: tile);
  }
}

/// The pen that marks a summary being written, on the Home tile and on the conversation page. It
/// nods gently while it writes; still under Reduce Motion.
class ConversationWritingPen extends StatefulWidget {
  const ConversationWritingPen({super.key, this.size = 18});

  final double size;

  @override
  State<ConversationWritingPen> createState() => _ConversationWritingPenState();
}

class _ConversationWritingPenState extends State<ConversationWritingPen> with SingleTickerProviderStateMixin {
  late final AnimationController _stroke =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void dispose() {
    _stroke.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = OmiMotion.of(context).standard == Duration.zero;
    final animate = !reduceMotion && TickerMode.valuesOf(context).enabled;
    if (animate) {
      if (!_stroke.isAnimating) _stroke.repeat(reverse: true);
    } else if (_stroke.isAnimating) {
      _stroke.stop();
    }
    final pen = Icon(Icons.edit_rounded, size: widget.size, color: OmiColors.textSecondary);
    if (!animate) return pen;
    return AnimatedBuilder(
      animation: _stroke,
      builder: (context, child) => Transform.rotate(
        angle: (Curves.easeInOut.transform(_stroke.value) - 0.5) * 0.25,
        child: Transform.translate(offset: Offset((_stroke.value - 0.5) * 2, 0), child: child),
      ),
      child: pen,
    );
  }
}
