import 'package:flutter/material.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/ui/ui.dart';

/// Reliability experiment `instant_live_text`: the newest lines the server streamed to this phone's
/// listening connection, under the open conversation's transcript, until the conversation itself holds
/// them. Shown only where the phone has no "Live on this phone" lines of its own.
class StreamedLinesTail extends StatelessWidget {
  const StreamedLinesTail({super.key, required this.capture, required this.lines, this.whenEmpty});

  /// Rebuilds the tail: the capture provider, which notifies when a line arrives or changes.
  final Listenable capture;

  /// The lines the conversation's transcript does not already cover, oldest first.
  final List<LivePreviewLine> Function() lines;
  final Widget? whenEmpty;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: capture,
      builder: (context, _) {
        final current = lines();
        if (current.isEmpty) return whenEmpty ?? const SizedBox.shrink();
        return Column(
          key: const Key('streamed_lines_tail'),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < current.length; i++)
              Padding(
                key: ValueKey('streamed_line_${current[i].id}'),
                padding: EdgeInsets.fromLTRB(OmiSpacing.md, i == 0 ? OmiSpacing.md : 0, OmiSpacing.md, OmiSpacing.sm),
                child: Text(current[i].text, style: OmiType.body.copyWith(height: 1.4, color: OmiColors.textSecondary)),
              ),
          ],
        );
      },
    );
  }
}
