import 'package:flutter/widgets.dart';

enum ChatScrollMode { followingBottom, freeScrolling }

/// Scroll-follow policy for the chat transcript.
///
/// Rebuilds and list padding must stay stable during a drag. Changing
/// [ListView] padding or calling setState on every pointer-move corrupts
/// sliver child extents and scrunches markdown/citation text.
class ChatScrollPolicy {
  static const liveEdgePx = 24.0;

  /// Extra space so the Latest chip can overlay the list without covering
  /// the last message. Must not depend on [ChatScrollMode] — a padding
  /// change mid-drag relayouts every child.
  static const transcriptBottomPadding = 72.0;

  static bool atLiveEdge(ScrollMetrics metrics) {
    return metrics.maxScrollExtent - metrics.pixels <= liveEdgePx && metrics.maxScrollExtent > 0;
  }

  /// Next mode, or null if the transcript should not rebuild.
  static ChatScrollMode? nextMode({
    required ChatScrollMode current,
    required bool isUserOrDragScroll,
    required bool atLiveEdge,
  }) {
    if (atLiveEdge) {
      if (current == ChatScrollMode.freeScrolling) {
        return ChatScrollMode.followingBottom;
      }
      return null;
    }
    if (isUserOrDragScroll && current == ChatScrollMode.followingBottom) {
      return ChatScrollMode.freeScrolling;
    }
    return null;
  }
}
