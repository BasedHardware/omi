import 'package:flutter/foundation.dart';

/// Global "the Cortex agent is taking actions" flag. When true, the app paints a
/// blue glow around the screen edges (see CortexAgentEdgeOverlay) to signal the
/// agent is working — mirroring the desktop behavior. The agent works without
/// otherwise interrupting the user.
class CortexAgentActivity {
  CortexAgentActivity._();
  static final CortexAgentActivity instance = CortexAgentActivity._();

  final ValueNotifier<bool> active = ValueNotifier<bool>(false);

  void setActive(bool v) => active.value = v;

  /// Run an async agent task with the edge glow shown for its duration.
  Future<T> run<T>(Future<T> Function() task) async {
    active.value = true;
    try {
      return await task();
    } finally {
      active.value = false;
    }
  }
}
