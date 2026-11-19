// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ends the conversation this phone is capturing: the same action as a pendant double-tap
/// (`CaptureProvider.forceProcessingCurrentConversation`). It sits in the live conversation's detail
/// bar beside Ask Omi, never on Home. It is hidden while this phone has nothing captured, since then
/// there is nothing here to end; [leadingGap] goes with it, so the Ask bar keeps the full width.
class LiveConversationEndButton extends StatelessWidget {
  const LiveConversationEndButton({super.key, this.leadingGap = 10});

  final double leadingGap;

  @override
  Widget build(BuildContext context) {
    final capturing = context.select<CaptureProvider?, bool>((capture) => capture?.segments.isNotEmpty ?? false);
    if (!capturing) return const SizedBox.shrink();
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
                context.read<CaptureProvider>().forceProcessingCurrentConversation();
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
