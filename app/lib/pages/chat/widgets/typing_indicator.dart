import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// Omi is thinking: the Omi mark with its dots lighting in sequence (v2 `OmiRingLogo`, chase).
///
/// Honours Reduce Motion: the mark then stands still. Decorative; the chat announces the reply.
class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return OmiRingLogo(size: 20, mode: OmiRingMode.chase, color: OmiColors.textSecondary);
  }
}
