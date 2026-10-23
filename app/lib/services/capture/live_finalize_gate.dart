/// When the person last ended the live conversation. A second double-tap within [window] would only
/// end a near-empty stretch, so it is ignored.
class LiveFinalizeGate {
  LiveFinalizeGate({this.window = const Duration(seconds: 3), DateTime Function()? clock})
      : _clock = clock ?? DateTime.now;

  final Duration window;
  final DateTime Function() _clock;
  DateTime? _last;

  /// Whether a double-tap may end the conversation now.
  bool get allowsDoubleTap => _last == null || _clock().difference(_last!) >= window;

  void markFinalized() => _last = _clock();
}
