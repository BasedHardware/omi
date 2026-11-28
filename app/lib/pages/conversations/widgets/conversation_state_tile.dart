import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import 'package:provider/provider.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/conversations/early_title.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A Home row's tile. For an account on v3 it shows where the conversation is in the pipeline:
/// today's breathing dot while it is going, a spinner while its transcript arrives, a pen while its
/// summary is written, and the subject's emoji when done. Otherwise (and for every conversation without
/// v3 fields, or after a rollback leaves them on old documents) it shows the emoji, as before.
///
/// The tile changes in place: live → transcribing → writing → done cross-fade at
/// `OmiMotion.standard`, never a pop, and a screen reader hears when the summary is ready.
class ConversationStateTile extends StatefulWidget {
  const ConversationStateTile({super.key, required this.conversation});

  final ServerConversation conversation;

  /// The tile's side: 36pt, or 44pt in the experimental design.
  static double extentOf(BuildContext context) => ExperimentalDesign.of(context) ? 44 : 36;

  /// The tile's fill and corners. In the experimental design a hairline in the border colour
  /// outlines it, so the tile keeps its edge on the bare page and under a pressed row.
  static BoxDecoration decorationOf(BuildContext context) => BoxDecoration(
        color: OmiColors.surface2,
        borderRadius: OmiRadius.mdAll,
        border: ExperimentalDesign.of(context) ? Border.all(color: OmiColors.border, width: 0.5) : null,
      );

  /// Reliability experiment `early_title_icon`: whether a row still in the pipeline already shows its
  /// emoji, because the server has fixed its title and emoji ([titledBeforeSummary]); the row's status
  /// line goes on saying what is still being done. Off, always false.
  static bool showsEmojiEarly(ServerConversation conversation, ConversationTileState? state) =>
      state != null && titledBeforeSummary(conversation);

  @override
  State<ConversationStateTile> createState() => _ConversationStateTileState();
}

class _ConversationStateTileState extends State<ConversationStateTile> {
  ConversationTileState? _shown;

  @override
  Widget build(BuildContext context) {
    final conversation = widget.conversation;
    final l10n = context.l10n;
    final v3On = context.select<ConversationsV3Provider?, bool>((p) => p?.v3 ?? false);
    final state = v3On ? conversation.v3?.tileState : null;
    final previous = _shown;
    _shown = state;
    if (state == ConversationTileState.done &&
        (previous == ConversationTileState.transcribing || previous == ConversationTileState.writing)) {
      final view = View.of(context);
      final direction = Directionality.of(context);
      final message = l10n.finishedSummaryReady;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        SemanticsService.sendAnnouncement(view, message, direction);
      });
    }
    // The emoji of a row whose title and emoji are already fixed; [_shown] still follows the real state.
    final tileState = ConversationStateTile.showsEmojiEarly(conversation, state) ? ConversationTileState.done : state;
    final (Widget child, String? label) = switch (tileState) {
      ConversationTileState.live => (const OmiBreathingDot(key: Key('conversation_tile_live')), l10n.live),
      ConversationTileState.transcribing => (
          const OmiSpinner(key: Key('conversation_tile_transcribing'), size: OmiSpinnerSize.small),
          l10n.homeStepTranscribing,
        ),
      ConversationTileState.writing => (
          const ConversationWritingPen(key: Key('conversation_tile_writing')),
          l10n.conversationWritingSummary
        ),
      ConversationTileState.failed => (
          Icon(Icons.error_outline_rounded,
              key: const Key('conversation_tile_failed'), size: 20, color: OmiColors.warning),
          l10n.conversationSummaryFailed,
        ),
      _ => (_emoji(context, conversation.structured.getEmoji()), null),
    };
    final tile = Container(
      width: ConversationStateTile.extentOf(context),
      height: ConversationStateTile.extentOf(context),
      decoration: ConversationStateTile.decorationOf(context),
      alignment: Alignment.center,
      child: OmiCrossFade(
        alignment: Alignment.center,
        // Done and no-state both show the emoji: one key, so the emoji never cross-fades with itself.
        child: KeyedSubtree(key: ValueKey('tile_${label == null ? 'emoji' : tileState!.name}'), child: child),
      ),
    );
    return label == null ? tile : Semantics(label: label, child: tile);
  }
}

Widget _emoji(BuildContext context, String emoji) {
  const key = Key('conversation_tile_emoji');
  if (!ExperimentalDesign.of(context)) {
    return Text(emoji, key: key, style: OmiType.title3.copyWith(fontWeight: FontWeight.w500));
  }
  // The system emoji font draws its glyph at the left of an advance wider than the glyph:
  // measured on an iPhone at this size, the picture sits 1pt left of the tile's centre.
  // The offset puts the picture, not its text box, in the centre.
  return Transform.translate(
    offset: const Offset(1, 0),
    child: Text(
      emoji,
      key: key,
      textAlign: TextAlign.center,
      style: OmiType.title3.copyWith(
          fontSize: 24, // omi-ux-allow: font-size-literal -- an emoji glyph sized to its tile, not text
          fontWeight: FontWeight.w400,
          height: 1,
          leadingDistribution: TextLeadingDistribution.even),
    ),
  );
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
