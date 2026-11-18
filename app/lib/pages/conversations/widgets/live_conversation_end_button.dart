// The End action on a v3 conversation in progress; owns only when it shows and what it calls.

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Ends the conversation this phone is capturing: the same action as a pendant double-tap
/// (`CaptureProvider.forceProcessingCurrentConversation`). The v3 live tile and its detail show it;
/// it is hidden while this phone has nothing captured, since then there is nothing here to end.
class LiveConversationEndButton extends StatelessWidget {
  const LiveConversationEndButton({super.key});

  @override
  Widget build(BuildContext context) {
    final capturing = context.select<CaptureProvider?, bool>((capture) => capture?.segments.isNotEmpty ?? false);
    if (!capturing) return const SizedBox.shrink();
    return OmiButton.secondary(
      key: const Key('live_conversation_end'),
      label: context.l10n.endConversation,
      size: OmiButtonSize.compact,
      onPressed: () => context.read<CaptureProvider>().forceProcessingCurrentConversation(),
    );
  }
}
