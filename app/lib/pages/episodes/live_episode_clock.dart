import 'dart:async';

import 'package:flutter/widgets.dart';

/// Refreshes only the live time label, independently of transcript/server updates.
/// Read the clock on each tick so backgrounding and delayed frames cannot accumulate drift.
class LiveEpisodeClock extends StatefulWidget {
  const LiveEpisodeClock({super.key, required this.clock, required this.builder});

  final DateTime Function() clock;
  final Widget Function(BuildContext context, DateTime now) builder;

  @override
  State<LiveEpisodeClock> createState() => _LiveEpisodeClockState();
}

class _LiveEpisodeClockState extends State<LiveEpisodeClock> with WidgetsBindingObserver {
  Timer? _tick;
  bool _tickerEnabled = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _start();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Subscribe even before the first tick so revealing Home catches up in its
    // first frame. Timer callbacks themselves are not muted by TickerMode.
    _tickerEnabled = TickerMode.valuesOf(context).enabled;
  }

  void _start() {
    _tick?.cancel();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted && _tickerEnabled) setState(() {});
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _start();
      if (_tickerEnabled) setState(() {});
    } else {
      _tick?.cancel();
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(context, widget.clock());
}
