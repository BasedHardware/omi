import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/messaging_channels_provider.dart';

/// Waits on a connect sheet for the backend to record a new link for [channel].
///
/// The link is made outside the app (Telegram's Start, a text to Omi), so the sheet re-reads the
/// links every [interval] and whenever the app returns to the foreground, until a link for the
/// channel appears that was not there when waiting began, or the proof expires.
mixin ChannelLinkWaiter<T extends StatefulWidget> on State<T>, WidgetsBindingObserver {
  ChatChannel get waitChannel;

  /// The link has arrived.
  void onLinked(ChannelLink link);

  /// How often to re-read while waiting.
  @visibleForTesting
  static Duration interval = const Duration(seconds: 3);

  Timer? _timer;
  Set<String> _known = const {};
  DateTime? _until;
  bool _checking = false;

  bool get isWaitingForLink => _timer != null;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    stopWaiting();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && isWaitingForLink) unawaited(checkForLink());
  }

  /// Starts (or restarts) waiting until [until]. Links already present are ignored.
  void startWaiting({required DateTime until}) {
    final provider = context.read<MessagingChannelsProvider>();
    if (_timer == null) {
      _known = {for (final link in provider.links) link.id};
    }
    _until = until;
    _timer?.cancel();
    _timer = Timer.periodic(interval, (_) => unawaited(checkForLink()));
  }

  void stopWaiting() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> checkForLink() async {
    if (_checking || !mounted) return;
    final until = _until;
    if (until != null && DateTime.now().isAfter(until.add(interval))) {
      stopWaiting();
      if (mounted) setState(() {});
      return;
    }
    _checking = true;
    try {
      await context.read<MessagingChannelsProvider>().refreshLinks();
    } finally {
      _checking = false;
    }
    if (!mounted || !isWaitingForLink) return;
    for (final link in context.read<MessagingChannelsProvider>().links) {
      if (link.channel == waitChannel && !_known.contains(link.id)) {
        stopWaiting();
        onLinked(link);
        return;
      }
    }
  }
}
