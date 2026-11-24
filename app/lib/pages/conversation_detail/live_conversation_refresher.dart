// Keeps an open v3 conversation that has not reached its summary current; owns only the re-read cadence.

import 'dart:async';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';

/// Re-reads the open conversation every [every] while it is still going or its transcript is still
/// arriving (tile state live or transcribing), so its transcript stays current and the page sees it
/// move on to writing its summary. The detail page owns it, so it runs whichever tab is selected: a
/// live conversation opens on Transcript, where the Summary tab is not built. One read at a time, and
/// none while another route covers the page.
class LiveConversationRefresher {
  LiveConversationRefresher({
    required this.read,
    required this.refresh,
    required this.inFront,
    this.every = const Duration(seconds: 15),
  });

  final ServerConversation? Function() read;
  final Future<bool> Function() refresh;
  final bool Function() inFront;
  final Duration every;

  Timer? _timer;
  bool _reading = false;

  /// Whether [conversation] has not reached its summary yet: still going, or its transcript still arriving.
  static bool awaitsSummary(ServerConversation? conversation) {
    final state = conversation?.v3?.tileState;
    return state == ConversationTileState.live || state == ConversationTileState.transcribing;
  }

  void start() => _timer ??= Timer.periodic(every, (_) => _tick());

  void _tick() {
    if (_reading || !inFront() || !awaitsSummary(read())) return;
    _reading = true;
    unawaited(refresh().catchError((Object _) => false).whenComplete(() => _reading = false));
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }
}
