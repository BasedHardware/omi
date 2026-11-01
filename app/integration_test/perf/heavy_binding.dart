import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

/// Keep real framework scheduling while suppressing LiveTestBinding's
/// unconditional tail request in handleDrawFrame (Flutter 3.44.5).
/// benchmarkLive alone still draws every vsync, including idle no-op frames.
class HeavyProfileBinding extends IntegrationTestWidgetsFlutterBinding {
  HeavyProfileBinding() {
    framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmarkLive;
  }

  @override
  void handleDrawFrame() {
    final previous = framePolicy;
    framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmark;
    try {
      super.handleDrawFrame();
    } finally {
      framePolicy = previous;
    }
  }

  // App requests from build/post-frame callbacks must still reach the engine
  // while handleDrawFrame temporarily suppresses the test binding's own tail.
  @override
  void scheduleFrame() {
    final previous = framePolicy;
    framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmarkLive;
    try {
      super.scheduleFrame();
    } finally {
      framePolicy = previous;
    }
  }

  @override
  void scheduleForcedFrame() {
    final previous = framePolicy;
    framePolicy = LiveTestWidgetsFlutterBindingFramePolicy.benchmarkLive;
    try {
      super.scheduleForcedFrame();
    } finally {
      framePolicy = previous;
    }
  }
}
